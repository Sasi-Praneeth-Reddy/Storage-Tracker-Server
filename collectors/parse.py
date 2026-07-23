import os
import sys
from datetime import date
from pathlib import Path
from bs4 import BeautifulSoup
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_setup import get_connection, create_tables
from database.models import upsert_facility, insert_pricing_snapshot, log_scrape

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "storagecafe"

def parse_html(filepath, scrape_date):
    html = filepath.read_text(encoding='utf-8', errors='replace')
    soup = BeautifulSoup(html, 'html.parser')
    zip_code = filepath.stem
    facilities_found = 0
    
    # StorageCafe wraps each facility in a 'property-card-info' div
    cards = soup.find_all('div', class_=lambda cl: cl and 'property-card-info' in cl)
    for card in cards:
        name_tag = card.find('h2')
        if not name_tag:
            continue
        
        name = name_tag.text.strip()
        address, city, state = "Unknown", "Unknown", "Unknown"
        zip_out = zip_code
        
        # Their name tags usually look like: "Public Storage - 123 Main St, City, ST 12345"
        if ' - ' in name:
            parts = name.split(' - ', 1)
            brand_or_name = parts[0].strip()
            addr_part = parts[1].strip()
            
            if ',' in addr_part:
                addr_splits = addr_part.split(',')
                address = addr_splits[0].strip()
                if len(addr_splits) > 1:
                    city = addr_splits[1].strip()
                if len(addr_splits) > 2:
                    st_zip = addr_splits[2].strip().split(' ')
                    state = st_zip[0].strip()
                    if len(st_zip) > 1:
                        zip_out = st_zip[-1].strip()
        else:
            brand_or_name = name
            
        brand = brand_or_name if brand_or_name in [
            "Public Storage", "Extra Space Storage", "CubeSmart", "Life Storage", "U-Haul", "StorageMart"
        ] else "Independent"
            
        phone = "Unknown"
        phone_tag = card.find('a', href=lambda h: h and 'tel:' in h)
        if phone_tag:
            phone = phone_tag.text.strip()
            
        # Get approximate lat/lon based on zip code
        import pgeocode
        nomi = pgeocode.Nominatim('us')
        zip_data = nomi.query_postal_code(zip_out)
        lat, lon = 0.0, 0.0
        if str(zip_data.latitude) != 'nan':
            lat = float(zip_data.latitude)
        if str(zip_data.longitude) != 'nan':
            lon = float(zip_data.longitude)
            
        # 1. Upsert Facility
        facility_data = {
            "google_place_id": f"sc_{zip_out}_{brand_or_name.replace(' ', '_')}",
            "name": brand_or_name,
            "address": address,
            "city": city,
            "state": state,
            "zip_code": zip_out,
            "phone": phone,
            "website": "https://www.storagecafe.com",
            "brand": brand,
            "lat": lat,
            "lon": lon
        }
        facility_id = upsert_facility(facility_data)
        facilities_found += 1
        
        # 2. Parse Prices
        # Prices sit outside the 'info' div, up one level in the 'details' div under 'pcum-row'
        unit_types = card.parent.parent.find_all('div', class_='pcum-row') if card.parent.parent else []
        for ut in unit_types:
            size_txt = ut.find('span', class_='pcum-dimensions')
            price_txt = ut.find('span', class_='pcum-price')
            
            if size_txt and price_txt:
                s = size_txt.text.strip()
                p_str = price_txt.text.strip().replace('$', '').replace('/mo', '').replace(',', '')
                try:
                    p = float(p_str)
                    price_data = {
                        "facility_id": facility_id,
                        "unit_size": s,
                        "unit_type": "Unknown",
                        "street_rate": p,
                        "web_rate": p,
                        "availability": "Available",
                        "source": "StorageCafe",
                        "scraped_at": scrape_date
                    }
                    insert_pricing_snapshot(price_data)
                except ValueError:
                    pass
                
    return facilities_found

def parse_all(target_date_str=None):
    if not target_date_str:
        target_date_str = date.today().isoformat()
        
    date_dir = RAW_DIR / target_date_str
    if not date_dir.exists():
        print(f"No raw data found for {target_date_str} in {date_dir}")
        return 0
        
    # Ensure tables exist
    conn = get_connection()
    create_tables(conn)
    conn.close()
    
    total_facilities = 0
    
    for filepath in date_dir.glob("*.html"):
        print(f"Parsing {filepath.name}...")
        try:
            count = parse_html(filepath, target_date_str)
            total_facilities += count
            print(f"  -> Found {count} facilities")
        except Exception as e:
            print(f"  -> Error parsing {filepath.name}: {e}")
            
    print(f"Parsing complete. Total facilities updated: {total_facilities}")
    log_scrape("storagecafe_etl", "success", total_facilities, f"Parsed date {target_date_str}")

    # Archive HTML files
    archive_dir = RAW_DIR / "archive" / target_date_str
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    for filepath in date_dir.glob("*.html"):
        shutil.move(str(filepath), str(archive_dir / filepath.name))

    print(f"Parsing complete. Total facilities updated: {total_facilities}")
    log_scrape("storagecafe_etl", "success", total_facilities, f"Parsed date {target_date_str}")
    
    # --- NEW CLEANUP STEP ---
    print(f"Cleaning up raw HTML files to save space...")
    shutil.rmtree(date_dir)
    print(f"Removed folder: {date_dir}")
    # ------------------------

    return total_facilities

if __name__ == "__main__":
    parse_all()