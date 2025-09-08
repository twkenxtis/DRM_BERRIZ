import httpx
import json 
import logging


class Watora_wv:
    def __init__(self):
        self.remote_cdm_api_key = 'SHZ6mJYw1H1oAKoJcnZLw10m6o5Y7O'
        
    async def get_license_key(self, pssh, assertion):
        try:
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'en-US,en;q=0.9',
                'acquirelicenseassertion': assertion
            }
            json_data = {
                'PSSH': pssh,
                'License URL': "https://berriz.drmkeyserver.com/widevine_license",
                'Headers': json.dumps(headers),
                "Cookies": "{}",
                'Data': "{}",
                'Proxy': "",
                'JSON': {},
            }
            async with httpx.AsyncClient() as client:
                decryption_results = await client.post('https://cdm.watora.me', json=json_data, headers={"Authorization": f"Bearer {self.remote_cdm_api_key}"})
                decryption_results.raise_for_status()

            if decryption_results.status_code != 200:
                logging.error(f"Failed to get decryption results: {decryption_results.text}")
                return None
            keys = []
            keys.append(decryption_results.json().get('Message').strip())
            return keys
        except Exception as e:
            logging.error(e)
            return None