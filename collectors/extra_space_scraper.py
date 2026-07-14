import sys
import pathlib
import time
import json
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

SOURCE_NAME = "Extra Space Direct"

def clean_size(size_str: str) -> str:
    """Convert "4' x 2'" to "4x2"."""
    if not size_str:
        return "Unknown"
    # Remove single quotes, double quotes, and spaces
    clean = size_str.replace("'", "").replace('"', '').replace(" ", "").lower()
    return clean

def scrape_extra_space():
    """Fetch all Extra Space Storage locations from DB and scrape their prices."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, website, zip_code FROM facilities WHERE brand = 'Extra Space Storage' AND website IS NOT NULL")
    facilities = cur.fetchall()
    conn.close()

    total_facilities = len(facilities)
    log.info(f"Starting Extra Space scraper. Facilities to check: {total_facilities}")

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
        
        log.info(f"[{idx+1}/{total_facilities}] Scraping Facility ID {fac_id} -> {url}")
        
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                log.warning(f"Failed to fetch {url}, status code {r.status_code}")
                continue
                
            soup = BeautifulSoup(r.text, 'html.parser')
            script = soup.find('script', id='__NEXT_DATA__')
            
            if not script:
                log.warning(f"No __NEXT_DATA__ found for {url}")
                continue
                
            data = json.loads(script.string)
            try:
                # The nested structure we found
                unit_classes = data['props']['pageProps']['pageData']['data']['unitClasses']['data']['unitClasses']
            except KeyError:
                log.warning(f"Unexpected JSON structure for {url}")
                continue
            
            seen_units = set()
            fac_units = 0
            
            for u in unit_classes:
                try:
                    dimensions = u.get('dimensions', {})
                    rates = u.get('rates', {})
                    
                    display_size = dimensions.get('display')
                    if not display_size:
                        continue
                        
                    unit_size = clean_size(display_size)
                    
                    web_rate = rates.get('web')
                    street_rate = rates.get('street')
                    
                    if web_rate is None:
                        continue
                        
                    # Skip duplicates
                    if unit_size in seen_units:
                        continue
                    seen_units.add(unit_size)
                    
                    # Attributes
                    features = u.get('features', [])
                    unit_type = 'Climate Controlled' if 'Climate Controlled' in features else 'Standard'
                    
                    snapshot = {
                        "facility_id": fac_id,
                        "unit_size": unit_size,
                        "unit_type": unit_type,
                        "street_rate": float(street_rate) if street_rate else float(web_rate),
                        "web_rate": float(web_rate),
                        "availability": "Available",
                        "source": SOURCE_NAME
                    }
                    
                    insert_pricing_snapshot(snapshot)
                    fac_units += 1
                    units_found += 1
                except Exception as e:
                    log.warning(f"Error parsing unit: {e}")
                    continue
            
            facilities_scraped += 1
            log.info(f"  Found {fac_units} unique unit sizes.")
            
        except Exception as e:
            log.error(f"Error scraping {url}: {e}")
            
        time.sleep(SCRAPE_DELAY_SECONDS)
        
    # Log scrape run
    log_scrape(SOURCE_NAME, facilities_scraped, units_found)
    log.info(f"Extra Space scrape complete! Scraped {facilities_scraped} facilities, {units_found} units.")

if __name__ == '__main__':
    scrape_extra_space()
