import asyncio
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from lib.lock_cookie import cookie_session
from mystate.fanclub import fanclub_main
from static.color import Color
from static.parameter import paramstore
from unit.handle.handle_log import setup_logging
from unit.http.request_berriz_api import Live, MediaList

MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]


logger = setup_logging('GetMediaList', 'turquoise')


class FanClubFilter:
    async def is_fanclub() -> Optional[Any]:
        if paramstore.get('no_cookie') is not True:
            context: Optional[Any] = await fanclub_main()
            """None - not fanclub"""
            match context:
                case 'NOFANCLUBINFO':
                    return 'NOFANCLUBINFO'
                case _:
                    return context


class MediaParser:
    def __init__(self, community_id: int, communityname: str, time_a: Optional[datetime], time_b: Optional[datetime]):
        self.community_id: int = community_id
        self.communityname: str = communityname
        self.time_a: Optional[datetime] = time_a
        self.time_b: Optional[datetime] = time_b
        self.fcinfo = None
    
    async def parse(self, _data: Dict[str, Any]) -> Tuple[List[Dict], List[Dict], List[Dict], Optional[str], bool]:
        # Fanclub 身份檢查
        FCINFO: Optional[Any] = await FanClubFilter.is_fanclub()
        self.fcinfo = FCINFO
        
        # Chunk 1: extract core
        contents, cursor, has_next = await self._extract_core(_data)
        if contents is None:
            return [], [], [], cursor, has_next
        # Chunk 2: parse three raw lists
        vods, photos, lives = self._extract_media_items(contents)
        # Chunk 3: concurrently split fanclub vs non-fanclub
        v_fc, v_nfc = self.fanclub_items(vods)
        l_fc, l_nfc = self.fanclub_items(lives)
        p_fc, p_nfc  = self.fanclub_items(photos)
        
        # Cookie 檢查：沒 cookie 則清空付費列表
        if cookie_session == {}:
            v_fc = p_fc = l_fc = []

        pref: Optional[bool] = paramstore.get("fanclub")
        if self.fcinfo == 'NOFANCLUBINFO' and pref in (None, False):
            # 非會員 → 回傳非付費
            return v_nfc, p_nfc, l_nfc, cursor, has_next
        elif pref is True:
            # --fanclub-only
            return v_fc, p_fc, l_fc, cursor, has_next
        elif pref is False:
            return v_nfc, p_nfc, l_nfc, cursor, has_next
        # 會員 fanclub only content + Normal none-fanclub content
        return v_fc+v_nfc, p_fc+p_nfc, l_fc+l_nfc, cursor, has_next

    async def _extract_core(self, _data: Dict[str, Any]) -> Tuple[Optional[List[Dict]], Optional[str], bool]:
        if not self._is_valid_response(_data):
            return None, None, False
        contents, (cursor, has_next) = await asyncio.gather(self._get_contents(_data), self._extract_pagination(_data))
        return contents, cursor, has_next

    async def parse_fanclub_community(self, contents: List[Dict]) -> List[Dict]:
        return [
            item for item in contents
            if item.get("media", {}).get("communityId") == self.community_id
            and item["media"].get("isFanclubOnly") is True
        ]

    def _is_valid_response(self, _data: Dict[str, Any]) -> bool:
        if _data is None:
            return False
        code: Optional[str] = _data.get("code")
        if code != "0000":
            logger.warning(f"API error: {code}")
            return False
        return True

    async def _get_contents(self, _data: Dict[str, Any]) -> List[Dict]:
        return _data.get("data", {}).get("contents", [])

    def _extract_media_items(
        self, contents: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        vod_list: List[Dict] = []
        photo_list: List[Dict] = []
        live_list: List[Dict] = []
        
        # 檢查是否需要進行時間篩選 -> bool
        should_filter_by_time: bool = (isinstance(self.time_a, datetime) and isinstance(self.time_b, datetime))

        for item in contents:
            media: Optional[Dict[str, Any]] = item.get("media")
            
            if not media:
                raise ValueError("The 'media' field is missing in the media item")
            
            published_at_str: Optional[str] = media.get("publishedAt")
            # 進行時間範圍篩選
            if should_filter_by_time and published_at_str:
                try:
                    # 將字串轉換為 datetime 物件，並處理時區
                    published_at: datetime = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
                    if not (self.time_a <= published_at <= self.time_b):
                        continue
                except (ValueError, TypeError):
                    continue
            match media.get("mediaType"):
                case "VOD":
                    vod_list.append(media)
                case "PHOTO":
                    photo_list.append(media)
                case "LIVE":
                    live_list.append(media)
        return vod_list, photo_list, live_list
    
    def fanclub_items(self, contents: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict]]:
        fanclub: List[Dict] = []
        not_fanclub: List[Dict] = []
        for item in contents:
            match item.get("isFanclubOnly"):
                case True:
                    fanclub.append(item)
                case False:
                    not_fanclub.append(item)
                case _:
                    not_fanclub.append(item)
        return fanclub, not_fanclub

    async def _extract_pagination(self, _data: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        pagination: Dict[str, Any] = _data.get("data", {})
        cursor: Optional[str] = pagination.get("cursor", {}).get("next")
        has_next: bool = pagination.get("hasNext", False)
        return cursor, has_next


class MediaFetcher:
    def __init__(self, community_id: int, communityname: str, time_a: Optional[datetime], time_b: Optional[datetime]):
        self.community_id: int = community_id
        self.communityname: str = communityname
        self.MP: MediaParser = MediaParser(community_id, communityname, time_a, time_b)

    async def get_all_media_lists(self) -> Tuple[List[Dict], List[Dict], List[Dict]] | bool:
        vod_total: List[Dict] = []
        photo_total: List[Dict] = []
        live_total: List[Dict] = []
        params: Dict[str, Any] = await self._build_params(cursor=None)

        while True:
            media_data , live_data = await self._fetch_data(params)
            
            if not (media_data or live_data):
                self.error_printer(media_data, live_data)
                break

            # 並行解析 + build params
            (vods, photos, params_media, has_next_media), \
            (lives, params_live, has_next_live) = await asyncio.gather(
                self._process_media_chunk(media_data),
                self._process_live_chunk(live_data),
            )

            vod_total  .extend(vods)
            photo_total.extend(photos)
            live_total .extend(lives)

            if not (has_next_media or has_next_live):
                break

            # 合併下一輪要用的 params
            params = {
                "media": params_media,
                "live":  params_live,
            }

        return vod_total, photo_total, live_total

    def error_printer(self, media_data: Dict[str, Any], live_data: Dict[str, Any]):
        if not media_data and live_data:
            M = 'Media data'
        elif not live_data and media_data:
            M = 'Live data'
        else:
            M = 'Media and Live data'
            logger.warning(
                f"Fail to get 【{Color.fg('light_yellow')}{M}"
                f"{Color.fg('gold')}】"
            )

    async def _fetch_data(
        self, params: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            async with asyncio.TaskGroup() as tg:
                media_task = tg.create_task(MediaList().media_list(self.community_id, params))
                live_task = tg.create_task(Live().fetch_live_replay(self.community_id, params))
            
            media_data = media_task.result()
            live_data = live_task.result()
            return media_data, live_data

    async def _process_media_chunk(
        self, media_data: Dict[str, Any]) -> Tuple[List[Dict], List[Dict], Dict[str, Any], bool]:
        vods, photos, _, cursor, has_next = await self.MP.parse(media_data)
        next_params: Dict[str, Any] = await self._build_params(cursor)
        return vods, photos, next_params, has_next

    async def _process_live_chunk(
        self, live_data: Dict[str, Any]) -> Tuple[List[Dict], Dict[str, Any], bool]:
        _, _, lives, cursor, has_next = await self.MP.parse(live_data)
        next_params: Dict[str, Any] = await self._build_params(cursor)
        return lives, next_params, has_next
    
    async def _build_params(self, cursor: Optional[str]) -> Dict[str, Any]:
        pagesize: int = random.randint(25000, 30000)
        params: Dict[str, Any] = {"pageSize": pagesize, "languageCode": "en"}
        if cursor:
            params["next"] = cursor
        return params