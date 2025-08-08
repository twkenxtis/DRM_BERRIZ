import requests
from lxml import etree
import logging
from typing import Any, Dict, List, Optional, Union

from cookies import Refresh_JWT, Berriz_cookie

def extract_pssh(response: requests.Response) -> List[str]:
    try:
        namespaces = {
            'cenc': 'urn:mpeg:cenc:2013',
            'mspr': 'urn:microsoft:playready'
        }
        root = etree.fromstring(response.content)
        
        pssh_elements = root.xpath('//cenc:pssh', namespaces=namespaces)
        
        return [pssh.text.strip() for pssh in pssh_elements if pssh.text]
        
    except etree.XMLSyntaxError as e:
        logging.error(f"XML parsing error: {e}")
        return []
    except Exception as e:
        logging.error(f"Error during PSSH extraction: {e}")
        return []
    
class GetMPD:
    def __init__(self):
        Refresh_JWT.main()
        self.cookies = Berriz_cookie()._cookies        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en,zh-CN;q=0.8,ja;q=0.6,ko;q=0.4,zh-TW;q=0.2',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': 'https://berriz.in/',
            'Origin': 'https://berriz.in',
        }

    def send_request(self, mpd_url: str) -> Optional[requests.Response]:
        try:
            response = requests.get(
                mpd_url,
                cookies=self.cookies,
                headers=self.headers,
                timeout=7
            )
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching MPD: {e}")
            return None
        
    def parse_pssh(mpd_url):
        response = GetMPD().send_request(mpd_url)
        
        if not response:
            logging.error("Failed to retrieve the MPD file.")
            return None
        
        pssh_values = extract_pssh(response)
        
        if not pssh_values:
            logging.error("No PSSH values found in the MPD file.")
            return None
        
        for pssh in pssh_values:
            if len(pssh) > 76:
                return pssh
        
        logging.error("No PSSH value with exactly 76 characters found")
        return None