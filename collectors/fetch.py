import os
import asyncio
from datetime import date
from pathlib import Path
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from config import STORAGE_ZIP_CODES, SCRAPE_DELAY_SECONDS, USER_AGENT
import pgeocode
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
nomi = pgeocode.Nominatim('us')

def get_city_state(zip_code):
    try:
        zip_data = nomi.query_postal_code(zip_code)
        if str(zip_data.place_name) != 'nan' and str(zip_data.state_code) != 'nan':
            city = str(zip_data.place_name).split(',')[0].lower().replace(" ", "-")
            state = str(zip_data.state_code).lower()
            return city, state
    except Exception as e:
        print(f"Error resolving ZIP {zip_code}: {e}")
    return None, None

async def fetch_zip(zip_code, session, sem, today_str):
    city, state = get_city_state(zip_code)
    if not city or not state:
        return

    url = f"https://www.storagecafe.com/self-storage/us/{state}/{city}/"
    key_path = RAW_DIR / "storagecafe" / today_str / f"{zip_code}.html"
    
    if key_path.exists():
        print(f"[{zip_code}] Already fetched today. Skipping.")
        return

    async with sem:
        print(f"[{zip_code}] Fetching {url}")
        try:
            r = await session.get(url, impersonate="chrome")
            if r.status_code == 200:
                key_path.parent.mkdir(parents=True, exist_ok=True)
                key_path.write_bytes(r.content)
            else:
                print(f"[{zip_code}] HTTP {r.status_code}")
        except Exception as e:
            print(f"[{zip_code}] Request failed: {e}")
        
        await asyncio.sleep(2) # Polite delay

async def fetch_all():
    today_str = date.today().isoformat()
    sem = asyncio.Semaphore(5)
    
    async with AsyncSession() as session:
        tasks = [fetch_zip(z, session, sem, today_str) for z in STORAGE_ZIP_CODES]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(fetch_all())