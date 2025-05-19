#!/usr/bin/env python3
"""
Amazon Deal Bot for GitHub Pages

This script finds Amazon products with 50% or more discount,
adds affiliate links, and saves the data as a CSV file in the docs directory
for GitHub Pages to host. This allows for easy Google Sheets integration.
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
MAX_ITEMS = 100

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
    "price drop",
    "flash sale",
    "bargain finds",
    "today's special",
    "limited time offer",
    "huge discount",
    "clearance items",
    "big savings",
    "special offer",
    "deal of the week"
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


def save_deals_to_file(deals, filename="amazon_deals.json"):
    """Save deals to a JSON file for reference."""
    try:
        with open(filename, 'w') as f:
            json.dump(deals, f, indent=2)
        logger.info(f"Saved {len(deals)} deals to {filename}")
    except Exception as e:
        logger.error(f"Error saving deals to file: {e}")


def save_deals_to_csv(deals, filename="amazon_deals.csv"):
    """Save deals to a CSV file for GitHub Pages."""
    try:
        with open(filename, 'w', newline='') as f:
            csv_writer = csv.writer(f)
            
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
                
        logger.info(f"Saved deals to CSV file: {filename}")
    except Exception as e:
        logger.error(f"Error saving deals to CSV: {e}")


def ensure_docs_directory():
    """Ensure the docs directory exists for GitHub Pages."""
    try:
        if not os.path.exists('docs'):
            os.makedirs('docs')
            logger.info("Created docs directory for GitHub Pages")
    except Exception as e:
        logger.error(f"Error creating docs directory: {e}")


def main():
    """Main function to run the Amazon deal finder for GitHub Pages."""
    parser = argparse.ArgumentParser(description='Amazon Deal Bot for GitHub Pages')
    parser.add_argument('--max-items', type=int, default=MAX_ITEMS,
                        help=f'Maximum items to find (default: {MAX_ITEMS})')
    parser.add_argument('--simulate', action='store_true', 
                        help='Run in simulation mode with sample data')
    args = parser.parse_args()
    
    logger.info("Starting Amazon Deal Bot for GitHub Pages")
    
    # Ensure the docs directory exists
    ensure_docs_directory()
    
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
    json_file = f"docs/amazon_deals_{timestamp}.json"
    save_deals_to_file(deals, json_file)
    
    # Also save to a consistent filename for easier access
    save_deals_to_file(deals, "docs/amazon_deals_latest.json")
    
    # Save deals to CSV file for GitHub Pages
    csv_file = f"docs/amazon_deals_{timestamp}.csv"
    save_deals_to_csv(deals, csv_file)
    
    # Also save to a consistent filename for easier access
    save_deals_to_csv(deals, "docs/amazon_deals.csv")
    
    # Create an index.html file that redirects to the CSV
    index_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="0; url=amazon_deals.csv">
    <title>Amazon Deals 50% Off or More</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}
        h1 {{
            color: #232f3e;
        }}
        p {{
            margin-bottom: 15px;
        }}
        a {{
            color: #e47911;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Amazon Deals 50% Off or More</h1>
        <p>If you are not redirected automatically, click <a href="amazon_deals.csv">here</a> to access the CSV file.</p>
        <p>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        <p>To use this data in Google Sheets, use the following formula:</p>
        <pre>=IMPORTDATA("https://YOUR-USERNAME.github.io/amazon-deal-bot/amazon_deals.csv")</pre>
        <p>(Replace YOUR-USERNAME with your actual GitHub username)</p>
    </div>
</body>
</html>
"""
    
    try:
        with open("docs/index.html", 'w') as f:
            f.write(index_html)
        logger.info("Created index.html for GitHub Pages")
    except Exception as e:
        logger.error(f"Error creating index.html: {e}")
    
    # Output the GitHub Pages URL for Google Sheets
    repo_name = os.environ.get('GITHUB_REPOSITORY', 'amazon-deal-bot')
    if '/' in repo_name:
        _, repo_name = repo_name.split('/', 1)
    
    github_username = os.environ.get('GITHUB_ACTOR', 'YOUR-USERNAME')
    
    github_pages_url = f"https://{github_username}.github.io/{repo_name}/amazon_deals.csv"
    
    print("\n" + "="*80)
    print(f"GitHub Pages URL for your Amazon Deals CSV:")
    print(github_pages_url)
    print("\nTo use this in Google Sheets, paste this formula in cell A1:")
    print(f'=IMPORTDATA("{github_pages_url}")')
    print("="*80 + "\n")
    
    logger.info(f"GitHub Pages URL: {github_pages_url}")
    logger.info(f"Found and saved {len(deals)} deals with {MIN_DISCOUNT_PERCENT}% or more discount")


if __name__ == "__main__":
    main()
