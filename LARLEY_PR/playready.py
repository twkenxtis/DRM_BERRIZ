import xml.etree.ElementTree as ET

import httpx

from unit.handle_log import setup_logging
from pyplayready.cdm import Cdm
from pyplayready.device import Device
from pyplayready.system.pssh import PSSH


logger = setup_logging('playready', 'graphite')


class PlayReadyDRM:
    def __init__(self, device_path: str):
        self.device = Device.load(device_path)
        self.cdm = Cdm.from_device(self.device)
        self.session_id = self.cdm.open()

    async def get_license_key(self, pssh: str, acquirelicenseassertion: str) -> str:
        try:
            pssh_obj = PSSH(pssh)
            if not pssh_obj.wrm_headers:
                logger.error("Invalid PSSH: No WRM headers found")
                return None
            if len(pssh) < 76:
                raise ValueError("Invalid PSSH: WRM header length is too short")

            challenge = self.cdm.get_license_challenge(self.session_id, pssh_obj.wrm_headers[0])

            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; AFTKA) AppleWebKit/537.36 (KHTML, like Gecko) Silk/112.5.1 like Chrome/112.0.5615.213 Safari/537.36',
                'Connection': 'Keep-Alive',
                'Content-Type': 'application/octet-stream',
                'acquirelicenseassertion': acquirelicenseassertion
            }

            async with httpx.AsyncClient(timeout=13.0, verify=True) as client:
                response = await client.post(
                    url="https://berriz.drmkeyserver.com/playready_license",
                    headers=headers,
                    data=challenge,
                )
                response.raise_for_status()

            self.cdm.parse_license(self.session_id, response.text)

            keys = self.cdm.get_keys(self.session_id)
            content_keys = []
            for key in keys:
                kid = key.key_id.hex() if isinstance(key.key_id, bytes) else str(key.key_id)
                kid = kid.replace('-', '')
                value = key.key.hex() if isinstance(key.key, bytes) else str(key.key)
                content_keys.append(f"{kid}:{value}")
            return content_keys

        except Exception as e:
            logger.error(e)

        finally:
            self.cdm.close(self.session_id)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cdm.close(self.session_id)