import sys
import pathlib
import time
import re
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Bootstrap path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from database.db_setup import get_connection
from database.models import insert_pricing_snapshot, log_scrape
from config import SCRAPE_DELAY_SECONDS

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

SOURCE_NAME = "Public Storage Direct"

def clean_size(size_str: str) -> str:
    """Convert '10\' x 15\'' to '10x15'."""
    if not size_str:
        return "Unknown"
    # Remove single quotes, double quotes, and spaces
    clean = size_str.replace("'", "").replace('"', '').replace(" ", "").lower()
    return clean

def run():
    """Fetch all Public Storage locations from DB and scrape their prices."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, website, zip_code FROM facilities WHERE brand = 'Public Storage' AND website IS NOT NULL")
    facilities = cur.fetchall()
    conn.close()

    total_facilities = len(facilities)
    log.info(f"Starting Public Storage scraper. Facilities to check: {total_facilities}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1"
    }

    facilities_scraped = 0
    units_found = 0

    for idx, row in enumerate(facilities):
        fac_id = row['id']
        url = row['website']
        zip_code = row['zip_code']
        
        log.info(f"[{idx+1}/{total_facilities}] Scraping Facility ID {fac_id} -> {url}")
        
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                log.warning(f"Failed to fetch {url}, status code {r.status_code}")
                continue
                
            soup = BeautifulSoup(r.text, 'html.parser')
            price_elements = soup.find_all('span', class_='unit-price')
            
            seen_units = set()
            fac_units = 0
            
            for el in price_elements:
                web_rate_str = el.get('data-pricebook-price') or el.get('data-list-price')
                street_rate_str = el.get('data-list-price') or web_rate_str
                
                if not web_rate_str:
                    continue
                    
                web_rate = float(web_rate_str)
                street_rate = float(street_rate_str)
                
                # Find size
                parent = el.parent
                size_str = None
                while parent and parent.name != 'body':
                    size_el = parent.find(string=re.compile(r"\d+'\s*x\s*\d+'"))
                    if size_el:
                        size_str = size_el.strip()
                        break
                    parent = parent.parent
                
                if not size_str:
                    continue
                    
                unit_size = clean_size(size_str)
                
                # Prevent duplicates for the same size from the same page (sometimes they list multiple similar units)
                # Or we can store all of them. Let's store the cheapest one per size.
                if unit_size in seen_units:
                    continue
                seen_units.add(unit_size)
                
                # Determine type (default standard, could try to find 'Climate Controlled')
                unit_type = 'Climate Controlled' if 'climate controlled' in r.text.lower() else 'Standard'
                
                snapshot = {
                    "facility_id": fac_id,
                    "unit_size": unit_size,
                    "unit_type": unit_type,
                    "street_rate": street_rate,
                    "web_rate": web_rate,
                    "availability": "Available",
                    "source": SOURCE_NAME
                }
                
                insert_pricing_snapshot(snapshot)
                fac_units += 1
                units_found += 1
            
            facilities_scraped += 1
            log.info(f"  Found {fac_units} unique unit sizes.")
            
        except Exception as e:
            log.error(f"Error scraping {url}: {e}")
            
        time.sleep(SCRAPE_DELAY_SECONDS)
        
    # Log scrape run
    log_scrape(SOURCE_NAME, facilities_scraped, units_found)
    log.info(f"Public Storage scrape complete! Scraped {facilities_scraped} facilities, {units_found} units.")

if __name__ == '__main__':
    run()
