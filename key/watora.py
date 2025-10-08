import os
import json
from pathlib import Path
from typing import List, Optional, Any

from lib.__init__ import use_proxy
from dotenv import load_dotenv
from unit.http.request_berriz_api import GetPost

from unit.handle.handle_log import setup_logging


logger = setup_logging('watora', 'foggy')


ENV_PATH: str = Path(__file__).parent.parent.joinpath('static', '.env')
load_dotenv(dotenv_path=ENV_PATH)

try:
    watora_api = os.getenv('watora_api')
except Exception as e:
    logger.error(e)
    raise ValueError("watora_api Failed to load") from e


class Watora_wv:
    def __init__(self) -> None:
        self.remote_cdm_api_key: str = str(watora_api)
        
    async def get_license_key(self, pssh: str, assertion: str) -> Optional[List[str]]:
        """
        使用遠端 API 取得 Widevine license key

        :param pssh: Base64 編碼的 PSSH 資訊
        :param assertion: License assertion
        :return: 成功時返回包含 key 的 list，失敗返回 None
        """
        _headers: dict[str, str] = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'acquirelicenseassertion': assertion
        }
        json_data: dict[str, Any] = {
            'PSSH': pssh,
            'License URL': "https://berriz.drmkeyserver.com/widevine_license",
            'Headers': json.dumps(_headers),
            "Cookies": "{}",
            'Data': "{}",
            'Proxy': "",
            'JSON': {},
        }
        match len(self.remote_cdm_api_key):
            case 0:
                logger.error("Remote CDM API key is not set")
                return None
            case length if length >= 20:
                url = 'https://cdm.watora.me'
                headers={"Authorization": f"Bearer {self.remote_cdm_api_key}"}
                data = await GetPost().get_post(url, json_data, {}, headers, use_proxy)
                keys: List[str] = []
                keys.append(data.get('Message', '').strip())
                return keys
