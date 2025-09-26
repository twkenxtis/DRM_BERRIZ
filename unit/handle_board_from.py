import asyncio

from static.Board_from import Board_from
from static.color import Color
from unit.handle_log import setup_logging
from unit.community import get_community
from unit.http.request_berriz_api import Translate

from datetime import datetime
import pytz
import orjson

from typing import Dict, List, Optional, Union, Any, Tuple


class DataFormatter:
    def format_time_for_seoul(iso_timestamp):
        seoul_timezone = pytz.timezone('Asia/Seoul')
        utc_time = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        seoul_time = utc_time.astimezone(seoul_timezone)
        return seoul_time.strftime('%Y%m%d %H-%M')
    

class BoardFetcher:
    def __init__(self, index: Dict):
        self.json_data = None
        self.fetcher = Board_from(index)
        
    def get_postid(self):
        return self.fetcher.post_id
    
    def get_community_id(self):
        return self.fetcher.post_community_id
    
    def get_title(self):
        return self.fetcher.title
    
    def get_plainbody(self):
        return self.fetcher.plain_body

    def get_createdAt(self):
        return self.fetcher.created_at

    def get_updatedAt(self):
        return self.fetcher.updated_at

    def get_links(self):
        return self.fetcher.links

    def get_photos(self):
        media_ids = []
        image_urls = []
        dimensions = []
        published_dates = []
        for p in self.fetcher.photos:
            if not isinstance(p, dict):
                continue
            media_ids.append(p.get("media_id"))
            image_urls.append(p.get("image_url"))
            dimensions.append((p.get("width"), p.get("height")))
            published_dates.append(p.get("published_at"))

        return media_ids, image_urls, dimensions, published_dates

    def get_analysis(self):
        return self.fetcher.analyses

    def get_hashtags(self):
        return self.fetcher.hashtags

    def get_writer_user_id(self):
        return self.fetcher.writer_user_id

    def get_writer_community_id(self):
        return self.fetcher.writer_community_id

    def get_writer_type(self):
        return self.fetcher.writer_type

    def get_writer_name(self):
        return self.fetcher.writer_name

    def get_board_id(self):
        return self.fetcher.board_id

    def get_board_name(self):
        return self.fetcher.board_name

    def get_board_is_fanclub_only(self):
        return self.fetcher.board_is_fanclub_only

    def get_board_community_id(self):
        return self.fetcher.board_community_id


class BoardMain:
    def __init__(self, board_list: List[Dict]):
        self.translate = Translate()
        self.board_list = board_list
        self.boardfetcher = BoardFetcher
        self.time_formatter = DataFormatter.format_time_for_seoul

    async def main(self):
        task = []
        for index in self.board_list:
            fetcher = self.boardfetcher(index)

            postid = fetcher.get_postid()
            image_info = fetcher.get_photos()
            community_id = fetcher.get_board_community_id()
            writer_name = fetcher.get_writer_name()
            board_name = fetcher.get_board_name()
            fanclub_only = fetcher.get_board_is_fanclub_only()
            ISO8601 = fetcher.get_createdAt()
            title = fetcher.get_plainbody()[:20].replace('\n', ' ').replace('\r', ' ').strip()
            mediaid = image_info[0]

            folder_name, formact_time_str = self.get_folder_name(
                writer_name, board_name, ISO8601, postid
            )

            community_name = await self.fetch_community_name(community_id)

            #json_data = await self.build_translated_json(index, postid)
            return_data = [
                {
                'publishedAt':ISO8601, 'title':title, 'mediaType':'POST',
                'communityId':community_id, 'isFanclubOnly':fanclub_only,
                'communityName':community_name, 'folderName':folder_name,
                'timeStr':formact_time_str, 'postId':postid, 'imageInfo':image_info,
                "mediaId":mediaid
                }
            ]
            task.append(return_data)
        return_data = [item for sublist in task for item in sublist]
        return return_data

    async def build_translated_json(self, index, postid: str) -> str:
        translations = await self.fetch_translations(postid)

        eng = translations.get("en")
        zhHant = translations.get("zh-Hant")
        zhHans = translations.get("zh-Hans")

        return self.get_json_formact(index, eng, zhHant, zhHans)

    async def fetch_translations(self, postid: str) -> dict:
        async with asyncio.TaskGroup() as tg:
            t_en = tg.create_task(self.translate.translate_post(postid, "en"))
            t_zhHant = tg.create_task(self.translate.translate_post(postid, "zh-Hant"))
            t_zhHans = tg.create_task(self.translate.translate_post(postid, "zh-Hans"))

        return {
            "en": t_en.result(),
            "zh-Hant": t_zhHant.result(),
            "zh-Hans": t_zhHans.result(),
        }

    async def fetch_community_name(self, community_id: int) -> str:
        return await self.get_commnity_name(community_id)
            
    def get_folder_name(self, writer_name:str, board_name:str, ISO8601:str, postid:str) -> str:
        formact_time_str = self.time_formatter(ISO8601)
        title = f"{formact_time_str} {board_name} {writer_name} {postid}"
        return title, formact_time_str
    
    async def get_commnity_name(self, community_id:int) -> str:
        group_name = await get_community(community_id)
        return group_name
    
    def get_json_formact(self, index, eng: str, zhHant: str, zhHans: str) -> str:
        payload = {
            "index": index,
            "translations": {
                "en": eng,
                "zh-Hant": zhHant,
                "zh-Hans": zhHans,
            }
        }
        return orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode()
