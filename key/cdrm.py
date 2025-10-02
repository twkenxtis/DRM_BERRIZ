import logging
from typing import List, Optional

import httpx

from unit.handle_log import setup_logging


logger = setup_logging('cdrm', 'gray')


class CDRM:
    def __init__(self) -> None:
        pass

    def chosee_drm_service(self, pssh: str) -> Optional[str]:
        """根據 PSSH 長度選擇 DRM 服務"""
        if len(pssh) > 76:
            return 'playready_license'
        if len(pssh) == 76:
            return 'widevine_license'
        return None

    async def get_license_key(self, pssh: str, acquirelicenseassertion: str) -> Optional[List[str]]:
        """
        使用遠端 CDRM 服務取得 License Key

        :param pssh: Base64 編碼的 PSSH
        :param acquirelicenseassertion: License assertion
        :return: 成功返回包含 key 的 list，失敗返回 None
        """
        if not pssh:
            logger.error("Invalid PSSH: No WRM headers found")
            return None

        drm_service = self.chosee_drm_service(pssh)
        if not drm_service:
            logger.error("Unable to determine DRM service from PSSH")
            return None

        async with httpx.AsyncClient(timeout=13.0, verify=True, http2=False) as client:
            licurl = f'https://berriz.drmkeyserver.com/{drm_service}'
            response: httpx.Response = await client.post(
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

            key: List[str] = []
            key.append(response.json().get('message', '').strip())
            return key