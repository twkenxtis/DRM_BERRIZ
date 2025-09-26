import asyncio

from static.color import Color
from unit.community import get_community
from unit.http.request_berriz_api import Community
from unit.http.request_berriz_api import Arits
from unit.handle_log import setup_logging
from unit.handle_board_from import BoardMain

from typing import Dict, List, Optional, Union, Any, Tuple


class Board:
    def __init__(self, communityId: int):
        self.communityId = communityId
        self.json_data = None

    async def get_artis_board_list(self):
        CM_id, group_name = await self.get_community_id(self.communityId)
        data = await Community().community_menus(CM_id)
        if data.get('code') != '0000':
            return None

        menus = data.get('data', {}).get('menus', [])
        for i in menus:
            if i.get('iconType') == 'artist':
                return await self.handle_artist_board(i, CM_id)

    async def handle_artist_board(self, menu, CM_id):
        board_list = await self.sort_board_list(menu, CM_id)
        if board_list:
            return await BoardMain(board_list).main()
    
    async def get_community_id(self, group_name):
        if isinstance(group_name, int):
            group_id = group_name
            group_name = await get_community(group_id)
            return group_id, group_name
        else:
            group_id = await get_community(group_name)
            return group_id, group_name
        
    async def sort_board_list(self, data:Dict, community_id:str):
        if data.get('type') != 'board':
            return None
        iconType = data.get('iconType')
        boards_id = data.get('id')
        boards_name = data.get('name')
        return await self.get_all_board_content_lists(boards_id, community_id)
        
    def basic_sort_josn(self):
        if not self.json_data or self.json_data.get('code') != '0000':
            return [], {}, False
        cursor = self.json_data.get('data').get('cursor')
        hasNext = self.json_data.get('data').get('hasNext')
        contents = self.json_data.get('data').get('contents')
        params = self.build_params(cursor)
        return contents, params, hasNext
        
    def build_params(self, cursor: Optional[str]) -> Dict[str, Any]:
        params = {"pageSize": 100, "languageCode": "en"}
        next_int = cursor['next']
        if cursor:
            params["next"] = next_int
        return params
    
    async def get_all_board_content_lists(self, boards_id, community_id):
        params = {"pageSize": 100, "languageCode": "en"}
        all_contents = []

        while True:
            self.json_data = await self._fetch_data(boards_id, community_id, params)
            if not self.json_data:
                break

            contents, params, hasNext = self.basic_sort_josn()
            all_contents.extend(contents)
            if hasNext is False:
                return all_contents

    async def _fetch_data(
        self, boards_id:str, community_id:int, params: dict,
    ) -> Tuple[dict, dict]:
        return await Arits()._board_list(boards_id, community_id, params)