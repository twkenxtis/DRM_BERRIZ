import asyncio
from pprint import pprint
from unit.http.request_berriz_api import *
from lib.Proxy import *

async def main():
    params: Dict[str, str] = {"languageCode": 'en'}
    url: str = "https://svc-api.berriz.in/service/v1/my/geo-location"
    headers = {
    "Host": "svc-api.berriz.in",
    "Referer": "https://berriz.in/",
    "Origin": "https://berriz.in",
    "Accept": "application/json",
    'pragma': 'no-cache',
    "User-Agent": f"{USERAGENT}"
    }
    P = await BerrizAPIClient()._send_request(url, params, headers)


async def main2():
    await Berriz_cookie.create_temp_json()
    await Berriz_cookie().get_valid_cookie()
    await Refresh_JWT().refresh_token()
    await Berriz_cookie().get_cookies()
    await BerrizAPIClient().ensure_cookie()
    print(await BerrizAPIClient().cookie())
    
    
async def proxy():
    proxy = Proxy._load_proxies()
    print(type(proxy))
    
if __name__ == '__main__':
    asyncio.run(proxy())