import requests

API = 'https://cdm.ive.rest/'

headers = {
    'Authorization': 'SHZ6mJYw1H1oAKoJcnZLw10m6o5Y7O'
}

json_data = {
    'PSSH': 'AAAAOHBzc2gAAAAA7e+LqXnWSs6jyCfc1R0h7QAAABgSEDRuCjltu0wTvbccSsAj+XpI49yVmwY=',
    'License URL': "https://berriz.drmkeyserver.com/widevine_license",
    'Headers': "{'Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36'}",
    'JSON': "{}",
    "Cookies": "{}",
    'Data': "01O3rjPc2k2i1Je7CiPL0aKFZlxr1Rx9oCofu+m7vvggY1uqD3EhasDQRRvoTbFaLygQM2d+Emk1Xc/XCZGco7WXqBdVs01+plkj/+5rWH3758Cdtpfrr+1mvJaaDqFMIqDtMXkG77xuV30FtgY+ps8T+sL1tY4a5Ic0IGoHD7XI+zyOHsDkt7GaAnAOt7JiPJrBHUc4oLVLxDlQmPv/JsDcBsiPKQkbfVRJkN699erxQXWft8K/RoUQ38bX8b/9c2IeI/Tmb+FRgi+C73+6Vo9d+HkNxsYsbVpXCL3fucdVZ4Gcdv/suJHMPCDZ8FGxbP/pZbuuM3X/muWn3PJR6cvOSn4jBab5jsk56KdX4WbOhlGKisx+XWUSh+Olh3jzHF4oPvKiNDXGv1lRtHQRoMJP/4wjhRSbGsePdtb6TOA2JA/chH4Whfi5Lm4yV12tzo8hg5jFO+1A+5KYjohS04a14jOjHwyrguF0pR0tmhT1wuwygRF8LFU5EGX4MbxNyBsInrKItBwrqhSkiTqOysmOB1P0vudSSFjz5OFx/eaZIUUZg7ASiz2uss9DH2VUnI8pa0TzuXV53kCO0jv7OJHL4rMPvL0udpZ9t24L/V33vA5WD014/+AxxZmp8yK93mFnd5uH6XJ/+xfkfY5DJopVekUxokyYUYBy/ogyKIZEnBG8wx1DNi3evxY/p+QJgH2OEwtF+Y7zE7+YjF6hAs4HAxvGrVEgUlorJzAW15c3M1JDnN0CYMuCYAw87cBf4zLd6IVuETpldYTqdTcTaTka4KfNg40Vdce2Et5aiU8vOCMIg1amQRRFTlbvl0IlIY8w9aR4HHhDZUsJCSGQjZIE3zKtflG14pQ/6XnCC4iK1lyr28HSxeFXRBrxldX9tcHLtLNZrRwBJzfUW6GIuGCEMabKMRAvH7OJUl/aKRixloS+xM62VUQxeBbXx9aCldSZhLxdxlgxPpI5Wg5KANui2LFkN0uVK05XA2c9SaY=",
    'Proxy': ""
}

decryption_results = requests.post(API, json=json_data, headers=headers)

print(decryption_results.json()['Message']) 