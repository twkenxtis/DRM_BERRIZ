import logging
import requests
import sys
import xml.etree.ElementTree as ET

from pyplayready.cdm import Cdm
from pyplayready.device import Device
from pyplayready.system.pssh import PSSH

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class PlayReadyDRM:
    def __init__(self, device_path: str):
        self.device = Device.load(device_path)
        self.cdm = Cdm.from_device(self.device)
        self.session_id = self.cdm.open()

    def get_license_key(self, pssh: str, acquirelicenseassertion: str, license_url: str = "https://berriz.drmkeyserver.com/playready_license") -> str:
        try:
            pssh_obj = PSSH(pssh)
            if not pssh_obj.wrm_headers:
                logging.error("Invalid PSSH: No WRM headers found")
                return None

            challenge = self.cdm.get_license_challenge(self.session_id, pssh_obj.wrm_headers[0])

            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-S911U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36',
                'Connection': 'Keep-Alive',
                'Content-Type': 'application/octet-stream',
                'acquirelicenseassertion': acquirelicenseassertion
            }

            response = requests.post(url=license_url, headers=headers, data=challenge)
            response.raise_for_status()

            self.cdm.parse_license(self.session_id, response.text)

            keys = self.cdm.get_keys(self.session_id)
            for key in keys:
                kid = key.key_id.hex() if isinstance(key.key_id, bytes) else str(key.key_id)
                kid = kid.replace('-', '')
                value = key.key.hex() if isinstance(key.key, bytes) else str(key.key)
                return f"{kid}:{value}"

        except Exception:
            logging.error("The acquirelicenseassertion Expired.")

        finally:
            self.cdm.close(self.session_id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cdm.close(self.session_id)