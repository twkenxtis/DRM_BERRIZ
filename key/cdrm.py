import logging
from typing import List

import httpx

from unit.handle_log import setup_logging


logger = setup_logging('cdrm', 'gray')


class CDRM:
    def __init__(self):
        pass

    def chosee_drm_service(self, pssh):
        if len(pssh) > 76:
            return 'playready_license'
        if len(pssh) == 76:
            return 'widevine_license'
        return None
        
        
    async def get_license_key(self, pssh: str, acquirelicenseassertion: str) -> List:
        if not pssh:
            logger.error("Invalid PSSH: No WRM headers found")
            return None
        drm_service = self.chosee_drm_service(pssh)

        async with httpx.AsyncClient(timeout=13.0, verify=True) as client:
            licurl =  f'https://berriz.drmkeyserver.com/{drm_service}'
            response = await client.post(
                url='https://cdrm-project.com/api/decrypt',
                headers={'Content-Type': 'application/json'},
                json={
                    'pssh': pssh,
                    'licurl': licurl,
                    'headers': str({
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; AFTKA) AppleWebKit/537.36 (KHTML, like Gecko) Silk/112.5.1 like Chrome/112.0.5615.213 Safari/537.36',
                        'acquirelicenseassertion': acquirelicenseassertion
                    })
                }
            )
            response.raise_for_status()
            key = []
            key.append(response.json()['message'].strip())
            return key