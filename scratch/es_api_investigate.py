import json
from bs4 import BeautifulSoup

html = open('es.html', encoding='utf-8').read()
soup = BeautifulSoup(html, 'html.parser')
script = soup.find('script', id='__NEXT_DATA__')
if script:
    data = json.loads(script.string)
    with open('es_data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print("Saved NEXT_DATA to es_data.json")
else:
    print("No NEXT_DATA found.")
