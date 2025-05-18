#!/usr/bin/env python3
"""
Amazon Deal Bot for GitHub Actions with Persistent Pastebin URL

This script finds Amazon products with 50% or more discount,
adds affiliate links, and uploads the data to a persistent Pastebin URL
for easy Google Sheets integration. Designed to run as a
scheduled GitHub Actions workflow.
"""

import os
import json
import random
import csv
import io
import logging
import requests
from bs4 import BeautifulSoup
import argparse
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Log to stdout for GitHub Actions logs
    ]
)
logger = logging.getLogger("amazon_deals_github")

# Constants
AFFILIATE_TAG = "nicdav09-20"
MIN_DISCOUNT_PERCENT = 50
MAX_ITEMS = 25

class AmazonDealFinder:
    """Class to find Amazon deals with significant discounts."""
    
    def __init__(self, affiliate_tag, min_discount=50):
        """Initialize the deal finder with affiliate tag and minimum discount."""
        self.affiliate_tag = affiliate_tag
        self.min_discount = min_discount
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection': 'keep-alive',
            'Accept-Encoding': 'gzip, deflate, br',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def find_deals(self, max_items=25):
        """
        Find Amazon deals with discount percentage >= min_discount.
        
        This method uses web scraping to find deals since direct API access
        requires Amazon approval and credentials.
        
        Returns:
            list: List of deal dictionaries with product info and affiliate links
        """
        deals = []
        
        # Amazon deal pages to check
        deal_urls = [
            "https://www.amazon.com/gp/goldbox",
            "https://www.amazon.com/deals",
            "https://www.amazon.com/gp/todays-deals"
        ]
        
        for url in deal_urls:
            if len(deals) >= max_items:
                break
                
            try:
                logger.info(f"Checking deals at {url}")
                response = self.session.get(url, timeout=10)
                
                if response.status_code != 200:
                    logger.warning(f"Failed to fetch {url}: Status code {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for deal elements - this will need adjustment based on Amazon's current HTML structure
                deal_elements = soup.select('.dealContainer, .dealTile, .deal-card, [data-testid="deal-card"]')
                
                for deal in deal_elements:
                    if len(deals) >= max_items:
                        break
                    
                    try:
                        # Extract product information
                        product_info = self._extract_product_info(deal)
                        
                        # Only include deals with discount >= min_discount
                        if product_info and product_info.get('discount_percent', 0) >= self.min_discount:
                            # Generate affiliate link
                            product_info['affiliate_link'] = self._generate_affiliate_link(product_info['url'])
                            
                            # Format post title
                            product_info['post_title'] = self._format_post_title(product_info)
                            
                            # Calculate dollar amount off
                            if product_info.get('original_price') and product_info.get('current_price'):
                                product_info['dollar_amount_off'] = product_info['original_price'] - product_info['current_price']
                            else:
                                product_info['dollar_amount_off'] = 0
                            
                            deals.append(product_info)
                            logger.info(f"Found deal: {product_info['title']} - {product_info['discount_percent']}% off (${product_info['dollar_amount_off']:.2f} off)")
                    except Exception as e:
                        logger.error(f"Error processing deal: {e}")
                        continue
            
            except Exception as e:
                logger.error(f"Error fetching deals from {url}: {e}")
                continue
                
        # If we couldn't find enough deals with the primary method, try the search method
        if len(deals) < max_items:
            logger.info("Trying alternative method to find more deals")
            more_deals = self._find_deals_by_search(max_items - len(deals))
            deals.extend(more_deals)
            
        return deals[:max_items]
    
    def _extract_product_info(self, deal_element):
        """
        Extract product information from a deal element.
        
        Args:
            deal_element: BeautifulSoup element containing deal information
            
        Returns:
            dict: Product information including title, price, discount, etc.
        """
        try:
            # These selectors will need adjustment based on Amazon's current HTML structure
            title_elem = deal_element.select_one('.dealTitle, .a-text-normal, [data-testid="deal-title"]')
            price_elem = deal_element.select_one('.dealPrice, .a-price, [data-testid="deal-price"]')
            original_price_elem = deal_element.select_one('.dealOriginalPrice, .a-text-strike, [data-testid="deal-original-price"]')
            discount_elem = deal_element.select_one('.dealBadge, .a-badge, [data-testid="deal-discount"]')
            
            # Extract URL
            url_elem = deal_element.select_one('a[href*="/dp/"]')
            url = url_elem['href'] if url_elem else None
            
            # Make sure URL is absolute
            if url and not url.startswith('http'):
                url = f"https://www.amazon.com{url}"
            
            # If we can't find a URL, this isn't a valid deal
            if not url:
                return None
                
            # Extract ASIN from URL
            asin = None
            if '/dp/' in url:
                asin = url.split('/dp/')[1].split('/')[0].split('?')[0]
            
            # Extract title
            title = title_elem.get_text().strip() if title_elem else "Unknown Product"
            
            # Extract prices and calculate discount
            current_price = None
            original_price = None
            discount_percent = 0
            
            if price_elem:
                price_text = price_elem.get_text().strip()
                # Extract numeric price (remove currency symbol, commas, etc.)
                current_price = float(''.join(c for c in price_text if c.isdigit() or c == '.'))
            
            if original_price_elem:
                original_price_text = original_price_elem.get_text().strip()
                original_price = float(''.join(c for c in original_price_text if c.isdigit() or c == '.'))
            
            # Try to get discount from discount element
            if discount_elem:
                discount_text = discount_elem.get_text().strip()
                # Extract percentage
                discount_percent = int(''.join(c for c in discount_text if c.isdigit()))
            
            # Calculate discount if not explicitly provided
            if discount_percent == 0 and original_price and current_price:
                discount_percent = int(((original_price - current_price) / original_price) * 100)
            
            # If we still don't have a discount percentage, this might not be a deal
            if discount_percent < self.min_discount:
                return None
                
            return {
                'title': title,
                'url': url,
                'asin': asin,
                'current_price': current_price,
                'original_price': original_price,
                'discount_percent': discount_percent
            }
            
        except Exception as e:
            logger.error(f"Error extracting product info: {e}")
            return None
    
    def _find_deals_by_search(self, max_items):
        """
        Alternative method to find deals using Amazon search.
        
        Args:
            max_items: Maximum number of items to return
            
        Returns:
            list: List of deal dictionaries
        """
        deals = []
        
        # Search queries likely to return discounted items
        search_queries = [
            "deals of the day",
            "clearance sale",
            "discount 50 percent or more",
            "lightning deals",
            "sale items",
            "price drop"
        ]
        
        random.shuffle(search_queries)
        
        for query in search_queries:
            if len(deals) >= max_items:
                break
                
            try:
                search_url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}"
                logger.info(f"Searching for deals with query: {query}")
                
                response = self.session.get(search_url, timeout=10)
                
                if response.status_code != 200:
                    logger.warning(f"Failed to search {search_url}: Status code {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for search result items
                result_elements = soup.select('.s-result-item')
                
                for result in result_elements:
                    if len(deals) >= max_items:
                        break
                    
                    try:
                        # Extract product information
                        title_elem = result.select_one('h2 a span')
                        price_elem = result.select_one('.a-price .a-offscreen')
                        original_price_elem = result.select_one('.a-text-price .a-offscreen')
                        
                        # Skip sponsored results
                        if result.select_one('.s-sponsored-label-info-icon'):
                            continue
                        
                        # Extract URL and ASIN
                        url_elem = result.select_one('a[href*="/dp/"]')
                        if not url_elem:
                            continue
                            
                        url = url_elem['href']
                        if not url.startswith('http'):
                            url = f"https://www.amazon.com{url}"
                        
                        asin = None
                        if '/dp/' in url:
                            asin = url.split('/dp/')[1].split('/')[0].split('?')[0]
                        
                        # Extract title
                        title = title_elem.get_text().strip() if title_elem else "Unknown Product"
                        
                        # Extract prices
                        current_price = None
                        original_price = None
                        
                        if price_elem:
                            price_text = price_elem.get_text().strip()
                            current_price = float(''.join(c for c in price_text if c.isdigit() or c == '.'))
                        
                        if original_price_elem:
                            original_price_text = original_price_elem.get_text().strip()
                            original_price = float(''.join(c for c in original_price_text if c.isdigit() or c == '.'))
                        
                        # Calculate discount
                        discount_percent = 0
                        if original_price and current_price and original_price > current_price:
                            discount_percent = int(((original_price - current_price) / original_price) * 100)
                        
                        # Only include deals with discount >= min_discount
                        if discount_percent >= self.min_discount:
                            product_info = {
                                'title': title,
                                'url': url,
                                'asin': asin,
                                'current_price': current_price,
                                'original_price': original_price,
                                'discount_percent': discount_percent
                            }
                            
                            # Calculate dollar amount off
                            if original_price and current_price:
                                product_info['dollar_amount_off'] = original_price - current_price
                            else:
                                product_info['dollar_amount_off'] = 0
                            
                            # Generate affiliate link
                            product_info['affiliate_link'] = self._generate_affiliate_link(url)
                            
                            # Format post title
                            product_info['post_title'] = self._format_post_title(product_info)
                            
                            deals.append(product_info)
                            logger.info(f"Found deal by search: {title} - {discount_percent}% off (${product_info['dollar_amount_off']:.2f} off)")
                    
                    except Exception as e:
                        logger.error(f"Error processing search result: {e}")
                        continue
            
            except Exception as e:
                logger.error(f"Error searching for deals: {e}")
                continue
        
        return deals
    
    def _generate_affiliate_link(self, product_url):
        """
        Generate an affiliate link for the given product URL.
        
        Args:
            product_url: The product URL
            
        Returns:
            str: Affiliate link with the affiliate tag
        """
        # Clean the URL first (remove existing tags if any)
        if '?' in product_url:
            base_url, params = product_url.split('?', 1)
            param_list = params.split('&')
            filtered_params = [p for p in param_list if not p.startswith('tag=')]
            
            if filtered_params:
                clean_url = f"{base_url}?{'&'.join(filtered_params)}&tag={self.affiliate_tag}"
            else:
                clean_url = f"{base_url}?tag={self.affiliate_tag}"
        else:
            clean_url = f"{product_url}?tag={self.affiliate_tag}"
            
        return clean_url
    
    def _format_post_title(self, product_info):
        """
        Format the post title including the discount percentage.
        
        Args:
            product_info: Dictionary containing product information
            
        Returns:
            str: Formatted post title
        """
        title = product_info['title']
        discount = product_info['discount_percent']
        
        # Format price information if available
        price_info = ""
        if product_info.get('current_price') and product_info.get('original_price'):
            dollar_off = product_info['original_price'] - product_info['current_price']
            price_info = f" - ${product_info['current_price']:.2f} (was ${product_info['original_price']:.2f}, ${dollar_off:.2f} off)"
        
        return f"🔥 {discount}% OFF! {title}{price_info}"


class PastebinUploader:
    """Class to upload data to Pastebin."""
    
    def __init__(self, api_dev_key=None, paste_key=None):
        """
        Initialize the Pastebin uploader.
        
        Args:
            api_dev_key: Pastebin API developer key (optional)
            paste_key: Existing Pastebin paste key for updates (optional)
        """
        self.api_dev_key = api_dev_key
        self.api_url = "https://pastebin.com/api/api_post.php"
        self.paste_key = paste_key
        
    def upload_deals_as_csv(self, deals, title="Amazon Deals 50% Off or More"):
        """
        Upload deals to Pastebin as CSV.
        
        Args:
            deals: List of deal dictionaries
            title: Title for the Pastebin
            
        Returns:
            str: URL of the created or updated Pastebin
        """
        # Create CSV content
        csv_buffer = io.StringIO()
        csv_writer = csv.writer(csv_buffer)
        
        # Write headers
        headers = ["Product Title", "Discount %", "Dollar Amount Off", "Current Price ($)", "Original Price ($)", "Affiliate Link"]
        csv_writer.writerow(headers)
        
        # Write deal data
        for deal in deals:
            dollar_off = deal.get('dollar_amount_off', 0)
            dollar_off_formatted = f"${dollar_off:.2f} off"
            
            row = [
                deal.get('title', 'Unknown Product'),
                f"{deal.get('discount_percent', 0)}%",
                dollar_off_formatted,
                deal.get('current_price', 0),
                deal.get('original_price', 0),
                deal.get('affiliate_link', '')
            ]
            csv_writer.writerow(row)
        
        # Get CSV content
        csv_content = csv_buffer.getvalue()
        
        # Save to local CSV file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"amazon_deals_{timestamp}.csv"
        with open(csv_filename, 'w') as f:
            f.write(csv_content)
        logger.info(f"Saved deals to local CSV file: {csv_filename}")
        
        # Also save to a consistent filename for easier access
        with open("amazon_deals_latest.csv", 'w') as f:
            f.write(csv_content)
        logger.info("Saved deals to amazon_deals_latest.csv")
        
        # Upload to Pastebin
        if self.api_dev_key:
            # Use Pastebin API if key is provided
            if self.paste_key:
                return self._update_existing_paste(csv_content, title)
            else:
                return self._create_new_paste(csv_content, title)
        else:
            # Use anonymous paste if no API key
            return self._upload_anonymous(csv_content, title)
    
    def _create_new_paste(self, content, title):
        """
        Create a new Pastebin paste.
        
        Args:
            content: Content to upload
            title: Title for the Pastebin
            
        Returns:
            str: URL of the created Pastebin
        """
        try:
            data = {
                'api_dev_key': self.api_dev_key,
                'api_option': 'paste',
                'api_paste_code': content,
                'api_paste_name': title,
                'api_paste_format': 'text',  # Changed from 'csv' to 'text'
                'api_paste_private': '0',  # Public
                'api_paste_expire_date': '1M'  # Expire in 1 month
            }
            
            response = requests.post(self.api_url, data=data)
            
            if response.status_code == 200 and not response.text.startswith('Bad API request'):
                pastebin_url = response.text
                # Extract paste key from URL
                self.paste_key = pastebin_url.split('/')[-1]
                logger.info(f"Successfully created new Pastebin: {pastebin_url}")
                return pastebin_url
            else:
                logger.error(f"Failed to create Pastebin: {response.text}")
                return None
        
        except Exception as e:
            logger.error(f"Error creating Pastebin: {e}")
            return None
    
    def _update_existing_paste(self, content, title):
        """
        Update an existing Pastebin paste.
        
        Args:
            content: Content to upload
            title: Title for the Pastebin
            
        Returns:
            str: URL of the updated Pastebin
        """
        try:
            # For updating existing pastes, we need to use the raw API
            data = {
                'api_dev_key': self.api_dev_key,
                'api_option': 'paste',
                'api_paste_code': content,
                'api_paste_name': title,
                'api_paste_format': 'text',
                'api_paste_private': '0',  # Public
                'api_paste_expire_date': '1M'  # Expire in 1 month
            }
            
            # If we have a paste key, try to use it
            if self.paste_key:
                logger.info(f"Attempting to update existing paste with key: {self.paste_key}")
                
                # Add the paste key to the request
                data['api_paste_key'] = self.paste_key
                
                response = requests.post(self.api_url, data=data)
                
                if response.status_code == 200 and not response.text.startswith('Bad API request'):
                    # If successful, the response will be the URL of the updated paste
                    pastebin_url = f"https://pastebin.com/{self.paste_key}"
                    logger.info(f"Successfully updated existing Pastebin: {pastebin_url}")
                    return pastebin_url
                else:
                    logger.warning(f"Failed to update existing paste: {response.text}")
                    # If update fails, try creating a new paste
                    logger.info("Attempting to create a new paste instead")
                    return self._create_new_paste(content, title)
            else:
                # If we don't have a paste key, create a new paste
                return self._create_new_paste(content, title)
        
        except Exception as e:
            logger.error(f"Error updating Pastebin: {e}")
            return None
    
    def _upload_anonymous(self, content, title):
        """
        Upload content to Pastebin anonymously.
        
        Args:
            content: Content to upload
            title: Title for the Pastebin
            
        Returns:
            str: URL of the created Pastebin
        """
        try:
            # Since we can't use the API without a key, we'll simulate what would happen
            # In a real implementation, this would use browser automation or another service
            
            logger.warning("Anonymous Pastebin upload not implemented - would require browser automation")
            logger.info("Simulating Pastebin upload - in a real scenario, this would create a public paste")
            
            # Save content locally as CSV for demonstration
            csv_filename = "amazon_deals.csv"
            with open(csv_filename, 'w') as f:
                f.write(content)
            
            logger.info(f"Saved deals to local CSV file: {csv_filename}")
            
            # Return a placeholder URL
            simulated_url = f"https://pastebin.com/simulated_paste_for_{title.replace(' ', '_')}"
            return simulated_url
        
        except Exception as e:
            logger.error(f"Error with anonymous Pastebin upload: {e}")
            return None


def save_deals_to_file(deals, filename="amazon_deals.json"):
    """Save deals to a JSON file for reference."""
    try:
        with open(filename, 'w') as f:
            json.dump(deals, f, indent=2)
        logger.info(f"Saved {len(deals)} deals to {filename}")
    except Exception as e:
        logger.error(f"Error saving deals to file: {e}")


def main():
    """Main function to run the Amazon deal finder for GitHub Actions."""
    parser = argparse.ArgumentParser(description='Amazon Deal Bot for GitHub Actions')
    parser.add_argument('--api-key', help='Pastebin API developer key')
    parser.add_argument('--paste-key', help='Existing Pastebin paste key for updates')
    parser.add_argument('--max-items', type=int, default=MAX_ITEMS,
                        help=f'Maximum items to find (default: {MAX_ITEMS})')
    parser.add_argument('--simulate', action='store_true', 
                        help='Run in simulation mode without Pastebin upload')
    args = parser.parse_args()
    
    # Get API key from arguments or environment variable
    api_key = args.api_key or os.environ.get('PASTEBIN_API_KEY')
    
    # Get paste key from arguments or environment variable
    paste_key = args.paste_key or os.environ.get('PASTEBIN_PASTE_KEY')
    
    logger.info("Starting Amazon Deal Bot for GitHub Actions")
    
    # Initialize the deal finder
    deal_finder = AmazonDealFinder(
        affiliate_tag=AFFILIATE_TAG,
        min_discount=MIN_DISCOUNT_PERCENT
    )
    
    # Find deals
    logger.info(f"Finding deals with {MIN_DISCOUNT_PERCENT}% or more discount")
    deals = deal_finder.find_deals(max_items=args.max_items)
    
    if not deals:
        logger.warning("No deals found")
        return
    
    # Save deals to JSON file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_file = f"amazon_deals_{timestamp}.json"
    save_deals_to_file(deals, json_file)
    
    # Also save to a consistent filename for easier access
    save_deals_to_file(deals, "amazon_deals_latest.json")
    
    # Initialize the Pastebin uploader with API key and paste key
    pastebin_uploader = PastebinUploader(api_dev_key=api_key, paste_key=paste_key)
    
    # Upload deals to Pastebin
    if not args.simulate and api_key:
        logger.info("Uploading deals to Pastebin")
        title = f"Amazon Deals {MIN_DISCOUNT_PERCENT}% Off or More - Updated {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        pastebin_url = pastebin_uploader.upload_deals_as_csv(deals, title=title)
        
        if pastebin_url:
            logger.info(f"Successfully uploaded deals to Pastebin: {pastebin_url}")
            print(f"Pastebin URL: {pastebin_url}")
            print("Use this formula in Google Sheets to import the data:")
            print(f'=IMPORTDATA("{pastebin_url}/raw")')
            
            # If we're using a persistent paste key, remind the user
            if paste_key:
                logger.info(f"Using persistent paste key: {paste_key}")
                print(f"Using persistent paste key: {paste_key}")
                print(f"Your Google Sheets formula will always work with: =IMPORTDATA(\"https://pastebin.com/raw/{paste_key}\")")
        else:
            logger.error("Failed to upload deals to Pastebin")
    else:
        logger.info("Running in simulation mode or without API key - skipping Pastebin upload")
        # Save deals to CSV file for manual upload
        csv_filename = f"amazon_deals_{timestamp}.csv"
        csv_content = io.StringIO()
        csv_writer = csv.writer(csv_content)
        
        # Write headers
        headers = ["Product Title", "Discount %", "Dollar Amount Off", "Current Price ($)", "Original Price ($)", "Affiliate Link"]
        csv_writer.writerow(headers)
        
        # Write deal data
        for deal in deals:
            dollar_off = deal.get('dollar_amount_off', 0)
            dollar_off_formatted = f"${dollar_off:.2f} off"
            
            row = [
                deal.get('title', 'Unknown Product'),
                f"{deal.get('discount_percent', 0)}%",
                dollar_off_formatted,
                deal.get('current_price', 0),
                deal.get('original_price', 0),
                deal.get('affiliate_link', '')
            ]
            csv_writer.writerow(row)
        
        # Save CSV content to file
        with open(csv_filename, 'w') as f:
            f.write(csv_content.getvalue())
        logger.info(f"Saved deals to CSV file: {csv_filename}")
        
        # Also save to a consistent filename for easier access
        with open("amazon_deals_latest.csv", 'w') as f:
            f.write(csv_content.getvalue())
        logger.info("Saved deals to amazon_deals_latest.csv")


if __name__ == "__main__":
    main()
