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

import urllib.request
import random

def get_free_proxies() -> list:
    url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=US&ssl=all&anonymity=all"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read().decode('utf-8')
            proxies = [p.strip() for p in data.split('\n') if p.strip()]
            print(f"Fetched {len(proxies)} free US proxies.")
            return proxies
    except Exception as e:
        print(f"Failed to fetch proxies: {e}")
    return []

free_proxies_list = []

async def fetch_zip(zip_code, session, sem, today_str):
    global free_proxies_list
    city, state = get_city_state(zip_code)
    if not city or not state:
        return

    url = f"https://www.storagecafe.com/self-storage/us/{state}/{city}/"
    key_path = RAW_DIR / "storagecafe" / today_str / f"{zip_code}.html"
    
    if key_path.exists():
        print(f"[{zip_code}] Already fetched today. Skipping.")
        return

    async with sem:
        retries = 0
        max_retries = 15
        
        while retries < max_retries:
            proxy_url = None
            if retries > 0 and free_proxies_list:
                proxy_host = random.choice(free_proxies_list)
                proxy_url = f"http://{proxy_host}"
                print(f"[{zip_code}] Fetching {url} (Retry {retries}, Proxy: {proxy_url})")
            else:
                print(f"[{zip_code}] Fetching {url} (Direct)")

            try:
                # pass proxy explicitly to get
                r = await session.get(url, impersonate="chrome", timeout=15, proxy=proxy_url)
                if r.status_code == 200:
                    key_path.parent.mkdir(parents=True, exist_ok=True)
                    key_path.write_bytes(r.content)
                    break # success
                elif r.status_code == 403:
                    print(f"[{zip_code}] Blocked (403). Rotating proxy...")
                else:
                    print(f"[{zip_code}] HTTP {r.status_code}")
            except Exception as e:
                print(f"[{zip_code}] Request failed: {e.__class__.__name__}")
            
            retries += 1
            await asyncio.sleep(1)

        await asyncio.sleep(2) # Polite delay

async def fetch_all():
    global free_proxies_list
    free_proxies_list = get_free_proxies()
    today_str = date.today().isoformat()
    sem = asyncio.Semaphore(5)
    
    async with AsyncSession() as session:
        tasks = [fetch_zip(z, session, sem, today_str) for z in STORAGE_ZIP_CODES]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(fetch_all())