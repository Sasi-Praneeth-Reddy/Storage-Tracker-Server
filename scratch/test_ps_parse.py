import re
from bs4 import BeautifulSoup

def test_parse():
    html = open('ps.html', encoding='utf-8').read()
    soup = BeautifulSoup(html, 'html.parser')
    
    # In public storage HTML, each unit is often inside a card or container.
    # Let's find all the unit-price labels
    price_elements = soup.find_all('span', class_='unit-price')
    for el in price_elements:
        try:
            web_rate = el.get('data-pricebook-price') or el.get('data-list-price')
            street_rate = el.get('data-list-price') or web_rate
            
            # Walk up the tree to find the nearest element that has a size like 5'x10'
            parent = el.parent
            size = None
            while parent and parent.name != 'body':
                size_el = parent.find(string=re.compile(r"\d+'\s*x\s*\d+'"))
                if size_el:
                    size = size_el.strip()
                    break
                parent = parent.parent
            print(f"Size: {size}, Web: {web_rate}, Street: {street_rate}")
        except Exception as e:
            pass

if __name__ == '__main__':
    test_parse()
