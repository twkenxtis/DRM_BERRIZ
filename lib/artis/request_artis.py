import orjson
from pathlib import Path
from typing import Dict, Union, List, Optional

import aiofiles

from unit.http.request_berriz_api import Arits
from unit.handle.handle_log import setup_logging
from static.color import Color

logger = setup_logging('request_artis', 'lemon')

AritsDict = Dict[str, Union[int, str]]

BASE_ARTIS_KEY_DICT = Path('static') / 'artis_keys.json'

class ArtisDict:
    def __init__(self):
        pass
    
    async def file_check(self) -> None:
        """確保 JSON 檔案存在，如果不存在則建立它"""
        if not BASE_ARTIS_KEY_DICT.exists():
            async with aiofiles.open(BASE_ARTIS_KEY_DICT, 'w') as f:
                await f.write(orjson.dumps([]).decode('utf-8'))

    @staticmethod
    def search_artis(contents: List[AritsDict], query: Union[str, int, None]) -> Union[str, int, None]:
        """在提供的內容中透過查詢條件 (communityId 或 communityKey) 搜尋藝術家"""
        if query is None:
            return None
        query = int(query) if isinstance(query, str) and query.isdigit() else query
        logger.debug(f"{Color.fg('gold')}search_artis {query}, {type(query)}{Color.reset()}")
        if isinstance(query, str):
            q = query.strip().lower()
            for item in contents:
                key = item.get("name", "").lower()
                if q == key:
                    return item.get("communityId")
        elif isinstance(query, int):
            for item in contents:
                if item.get("communityId") == query:
                    return item.get("name")
        return None

    async def get_community(self, community_id: int, query: Union[str, int, None] = None) -> Dict:
        """取得社群藝術家資料，先從本地 JSON 嘗試，如果需要則從 API 取得"""
        await self.file_check()
        try:
            async with aiofiles.open(BASE_ARTIS_KEY_DICT, 'rb') as f:
                contents = orjson.loads(await f.read())
        except (orjson.JSONDecodeError, FileNotFoundError):
            contents = []
        # 如果提供了查詢條件，先在本機搜尋
        if query is not None:
            result = self.search_artis(contents, query)
            if result is not None:
                logger.debug(f"在本地 JSON 中找到結果: {result}")
                # 如果查詢的是 communityKey，回傳對應的 communityId
                if isinstance(query, str):
                    return {"data": {"communityArtists": [item for item in contents if item.get("communityId") == result]}}
                # 如果查詢的是 communityId，繼續使用 community_id

        # 如果沒有查詢條件或找不到結果，從 API 取得
        try:
            artis_json = await Arits().artis_list(community_id)
            if artis_json.get('code') != '0000':
                logger.warning(
                    f"取得【{Color.fg('light_yellow')}社群 id: {community_id} 藝術家列表{Color.fg('gold')}】資料失敗"
                )
                return {}
        except AttributeError:
            logger.warning(
                f"取得【{Color.fg('light_yellow')}社群 id: {community_id} 藝術家列表{Color.fg('gold')}】資料失敗"
            )
            return {}
        
        async with aiofiles.open(BASE_ARTIS_KEY_DICT, 'rb') as f:
            old_bytes = await f.read()
        old_items = orjson.loads(old_bytes)
        old_items.extend(contents)
        async with aiofiles.open(BASE_ARTIS_KEY_DICT, 'wb') as f:
            await f.write(orjson.dumps(old_items, option=orjson.OPT_INDENT_2))
        return artis_json

class JSON_Artis:
    def __init__(self, artis_json: Dict):
        self.artists: List[Dict] = []
        self.mapping_id_to_name: Dict[int, str] = {}
        self.mapping_name_to_id: Dict[str, int] = {}

        for data in artis_json.get('data', {}).get('communityArtists', []):
            artist_obj = {
                "communityArtistId": data.get("communityArtistId"),
                "communityId": data.get("communityId"),
                "artistId": data.get("artistId"),
                "userId": data.get("userId"),
                "name": data.get("name"),
                "tags": data.get("tags"),
                "imageUrl": data.get("imageUrl"),
                "pcImageUrl": data.get("pcImageUrl"),
                "description": data.get("description"),
                "displayOrder": data.get("displayOrder"),
            }
            self.artists.append(artist_obj)

            artist_id = artist_obj["artistId"]
            name = artist_obj["name"]
            if artist_id is not None and name is not None:
                self.mapping_id_to_name[artist_id] = name
                self.mapping_name_to_id[name] = artist_id

    def lookup(self, key: Union[int, str]) -> Union[int, str, None]:
        if isinstance(key, int):
            return self.mapping_id_to_name.get(key)
        elif isinstance(key, str):
            return self.mapping_name_to_id.get(key)
        return None

    def all(self) -> List[Dict]:
        return self.artists

    def all_sorted_by_display_order(self) -> List[Dict]:
        return sorted(
            self.artists,
            key=lambda a: (a.get("displayOrder") is None, a.get("displayOrder"))
        )

    def get_image_url(self, key: Union[int, str]) -> Optional[str]:
        """透過 artistId 或名稱回傳藝術家的 imageUrl"""
        target_id: Optional[int] = None

        if isinstance(key, int):
            target_id = key
        elif isinstance(key, str):
            target_id = self.mapping_name_to_id.get(key)

        if target_id is None:
            return None

        for artist in self.artists:
            if artist.get("artistId") == target_id:
                return artist.get("imageUrl")
        return None

class ArtisManger:
    def __init__(self, community_id: int):
        self.community_id = community_id
        self.json_data: Optional[Dict] = None
        self._mapper: Optional[JSON_Artis] = None
        self.artis_dict = ArtisDict()

    async def get_community_artis_list(self, query: Union[str, int, None] = None) -> Dict:
        """取得藝術家列表，優先透過 ArtisDict 從本地 JSON 取得"""
        try:
            artis_json = await self.artis_dict.get_community(self.community_id, query)
        except Exception as e:
            logger.warning(
                f"GET【{Color.fg('light_yellow')}community id: {self.community_id} Artis List{Color.fg('gold')}】fail: {e}"
            )
            return {}
        return artis_json

    async def artis(self, key: Union[int, str]) -> Union[int, str, None]:
        """回傳單一值: int→名稱; str→artistId"""
        if self._mapper is None:
            artis_json = await self.get_community_artis_list(key)
            self._mapper = JSON_Artis(artis_json)
        return self._mapper.lookup(key)

    async def get_artis_avatar(self, key: Union[int, str]) -> Optional[str]:
        """透過 artistId 或名稱取得藝術家頭像 URL"""
        artis_json = await self.get_community_artis_list(key)
        avatar_link = JSON_Artis(artis_json).get_image_url(key)
        return avatar_link