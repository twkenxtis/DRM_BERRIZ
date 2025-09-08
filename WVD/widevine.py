import httpx
import logging

from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class WidevineDRM:
    def __init__(self, device_path: str):
        self.device = Device.load(device_path)
        self.cdm = Cdm.from_device(self.device)
        self.session_id = self.cdm.open()
    
    async def get_license_key(self, pssh: str, acquirelicenseassertion: str) -> str:
        req_pssh = PSSH(pssh)
        if not pssh:
            logging.error("Invalid PSSH: No WRM headers found")
            return None
        if len(pssh) < 76:
            raise ValueError("Invalid PSSH: WRM header length is too short")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-S911U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36',
            'Connection': 'Keep-Alive',
            'Content-Type': 'application/octet-stream',
            'acquirelicenseassertion': acquirelicenseassertion
        }
        
        challenge = self.cdm.get_license_challenge(self.session_id, req_pssh)
        async with httpx.AsyncClient(timeout=13.0, verify=True) as client:
            response = await client.post(
                url="https://berriz.drmkeyserver.com/widevine_license",
                headers=headers,
                data=challenge,
            )
            response.raise_for_status()
        
        self.cdm.parse_license(self.session_id, response.content)
        
        content_keys = []
        for key in self.cdm.get_keys(self.session_id):
            if key.type == "CONTENT":
                kid = key.kid.hex if isinstance(key.kid.hex, bytes) else str(key.kid.hex)
                kid = kid.replace('-', '')
                value = key.key.hex() if isinstance(key.key, bytes) else str(key.key)
                content_keys.append(f"{kid}:{value}")

        self.cdm.close(self.session_id)
        return content_keys
