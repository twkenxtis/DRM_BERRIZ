import asyncio
import sys
from datetime import datetime

from InquirerPy import inquirer

from static.color import Color
from static.api_error_handle import api_error_handle
from unit.community.community import get_community
from unit.http.request_berriz_api import Community
from unit.http.request_berriz_api import Arits
from unit.handle.handle_log import setup_logging
from unit.handle.handle_board_from import BoardMain, BoardNotice
from static.parameter import paramstore

from typing import Dict, Optional, Any, List, Tuple, Union


logger = setup_logging('artis_menu', 'ivory')


boardonly: Optional[bool] = paramstore.get('board')
noticeonly: Optional[bool] = paramstore.get('noticeonly')
        
        
class Board:
    def __init__(self, communityId: int, time_a: Optional[datetime] = None, time_b: Optional[datetime] = None) -> None:
        self.communityId: int = communityId
        self.json_data: Optional[Dict[str, Any]] = None
        self.time_a: Optional[datetime] = time_a
        self.time_b: Optional[datetime] = time_b

    async def match_noticeonly(self, choices: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
        match choices:
            case []:
                return {'type': 'board', 'iconType': 'artist', 'id': '', 'name': 'Unable to automatically select'}, []
            case _:
                selected_list = []
                selected: Optional[Dict[str, Any]] = None
                choices = [c for c in choices]
                filterchoice = [c for c in choices if c['value']['type'] != 'notice']
                if filterchoice != []:
                    selected_notice = self.selected_notice(choices)
                    if noticeonly is True and boardonly is False:
                        selected = selected_notice
                    elif noticeonly == boardonly:
                        selected_list.append(selected_notice)
                        try:
                            selected = await self.call_inquirer(filterchoice)
                            selected_list.append(selected)
                        except asyncio.TimeoutError:
                            selected = await self.call_auto_choese(choices)
                            selected_list.append(selected)
                    else:
                        # 'board only'
                        try:
                            selected = await self.call_inquirer(filterchoice)
                        except asyncio.TimeoutError:
                            selected = await self.call_auto_choese(choices)
                    return selected, selected_list
                else:
                    return {'type': 'board', 'iconType': 'artist', 'id': '', 'name': 'Unable to automatically select'}, [] 
    
    async def call_inquirer(self, filterchoice: List[Dict]) -> Dict:
        return await asyncio.wait_for(
            inquirer.select(
                message="Please select a project: (After 7s auto choese default Options)",
                choices=filterchoice
            ).execute_async(),
            timeout=7
        )
        
    async def call_auto_choese(self, choices: List[Dict]) -> Dict:
        for value in choices:
            if value['value']['iconType'] == 'artist':
                logger.info(
                    f"{Color.fg('light_gray')}Auto-selecting default Options "
                    f"{Color.fg('light_blue')}{value['value']['name']}{Color.reset()}"
                )
                selected = value['value']
                return selected
        # 如我迴圈沒有符合條件返回模板預設
        return {'type': 'board', 'iconType': 'artist', 'id': '', 'name': 'Unable to automatically select'}

    def selected_notice(self, choices: List[Dict]) -> Dict:
        for value in choices:
            if "notice" in value["value"]['type'].lower():
                selected_notice = value['value']
                return selected_notice

    def make_choice(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {"name": f"{idx}. {i['name']}", "value": i}
            for idx, i in enumerate(data.get("data", {}).get("menus", []))
            if i["name"] not in ("MEDIA", "LIVE", "Media")
        ]

    async def get_artis_board_list(self) -> Optional[Tuple[Any, str]]:
        CM_id: Union[int, str]
        group_name: str
        CM_id, group_name = await self.get_community_id(self.communityId)
        
        # Community().community_menus 回傳 Optional[Dict[str, Any]]
        community_menu: Optional[Dict[str, Any]] = await Community().community_menus(CM_id) 
        
        if community_menu is None or community_menu.get('code') != '0000':
            return None
        selected, selected_list = await self.match_noticeonly(self.make_choice(community_menu))
        if selected is None:
            return None # 如果沒有選擇，提前返回
        
        _type: str
        iconType: str
        _id: Union[int, str]
        name: str
        _type, iconType, _id, name = self.parse_user_select(selected)
        selected_list: List[Dict[str:Any]]
        if len(selected_list) > 0:
            result: Any = await self.handle_artist_board(selected, CM_id)
            result_notice: Any = await self.handle_artist_notice(selected_list[0], CM_id)
            data = [result, result_notice]
            return (data, 'notice+board')
        if iconType in('artist', 'user', 'artist-fanclub', 'user-fanclub', 'shop', 'live', 'media'):
            result: Any = await self.handle_artist_board(selected, CM_id)
            return (result, 'artist')
        if iconType == 'notice':
            result: Any = await self.handle_artist_notice(selected, CM_id)
            return (result, 'notice')
        else:
            logger.warning(
                f"Fail to parse {Color.bg('magenta')}{iconType}"
                f"{Color.reset()}{Color.fg('light_gray')}  {selected}"
                           )
            sys.exit(1)

    def parse_user_select(self, selected: Dict[str, Any]) -> Tuple[str, str, Union[int, str], str]:
        _type: str = selected['type']
        iconType: str = selected['iconType']
        _id: Union[int, str] = selected['id']
        name: str = selected['name']
        return _type, iconType, _id, name

    async def handle_artist_board(self, menu: Dict[str, Any], CM_id: Union[int, str]) -> Optional[Any]:
        board_list: Optional[List[Dict[str, Any]]] = await self.sort_board_list(menu, CM_id)
        return await BoardMain(board_list, self.time_a, self.time_b).main()
    
    async def handle_artist_notice(self, menu: Dict[str, Any], CM_id: Union[int, str]) -> Optional[Any]:
        board_list: Optional[List[Dict[str, Any]]] = await self.sort_board_list(menu, CM_id)
        return await BoardNotice(board_list, CM_id, self.time_a, self.time_b).notice_list()
    
    async def get_community_id(self, group_name: Union[int, str]) -> Tuple[int, str]:
        group_id: int
        _group_name: str
        if isinstance(group_name, int):
            group_id = group_name
            _group_name = await get_community(group_id) 
            return group_id, _group_name
        else:
            group_id = await get_community(group_name)
            return group_id, group_name

    async def sort_board_list(self, data: Dict[str, Any], community_id: Union[int, str]) -> Optional[List[Dict[str, Any]]]:
        boards_id: Union[int, str] = data.get('id', '')
        boards_name: Union[int, str] = data.get('name', '')
        if data.get('type') in('board', 'shop', 'live', 'media'):
            return await self.get_all_board_content_lists(str(boards_id), int(community_id), str(boards_name))
        elif data.get('type') == 'notice':
            return await Notice(int(community_id)).get_all_notice_content_lists()
        return None
        
    def basic_sort_json(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any], bool]:
        if not self.json_data or self.json_data.get('code') != '0000':
            return [], {}, False
        
        data: Dict[str, Any] = self.json_data.get('data', {})
        cursor: Optional[Dict[str, Any]] = data.get('cursor')
        hasNext: bool = data.get('hasNext', False)
        contents: List[Dict[str, Any]] = data.get('contents', [])
        params: Dict[str, Any] = self.build_params(cursor)
        
        return contents, params, hasNext
        
    def build_params(self, cursor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        params: Dict[str, Any] = {"pageSize": 100, "languageCode": "en"}
        if cursor and 'next' in cursor:
            params["next"] = cursor['next']
        return params
    
    async def get_all_board_content_lists(self, boards_id: str, community_id: int, boards_name: str) -> List[Dict[str, Any]]:
        all_contents: List[Dict[str, Any]] = []
        next_int: Optional[int] = 0
        hasNext: bool = True
        
        # 初始請求
        params: Dict[str, Union[str, int]] = {"pageSize": 100, "languageCode": "en"}
        self.json_data = await self._fetch_board_data(boards_id, community_id, params)
        contents: List[Dict[str, Any]]
        contents, _, hasNext = self.basic_sort_json()
        all_contents.extend(contents)
        
        try:
            if self.json_data['code'] != '0000':
                logger.warning(
                    f"Fail to get 【{Color.fg('light_yellow')}{boards_name}"
                    f"{Color.fg('gold')}】 {api_error_handle(self.json_data['code'])}"
                )
                return []
        except KeyError:
            logger.warning(
                f"Fail to get 【{Color.fg('light_yellow')}{boards_name}"
                f"{Color.fg('gold')}】"
            )
            pass
        
        if not hasNext:
            return self.deduplicate_contents(all_contents)
        # 取得初始 next_int
        cursor: Dict[str, Any] = self.json_data.get('data', {}).get('cursor', {})
        next_int = cursor.get('next', 0)

        # 單筆擴展，每次用回應的指針
        while hasNext and next_int is not None:
            params = {"pageSize": 100, "languageCode": "en", "next": next_int}
            result: Optional[Dict[str, Any]] = await self._fetch_board_data(boards_id, community_id, params)
            if result is None:
                break
            
            self.json_data = result
            page_contents: List[Dict[str, Any]]
            page_contents, _, hasNext = self.basic_sort_json()

            actual_cursor: Dict[str, Any] = result.get('data', {}).get('cursor', {})
            actual_next: Optional[int] = actual_cursor.get('next', None)
            
            if page_contents:
                all_contents.extend(page_contents)
            
            if actual_next:
                next_int = actual_next
            else:
                hasNext = False
                
        return self.deduplicate_contents(all_contents)


    def deduplicate_contents(self, contents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set = set()
        deduped: List[Dict[str, Any]] = []
        for item in contents:
            post: Dict[str, Any] = item.get('post', {})
            post_id: Optional[Union[str, int]] = post.get('postId')
            if post_id is not None and post_id not in seen:
                seen.add(post_id)
                deduped.append(item)
        return deduped

    async def _fetch_board_data(self, boards_id: str, community_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        data: Optional[Dict[str, Any]] = await Arits()._board_list(boards_id, str(community_id), params)
        return data if data is not None else {} # 處理 _board_list 可能回傳 None 的情況


class Notice(Board):
    def __init__(self, communityId: int) -> None:
        self.communityId: int = communityId
        super().__init__(self.communityId)
    
    async def fetch_notice_content_lists(self, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return await Arits().request_notice(self.communityId, params)

    async def get_all_notice_content_lists(self) -> List[Dict[str, Any]]:
        params: Dict[str, Union[str, int]] = {'languageCode': 'en', 'pageSize': 999999999339134974}
        all_contents: List[Dict[str, Any]] = []
        hasNext: bool = True
        next_int: Optional[int] = 0

        # 初始請求
        result: Optional[Dict[str, Any]] = await self.fetch_notice_content_lists(params)
        
        if result is None:
            return all_contents
            
        self.json_data = result
        contents: List[Dict[str, Any]]
        contents, _, hasNext = self.basic_sort_json()
        all_contents.extend(contents)

        if not hasNext:
            return all_contents

        # 取得初始 next_int
        cursor: Dict[str, Any] = self.json_data.get('data', {}).get('cursor', {})
        next_int = cursor.get('next', 0)

        # 單筆擴展，每次用回應的指針
        while hasNext and next_int is not None:
            params = {"pageSize": 999999999339134974, "languageCode": "en", "next": next_int}
            result = await self.fetch_notice_content_lists(params)
            
            if result is None:
                break
                
            self.json_data = result
            page_contents: List[Dict[str, Any]]
            page_contents, _, hasNext = self.basic_sort_json()

            actual_cursor: Dict[str, Any] = result.get('data', {}).get('cursor', {})
            actual_next: Optional[int] = actual_cursor.get('next', None)
            
            if page_contents:
                all_contents.extend(page_contents)
            
            if actual_next:
                next_int = actual_next
            else:
                hasNext = False
                
        return all_contents