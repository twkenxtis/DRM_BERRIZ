import requests
import asyncio
import logging
from typing import Dict, Optional, Any, List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GetMediaList:
    def __init__(self):
        self.headers = self._build_headers()
        self.base_url = "https://svc-api.berriz.in/service/v1"
        self.delay = 1

    def _build_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': 'https://berriz.in/',
            'Origin': 'https://berriz.in',
            'Alt-Used': 'svc-api.berriz.in',
        }

    async def _fetch_page(self, community_id: int, cursor: Optional[str]) -> Optional[Dict[str, Any]]:
        params = {
            "pageSize": 20,
            "languageCode": "en"
        }
        if cursor:
            params["cursor"] = cursor

        url = f"{self.base_url}/community/{community_id}/mediaCategories/112/medias"
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Pagination request error: {e}")
            return None

    async def get_all_media_lists(self, community_id: int) -> Tuple[List[Dict], List[Dict]]:
        vod_list = []
        photo_list = []
        cursor = None

        while True:
            data = await self._fetch_page(community_id, cursor)
            
            if not data or data.get("code") != "0000":
                break

            for item in data.get("data", {}).get("contents", []):
                if media := item.get("media"):
                    media_type = media.get("mediaType")
                    if media_type == "VOD":
                        vod_list.append(media)
                    elif media_type == "PHOTO":
                        photo_list.append(media)

            if data.get("data", {}).get("hasNext"):
                cursor = data["data"]["cursor"]["next"]
                await asyncio.sleep(self.delay)
            else:
                break
        
        return vod_list, photo_list


async def main():
    media_fetcher = GetMediaList()
    community_id = 7
    
    logging.info("Starting to retrieve media list...")
    
    vod_list, photo_list = await media_fetcher.get_all_media_lists(community_id)
    
    print(f"\n--- Summary ---")
    print(f"A total of {len(vod_list)} VOD media items were found.")
    print(f"A total of {len(photo_list)} PHOTO media items were found.")
    return vod_list, photo_list


if __name__ == "__main__":
    vod_list, photo_list = asyncio.run(main())
    print(vod_list)
    print(photo_list)
