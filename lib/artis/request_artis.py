from typing import Dict, Union, List, Optional

from unit.http.request_berriz_api import Arits
from unit.handle_log import setup_logging
from static.color import Color

logger = setup_logging('request_artis', 'lemon')


class ArtisManger:
    def __init__(self, community_id: int):
        self.community_id = community_id
        self.json_data: Optional[Dict] = None
        self._mapper: Optional[JSON_Artis] = None  # cache

    async def get_community_artis_list(self) -> Dict:
        artis_json = await Arits().artis_list(self.community_id)
        if artis_json is None:
            logger.warning(
                f"Fail to get 【{Color.fg('light_yellow')}Community id: {self.community_id} Artis List{Color.fg('gold')}】data"
            )
            return {}
        try:
            if artis_json.get('code') != '0000':
                logger.warning(
                    f"Fail to get 【{Color.fg('light_yellow')}Community id: {self.community_id} Artis List{Color.fg('gold')}】data"
                )
        except KeyError as e:
            logger.warning(e)
        return artis_json

    async def artis(self, key: Union[int, str]) -> Union[int, str, None]:
        """依輸入回傳單一值：int→name；str→artistId"""
        if self._mapper is None:
            artis_json = await self.get_community_artis_list()
            self._mapper = JSON_Artis(artis_json)
        return self._mapper.lookup(key)
    
    async def get_artis_avatar(self, key: Union[int, str]) -> Optional[str]:
        artis_json = await self.get_community_artis_list()
        avatar_link = JSON_Artis(artis_json).get_image_url(key)
        return avatar_link


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
        """
        根據輸入 (artistId:int 或 name:str) 回傳對應藝人的 imageUrl
        找不到則回傳 None
        """
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