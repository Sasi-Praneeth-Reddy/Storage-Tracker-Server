import requests
from bs4 import BeautifulSoup
import json

url = "https://www.publicstorage.com/self-storage-dc-washington/2195.html"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": "\"Not_A Brand\";v=\"8\", \"Chromium\";v=\"120\", \"Google Chrome\";v=\"120\"",
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": "\"Windows\"",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

r = requests.get(url, headers=headers)
print("Status:", r.status_code)

if r.status_code == 200:
    html = r.text
    print("Length:", len(html))
    
    # Try parsing NEXT_DATA
    soup = BeautifulSoup(html, 'html.parser')
    script = soup.find('script', id='__NEXT_DATA__')
    if script:
        print("Found __NEXT_DATA__")
        data = json.loads(script.string)
        # Check if units are in the data
        try:
            # Structure usually is props.pageProps.initialState...
            props = data.get('props', {})
            pageProps = props.get('pageProps', {})
            print("pageProps keys:", pageProps.keys())
            
            # Let's save the NEXT_DATA for inspection
            with open('public_storage_data.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            print("Saved to public_storage_data.json")
        except Exception as e:
            print("Error parsing __NEXT_DATA__:", e)
    else:
        print("__NEXT_DATA__ not found. Might not be NextJS.")
