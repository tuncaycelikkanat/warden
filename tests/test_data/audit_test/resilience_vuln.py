import requests

def fetch_data():
    try:
        res = requests.get("https://example.com")
        return res.json()
    except:
        pass
