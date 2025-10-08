import asyncio

from datetime import datetime

from typing import Dict, List, Optional, Tuple, Any

from static.Board_from import Board_from
from static.Notice import Notice, Notice_info
from lib.load_yaml_config import CFG
from lib.__init__ import OutputFormatter, FilenameSanitizer, use_proxy
from unit.data.data import get_timestamp_formact, get_formatted_publish_date
from unit.handle.handle_log import setup_logging
from unit.community.community import get_community, custom_dict
from unit.http.request_berriz_api import Arits, Translate


logger = setup_logging('handle_board_from', 'midnight_blue')


class BoardFetcher:
    def __init__(self, index: Dict[str, Any]):
        self.json_data: Optional[Dict[str, Any]] = None
        self.fetcher: Any = Board_from(index)
        
    def get_postid(self) -> Any:
        return self.fetcher.post_id
    
    def get_community_id(self) -> Any:
        return self.fetcher.post_community_id
    
    def get_title(self) -> str:
        return self.fetcher.title
    
    def get_plainbody(self) -> str:
        return self.fetcher.plain_body

    def get_createdAt(self) -> str:
        return self.fetcher.created_at

    def get_updatedAt(self) -> str:
        return self.fetcher.updated_at

    def get_links(self) -> Any:
        return self.fetcher.links

    def get_photos(self) -> Tuple[List[Optional[str]], List[Optional[str]], List[Tuple[Optional[int], Optional[int]]], List[Optional[str]]]:
        media_ids: List[Optional[str]] = []
        image_urls: List[Optional[str]] = []
        dimensions: List[Tuple[Optional[int], Optional[int]]] = []
        published_dates: List[Optional[str]] = []
        for p in self.fetcher.photos:
            if not isinstance(p, dict):
                continue
            media_ids.append(p.get("media_id"))
            image_urls.append(p.get("image_url"))
            dimensions.append((p.get("width"), p.get("height")))
            published_dates.append(p.get("published_at"))

        return media_ids, image_urls, dimensions, published_dates

    def get_analysis(self) -> Any:
        return self.fetcher.analyses

    def get_hashtags(self) -> Any:
        return self.fetcher.hashtags

    def get_writer_user_id(self) -> Any:
        return self.fetcher.writer_user_id

    def get_writer_community_id(self) -> Any:
        return self.fetcher.writer_community_id

    def get_writer_type(self) -> Any:
        return self.fetcher.writer_type

    def get_writer_name(self) -> str:
        return self.fetcher.writer_name

    def get_board_id(self) -> Any:
        return self.fetcher.board_id

    def get_board_name(self) -> str:
        return self.fetcher.board_name

    def get_board_is_fanclub_only(self) -> bool:
        return self.fetcher.board_is_fanclub_only

    def get_board_community_id(self) -> Any:
        return self.fetcher.board_community_id


class NoticeFetcher:
    def __init__(self, index: Dict[str, Any]):
        self.json_data: Optional[Dict[str, Any]] = None
        self.fetcher: Any = Notice(index)
        
    def get_code(self) -> str:
        return self.fetcher.code

    def get_message(self) -> str:
        return self.fetcher.message

    def get_cursor_next(self) -> Any:
        return self.fetcher.cursor_next

    def get_has_next(self) -> bool:
        return self.fetcher.has_next

    def get_notices(self) -> Any:
        return self.fetcher.notices


class NoticeINFOFetcher:
    def __init__(self, index: Dict[str, Any]):
        self.fetcher_info: Any = Notice_info(index)

    def get_communityNoticeId(self) -> int:
        return self.fetcher_info.communityNoticeId
    
    def get_title(self) -> str:
        return self.fetcher_info.title
    
    def get_body(self) -> str:
        return self.fetcher_info.body
    
    def get_eventId(self) -> Optional[int]:
        return self.fetcher_info.eventId
    
    def get_reservedAt(self) -> str:
        return self.fetcher_info.reservedAt


class BoardMain:
    def __init__(self, board_list: List[Dict[str, Any]], time_a: Optional[datetime] = None, time_b: Optional[datetime] = None):
        self.board_list: List[Dict[str, Any]] = board_list
        self.boardfetcher: Any = BoardFetcher
        self.time_a: Optional[datetime] = time_a
        self.time_b: Optional[datetime] = time_b
        self.fm:str = get_timestamp_formact(CFG['Donwload_Dir_Name']['date_formact']) # %y%m%d_%H-%M
        self.FilenameSanitizer = FilenameSanitizer

    async def main(self) -> List[Dict[str, Any]]:
        task: List[List[Dict[str, Any]]] = []
        for index in self.sort_by_time():
            fetcher: BoardFetcher = self.boardfetcher(index)

            postid: Any = fetcher.get_postid()
            image_info: Tuple[List[Optional[str]], List[Optional[str]], List[Tuple[Optional[int], Optional[int]]], List[Optional[str]]] = fetcher.get_photos()
            community_id: Any = fetcher.get_board_community_id()
            writer_name: str = fetcher.get_writer_name()
            board_name: str = fetcher.get_board_name()
            fanclub_only: bool = fetcher.get_board_is_fanclub_only()
            ISO8601: str = fetcher.get_createdAt()
            title: str = fetcher.get_plainbody()[:45].replace('\n', ' ').replace('\r', ' ').strip()
            save_title = self.FilenameSanitizer.sanitize_filename(title)
            
            mediaid: List[Optional[str]] = image_info[0]
            folder_name, formact_time_str, video_meta = self.get_folder_name(fetcher, save_title, ISO8601, board_name, writer_name)
            community_name: str = await self.fetch_community_name(community_id)
            return_data: List[Dict[str, Any]] = [
                {
                    'publishedAt': ISO8601, 'title': save_title, 'mediaType': 'POST',
                    'communityId': community_id, 'isFanclubOnly': fanclub_only,
                    'communityName': community_name, 'folderName': folder_name,
                    'timeStr': formact_time_str, 'postId': postid, 'imageInfo': image_info,
                    "mediaId": mediaid, 'board_name': board_name, 'writer_name': writer_name,
                    'index': index, 'fetcher': fetcher, 'video_meta': video_meta,
                }
            ]
            task.append(return_data)
        return_data: List[Dict[str, Any]] = [item for sublist in task for item in sublist]
        return return_data

    def sort_by_time(self) -> List[Dict[str, Any]]:
        sort_list: List[Dict[str, Any]] = []
        
        should_filter_by_time: bool = (isinstance(self.time_a, datetime) and isinstance(self.time_b, datetime))

        for index in self.board_list:
            fetcher: BoardFetcher = self.boardfetcher(index)
            
            ISO8601: str = fetcher.get_createdAt()
            if should_filter_by_time and ISO8601:
                try:
                    published_at: datetime = datetime.fromisoformat(ISO8601.replace('Z', '+00:00'))
                    if not (self.time_a <= published_at <= self.time_b):
                        continue
                except (ValueError, TypeError):
                    continue
            sort_list.append(index)
        return sort_list

    async def fetch_community_name(self, community_id: int) -> str:
        return await self.get_commnity_name(community_id)
            
    def get_folder_name(self, fetcher: BoardFetcher, title: str, ISO8601: str, board_name: str, writer_name: str) -> Tuple[str, str]:
        formact_ISO8601:str = get_formatted_publish_date(ISO8601, self.fm)
        dt: datetime = datetime.strptime(formact_ISO8601, self.fm)
        d:str = dt.strftime(self.fm)
        safe_title: str = FilenameSanitizer.sanitize_filename(title)
        video_meta: Dict[str, str] = {
            "date": d,
            "title": safe_title,
            "community_name": board_name,
            "artis": writer_name,
            "source": "Berriz",
            "tag": CFG['output_template']['tag']
        }
        folder_name: str = OutputFormatter(f"{CFG['Donwload_Dir_Name']['dir_name']}").format(video_meta)
        return folder_name, d, video_meta
    
    async def get_commnity_name(self, community_id: int) -> str:
        group_name: str = await get_community(community_id)
        return group_name


class BoardNotice(BoardMain):
    def __init__(self, notice_list: List[Dict[str, Any]], Community_id: int, time_a: Optional[datetime] = None, time_b: Optional[datetime] = None):
        super().__init__(notice_list, time_a, time_b)
        self.notice: List[Dict[str, Any]] = notice_list
        self.noticefetcher: Any = NoticeFetcher
        self.community_id: int = Community_id
        self.FilenameSanitizer = FilenameSanitizer

    def sort_by_time(self) -> List[Dict[str, Any]]:
        sort_list: List[Dict[str, Any]] = []
        should_filter_by_time: bool = (isinstance(self.time_a, datetime) and isinstance(self.time_b, datetime))
        for index in self.notice:
            ISO8601 = index.get('reservedAt')
            if should_filter_by_time and ISO8601:
                try:
                    published_at: datetime = datetime.fromisoformat(ISO8601.replace('Z', '+00:00'))
                    if not (self.time_a <= published_at <= self.time_b):
                        continue
                except (ValueError, TypeError):
                    continue
            sort_list.append(index)
        return sort_list

    async def notice_list(self) -> List[Dict[str, Any]]:
        notices: List[Dict[str, Any]] = self.sort_by_time()
        return_data: List[Dict[str, Any]] = [
            {
                "publishedAt": n["reservedAt"],
                "title": self.FilenameSanitizer.sanitize_filename(n["title"]),
                "mediaType": "NOTICE",
                "communityId": self.community_id,
                "isFanclubOnly": False,
                "mediaId": n["communityNoticeId"],
                "index": idx,
            }
            for idx, n in enumerate(notices)
        ]
        return return_data


class BoardNoticeINFO(BoardMain):
    def __init__(self, notice_list: Dict[str, Any], time_a: Optional[datetime] = None, time_b: Optional[datetime] = None):
        super().__init__(notice_list, time_a, time_b)
        self.notice: Dict[str, Any] = notice_list
        self.noticefetcher: Any = NoticeFetcher
        self.noticeinfofetcher: Any = NoticeINFOFetcher
        self.Artis: classmethod = Arits()
        self.FilenameSanitizer = FilenameSanitizer

    async def call_notice_page(self, communityNoticeId: int, communityId: int, retry: int = 3) -> Optional[Dict[str, Any]]:
        for _ in range(retry):
            if (data := await self.Artis.request_notice_page(communityId, communityNoticeId, use_proxy)) and data.get('code') == '0000':
                return data
        return None

    async def request_notice_info(self, communityNoticeId: int, communityId: int) -> Any:
        return await self.main(communityId, await self.call_notice_page(communityNoticeId, communityId))

    def get_folder_name(self, fetcher: BoardFetcher, title: str, ISO8601: str, custom_community_name: str) -> Tuple[str, str]:
        formact_ISO8601:str = get_formatted_publish_date(ISO8601, self.fm)
        dt: datetime = datetime.strptime(formact_ISO8601, self.fm)
        safe_title: str = self.FilenameSanitizer.sanitize_filename(title)
        d:str = dt.strftime(self.fm)
        video_meta: Dict[str, str] = {
            "date": d,
            "title": safe_title,
            "artis": 'NOTICE',
            "community_name": custom_community_name,
            "source": "Berriz",
            "tag": CFG['output_template']['tag']
        }
        folder_name: str = OutputFormatter(f"{CFG['Donwload_Dir_Name']['dir_name']}").format(video_meta)
        return folder_name, d, video_meta

    async def main(self, cid: int, data: Dict[str, Any]) -> Dict[str, Any]:
        fetcher: NoticeINFOFetcher = self.noticeinfofetcher(data)
        communityNoticeId: int = fetcher.get_communityNoticeId()
        title: str = fetcher.get_title()
        ISO8601: str = fetcher.get_reservedAt()
        body: str = fetcher.get_body()
        get_eventId: Optional[int] = fetcher.get_eventId()
        
        safe_title: str = FilenameSanitizer.sanitize_filename(title)
        community_name: str = await self.fetch_community_name(cid)
        custom_community_name: str = await custom_dict(community_name)
        community_id: int = await get_community(community_name)
        folder_name, formact_time_str, video_meta = self.get_folder_name(fetcher, safe_title, ISO8601, custom_community_name)
        return {
            'safe_title': safe_title, 'folderName': folder_name, 'formact_time_str': formact_time_str,
            'community_name': community_name,
            'custom_community_name': custom_community_name, 'communityId': community_id,
            'fetcher': fetcher, 'notice_list': self.notice, 'video_meta': video_meta
        }


class JsonBuilder:
    def __init__(self, index: Dict[str, Any], postid: str):
        self.translate: classmethod  = Translate()
        self.index: Dict[str, Any] = index
        self.postid: str = postid
        self.use_proxy: bool = use_proxy
    
    async def build_translated_json(self) -> Dict[str, Any]:
        translations: Dict[str, str] = await self.fetch_translations()

        eng: str = translations.get("en")
        jp: str = translations.get("jp")
        zhHant: str = translations.get("zh-Hant")
        zhHans: str = translations.get("zh-Hans")

        return self.get_json_formact(eng, jp, zhHant, zhHans)

    def get_json_formact(self, eng: str, jp: str, zhHant: str, zhHans: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "index": self.index,
            "translations": {
                "en": eng,
                "jp": jp,
                "zh-Hant": zhHant,
                "zh-Hans": zhHans,
            }
        }
        return payload
    
    async def fetch_translations(self) -> Dict[str, str]:
        tasks = [
            self.translate.translate_post(self.postid, "en", self.use_proxy),
            self.translate.translate_post(self.postid, "ja", self.use_proxy),
            self.translate.translate_post(self.postid, "zh-Hant", self.use_proxy),
            self.translate.translate_post(self.postid, "zh-Hans", self.use_proxy),
        ]

        try:
            results = await asyncio.gather(*tasks)
        except Exception as e:
            raise e 
        return {
            "en": results[0],
            "jp": results[1],
            "zh-Hant": results[2],
            "zh-Hans": results[3],
        }
