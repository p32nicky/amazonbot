#!/usr/bin/env python3
"""
Enhanced Amazon Deal Bot for GitHub Pages

This script finds Amazon products with 50% or more discount,
adds affiliate links, and saves the data as a CSV file in the docs directory
for GitHub Pages to host. This allows for easy Google Sheets integration.

Enhanced version with:
- Increased MAX_ITEMS to find more deals
- More search queries for wider coverage
- Improved error handling and retry mechanism
- Better parsing of product information
"""

import os
import json
import random
import csv
import io
import logging
import requests
import time
import re
from bs4 import BeautifulSoup
import argparse
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

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
MAX_ITEMS = 100  # Increased from 25 to 100
MAX_RETRIES = 3  # Number of retries for failed requests
RETRY_DELAY = 2  # Delay between retries in seconds

class AmazonDealFinder:
    """Enhanced class to find Amazon deals with significant discounts."""
    
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
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        # Add a list of user agents to rotate
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
        ]
    
    def _get_with_retries(self, url, max_retries=MAX_RETRIES, delay=RETRY_DELAY):
        """
        Make a GET request with retries and rotating user agents.
        
        Args:
            url: URL to request
            max_retries: Maximum number of retry attempts
            delay: Delay between retries in seconds
            
        Returns:
            requests.Response object or None if all retries fail
        """
        for attempt in range(max_retries):
            try:
                # Rotate user agent for each attempt
                self.session.headers.update({
                    'User-Agent': random.choice(self.user_agents)
                })
                
                response = self.session.get(url, timeout=15)
                
                # Check if we got a successful response
                if response.status_code == 200:
                    return response
                
                # If we got a 503 or 429, wait longer before retry
                if response.status_code in [503, 429]:
                    logger.warning(f"Rate limited (status {response.status_code}) on attempt {attempt+1}/{max_retries}, waiting longer...")
                    time.sleep(delay * 2)  # Wait twice as long
                else:
                    logger.warning(f"Failed to fetch {url}: Status code {response.status_code} on attempt {attempt+1}/{max_retries}")
                    time.sleep(delay)
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error for {url} on attempt {attempt+1}/{max_retries}: {e}")
                time.sleep(delay)
                
        logger.error(f"All {max_retries} attempts to fetch {url} failed")
        return None
    
    def find_deals(self, max_items=MAX_ITEMS):
        """
        Find Amazon deals with discount percentage >= min_discount.
        
        Enhanced to find more deals and handle errors better.
        
        Returns:
            list: List of deal dictionaries with product info and affiliate links
        """
        deals = []
        
        # Amazon deal pages to check
        deal_urls = [
            "https://www.amazon.com/gp/goldbox",
            "https://www.amazon.com/deals",
            "https://www.amazon.com/gp/todays-deals",
            "https://www.amazon.com/gp/bestsellers",
            "https://www.amazon.com/gp/new-releases"
        ]
        
        for url in deal_urls:
            if len(deals) >= max_items:
                break
                
            try:
                logger.info(f"Checking deals at {url}")
                response = self._get_with_retries(url)
                
                if not response:
                    logger.warning(f"Skipping {url} due to failed requests")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for deal elements - try multiple selectors for better coverage
                deal_elements = soup.select('.dealContainer, .dealTile, .deal-card, [data-testid="deal-card"], .a-carousel-card, .octopus-pc-card, .octopus-pc-item')
                
                if not deal_elements:
                    logger.info(f"No deal elements found with primary selectors, trying alternative selectors")
                    # Try alternative selectors
                    deal_elements = soup.select('.a-carousel-card, .a-list-item, .a-section')
                
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
                            
                            # Check if this is a duplicate (same URL or title)
                            is_duplicate = False
                            for existing_deal in deals:
                                if (existing_deal.get('url') == product_info.get('url') or 
                                    existing_deal.get('title') == product_info.get('title')):
                                    is_duplicate = True
                                    break
                            
                            if not is_duplicate:
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
            logger.info(f"Found {len(deals)} deals so far, trying search method to find more")
            more_deals = self._find_deals_by_search(max_items - len(deals))
            
            # Add non-duplicate deals
            for deal in more_deals:
                # Check if this is a duplicate
                is_duplicate = False
                for existing_deal in deals:
                    if (existing_deal.get('url') == deal.get('url') or 
                        existing_deal.get('title') == deal.get('title')):
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    deals.append(deal)
                    
                if len(deals) >= max_items:
                    break
            
        return deals[:max_items]
    
    def _extract_product_info(self, deal_element):
        """
        Extract product information from a deal element.
        
        Enhanced with better selectors and more robust parsing.
        
        Args:
            deal_element: BeautifulSoup element containing deal information
            
        Returns:
            dict: Product information including title, price, discount, etc.
        """
        try:
            # Try multiple selectors for each element to improve coverage
            title_elem = None
            for selector in ['.dealTitle', '.a-text-normal', '[data-testid="deal-title"]', 'h2 a span', '.a-size-medium', '.a-link-normal span']:
                title_elem = deal_element.select_one(selector)
                if title_elem:
                    break
            
            price_elem = None
            for selector in ['.dealPrice', '.a-price', '[data-testid="deal-price"]', '.a-price .a-offscreen', '.a-color-price']:
                price_elem = deal_element.select_one(selector)
                if price_elem:
                    break
            
            original_price_elem = None
            for selector in ['.dealOriginalPrice', '.a-text-strike', '[data-testid="deal-original-price"]', '.a-price.a-text-price .a-offscreen', '.a-text-price']:
                original_price_elem = deal_element.select_one(selector)
                if original_price_elem:
                    break
            
            discount_elem = None
            for selector in ['.dealBadge', '.a-badge', '[data-testid="deal-discount"]', '.a-color-secondary', '.octopus-deal-badge']:
                discount_elem = deal_element.select_one(selector)
                if discount_elem:
                    break
            
            # Extract URL - try multiple approaches
            url = None
            url_elem = None
            
            # Try direct link to product
            for selector in ['a[href*="/dp/"]', 'a[href*="/gp/product/"]', 'a[href*="/product/"]']:
                url_elem = deal_element.select_one(selector)
                if url_elem:
                    url = url_elem['href']
                    break
            
            # If no direct link, try parent elements
            if not url:
                parent = deal_element.parent
                for _ in range(3):  # Check up to 3 levels up
                    if parent:
                        url_elem = parent.select_one('a[href*="/dp/"]')
                        if url_elem:
                            url = url_elem['href']
                            break
                        parent = parent.parent
            
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
            elif '/product/' in url:
                asin = url.split('/product/')[1].split('/')[0].split('?')[0]
            elif '/gp/product/' in url:
                asin = url.split('/gp/product/')[1].split('/')[0].split('?')[0]
            
            # Extract title
            title = "Unknown Product"
            if title_elem:
                title = title_elem.get_text().strip()
            
            # Extract prices and calculate discount
            current_price = None
            original_price = None
            discount_percent = 0
            
            # Extract current price
            if price_elem:
                price_text = price_elem.get_text().strip()
                # Extract numeric price (remove currency symbol, commas, etc.)
                price_match = re.search(r'[\d,]+\.\d+', price_text)
                if price_match:
                    current_price = float(price_match.group(0).replace(',', ''))
                else:
                    # Try another pattern
                    price_match = re.search(r'\d+', price_text)
                    if price_match:
                        current_price = float(price_match.group(0))
            
            # Extract original price
            if original_price_elem:
                original_price_text = original_price_elem.get_text().strip()
                # Extract numeric price
                price_match = re.search(r'[\d,]+\.\d+', original_price_text)
                if price_match:
                    original_price = float(price_match.group(0).replace(',', ''))
                else:
                    # Try another pattern
                    price_match = re.search(r'\d+', original_price_text)
                    if price_match:
                        original_price = float(price_match.group(0))
            
            # Try to get discount from discount element
            if discount_elem:
                discount_text = discount_elem.get_text().strip()
                # Extract percentage
                discount_match = re.search(r'(\d+)%', discount_text)
                if discount_match:
                    discount_percent = int(discount_match.group(1))
                else:
                    # Try to find any number
                    discount_match = re.search(r'\d+', discount_text)
                    if discount_match:
                        discount_percent = int(discount_match.group(0))
            
            # Calculate discount if not explicitly provided
            if discount_percent == 0 and original_price and current_price and original_price > current_price:
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
        
        Enhanced with more search queries and better error handling.
        
        Args:
            max_items: Maximum number of items to return
            
        Returns:
            list: List of deal dictionaries
        """
        deals = []
        
        # Expanded list of search queries likely to return discounted items
        search_queries = [
            "deals of the day",
            "clearance sale",
            "discount 50 percent or more",
            "lightning deals",
            "sale items",
            "price drop",
            "flash sale",
            "limited time offer",
            "bargain finds",
            "today's special",
            "huge discount",
            "clearance items",
            "big savings",
            "special offer",
            "deal of the week",
            "price reduction",
            "markdown",
            "closeout sale",
            "hot deals",
            "best deals"
        ]
        
        # Add some category-specific queries
        categories = ["electronics", "home", "kitchen", "toys", "clothing", "beauty", "books", "sports"]
        for category in categories:
            search_queries.append(f"{category} deals")
            search_queries.append(f"{category} sale")
        
        random.shuffle(search_queries)
        
        for query in search_queries:
            if len(deals) >= max_items:
                break
                
            try:
                search_url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}"
                logger.info(f"Searching for deals with query: {query}")
                
                response = self._get_with_retries(search_url)
                
                if not response:
                    logger.warning(f"Skipping search query '{query}' due to failed requests")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for search result items
                result_elements = soup.select('.s-result-item')
                
                for result in result_elements:
                    if len(deals) >= max_items:
                        break
                    
                    try:
                        # Skip sponsored results
                        if result.select_one('.s-sponsored-label-info-icon'):
                            continue
                        
                        # Extract product information using multiple selectors
                        title_elem = result.select_one('h2 a span') or result.select_one('.a-size-medium') or result.select_one('.a-link-normal span')
                        price_elem = result.select_one('.a-price .a-offscreen') or result.select_one('.a-color-price')
                        original_price_elem = result.select_one('.a-text-price .a-offscreen') or result.select_one('.a-text-strike')
                        
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
                            price_match = re.search(r'[\d,]+\.\d+', price_text)
                            if price_match:
                                current_price = float(price_match.group(0).replace(',', ''))
                        
                        if original_price_elem:
                            original_price_text = original_price_elem.get_text().strip()
                            price_match = re.search(r'[\d,]+\.\d+', original_price_text)
                            if price_match:
                                original_price = float(price_match.group(0).replace(',', ''))
                        
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
        
        Enhanced with better URL parsing and handling.
        
        Args:
            product_url: The product URL
            
        Returns:
            str: Affiliate link with the affiliate tag
        """
        try:
            # Parse the URL
            parsed_url = urlparse(product_url)
            
            # Get existing query parameters
            query_params = parse_qs(parsed_url.query)
            
            # Remove any existing tag parameter
            if 'tag' in query_params:
                del query_params['tag']
            
            # Add our affiliate tag
            query_params['tag'] = [self.affiliate_tag]
            
            # Build the new query string
            new_query = urlencode(query_params, doseq=True)
            
            # Reconstruct the URL
            clean_url = urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                new_query,
                parsed_url.fragment
            ))
            
            return clean_url
            
        except Exception as e:
            logger.error(f"Error generating affiliate link: {e}")
            # Fallback to simple method
            if '?' in product_url:
                return f"{product_url}&tag={self.affiliate_tag}"
            else:
                return f"{product_url}?tag={self.affiliate_tag}"
    
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
        with open(filename, 'w', newline='', encoding='utf-8') as f:
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
    parser = argparse.ArgumentParser(description='Enhanced Amazon Deal Bot for GitHub Pages')
    parser.add_argument('--max-items', type=int, default=MAX_ITEMS,
                        help=f'Maximum items to find (default: {MAX_ITEMS})')
    parser.add_argument('--min-discount', type=int, default=MIN_DISCOUNT_PERCENT,
                        help=f'Minimum discount percentage (default: {MIN_DISCOUNT_PERCENT})')
    parser.add_argument('--simulate', action='store_true', 
                        help='Run in simulation mode with sample data')
    args = parser.parse_args()
    
    logger.info("Starting Enhanced Amazon Deal Bot for GitHub Pages")
    
    # Ensure the docs directory exists
    ensure_docs_directory()
    
    # Initialize the deal finder
    deal_finder = AmazonDealFinder(
        affiliate_tag=AFFILIATE_TAG,
        min_discount=args.min_discount
    )
    
    # Find deals
    logger.info(f"Finding deals with {args.min_discount}% or more discount")
    deals = deal_finder.find_deals(max_items=args.max_items)
    
    if not deals:
        logger.warning("No deals found")
        # Create empty files to avoid workflow failures
        save_deals_to_file([], "docs/amazon_deals_latest.json")
        save_deals_to_csv([], "docs/amazon_deals.csv")
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
    <title>Amazon Deals {args.min_discount}% Off or More</title>
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
        <h1>Amazon Deals {args.min_discount}% Off or More</h1>
        <p>If you are not redirected automatically, click <a href="amazon_deals.csv">here</a> to access the CSV file.</p>
        <p>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        <p>Found {len(deals)} deals with {args.min_discount}% or more discount.</p>
        <p>To use this data in Google Sheets, use the following formula:</p>
        <pre>=IMPORTDATA("https://YOUR-USERNAME.github.io/YOUR-REPO-NAME/amazon_deals.csv")</pre>
        <p>(Replace YOUR-USERNAME with your actual GitHub username and YOUR-REPO-NAME with your repository name)</p>
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
    logger.info(f"Found and saved {len(deals)} deals with {args.min_discount}% or more discount")


if __name__ == "__main__":
    main()
