import sys
from datetime import datetime
from typing import NamedTuple
from typing import Optional, List, Dict, Any, Tuple, Callable

from lib.artis.artis_menu import Board
from lib.media_queue import MediaQueue
from mystate.parse_my import request_my
from static.parameter import paramstore
from static.color import Color
from unit.getall.GetMediaList import MediaFetcher
from unit.handle.handle_log import setup_logging
from unit.main_process import MediaProcessor
from unit.media.media_json_process import MediaJsonProcessor
from unit.user_choice import InquirerPySelector
from unit.getall.GetNotifyList import NotifyFetcher


logger = setup_logging('handle_choice', 'light_slate_gray')


# Get the parameter flags with default False
liveonly = paramstore.get('liveonly')
mediaonly = paramstore.get('mediaonly')
photoonly = paramstore.get('photoonly')
boardonly = paramstore.get('board')
noticeonly = paramstore.get('noticeonly')


active_conditions_1 = sum([
    bool(liveonly),
    bool(mediaonly),
    bool(photoonly),
])


active_conditions_2 = sum([
    bool(boardonly),
    bool(noticeonly),
])


active_conditions: int = sum([
    bool(liveonly),
    bool(mediaonly),
    bool(photoonly),
    bool(boardonly),
    bool(noticeonly),
])


class MediaLists(NamedTuple):
    vod_list: List[Dict[str, Any]]
    photo_list: List[Dict[str, Any]]
    live_list: List[Dict[str, Any]]
    post_list: List[Dict[str, Any]]
    notice_list: List[Dict[str, Any]]
    notice_list: List[Dict[str, Any]]


class FilteredMediaLists(NamedTuple):
    filter_vod_list: List[Dict[str, Any]]
    filter_photo_list: List[Dict[str, Any]]
    filter_live_list: List[Dict[str, Any]]
    filter_post_list: List[Dict[str, Any]]
    filter_notice_list: List[Dict[str, Any]]



SelectedMediaDict = Dict[str, List[Dict[str, Any]]]
ListDataTuple = Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]


class Handle_Choice:
    def __init__(self, community_id: int, communityname: str, time_a: Optional[datetime], time_b: Optional[datetime]):
        self.community_id: int = community_id
        self.communityname: str = communityname
        self.time_a: Optional[datetime] = time_a
        self.time_b: Optional[datetime] = time_b
        self.selected_media = None
        self.fetcher = MediaFetcher(self.community_id, self.communityname, self.time_a, self.time_b)
        
    async def get_list_data(self) -> ListDataTuple:
        # Fetch all media lists concurrently
        BO: Board = Board(self.community_id, self.communityname, self.time_a, self.time_b)
        MediaLists([], [], [], [], [])
        TYPE: str = ''
        if active_conditions_1 != 0 or active_conditions_1 + active_conditions_2 == 0: 
            vod_list, photo_list, live_list = await self.fetcher.get_all_media_lists()
        else:
            vod_list, photo_list, live_list = [], [], []
        if active_conditions_2 != 0 or active_conditions_1 + active_conditions_2 == 0:
            data_list, TYPE = await BO.get_artis_board_list()
        else:
            data_list, TYPE = [], 'null'
        
        match TYPE:
            case 'artist':
                if noticeonly is False:
                    notice_list: List[Dict[str, Any]] = []
                    post_list = data_list
                    return MediaLists(vod_list, photo_list, live_list, post_list, notice_list)
            case 'notice':
                post_list: List[Dict[str, Any]] = []
                notice_list = data_list
                return MediaLists(vod_list, photo_list, live_list, post_list, notice_list)
            case 'notice+board':
                post_list: List[Dict[str, Any]] = []
                notice_list: List[Dict[str, Any]] = []
                post_list, notice_list = data_list[0], data_list[1]
                return MediaLists(vod_list, photo_list, live_list, post_list, notice_list)
            case _:
                post_list, notice_list = [], []
                return MediaLists(vod_list, photo_list, live_list, post_list, notice_list)
            
    async def fetch_filtered_media(self) -> ListDataTuple:
        # 接收 ListDataTuple, 5個 List[dict]
        vod_list, photo_list, live_list, post_list, notice_list = await self.get_list_data()
        # If no conditions are True, return all lists
        if active_conditions == 0:
            return vod_list, photo_list, live_list, post_list, notice_list
        # Initialize result lists based on corresponding flags
        result_vod_list: List[Dict[str, Any]] = vod_list if mediaonly else []
        result_photo_list: List[Dict[str, Any]] = photo_list if photoonly else []
        result_live_list: List[Dict[str, Any]] = live_list if liveonly else []
        result_post_list: List[Dict[str, Any]] = post_list if boardonly else []
        result_notice_list: List[Dict[str, Any]] = notice_list if noticeonly else []
        return FilteredMediaLists(result_vod_list, result_photo_list, result_live_list, result_post_list, result_notice_list)

    async def handle_choice(self) -> Optional[SelectedMediaDict]:
        if paramstore.get('no_cookie') is not True:
            await request_my()

        if self.time_a is not None or self.time_b is not None:
            self.printer_time_filter()
        selected_media: Optional[SelectedMediaDict] = await self.media_list()
        self.selected_media = await self.user_selected_media(selected_media)
        self.printer_user_choese()
        return await self.process_selected_media()
    
    async def media_list(self):
        try:
            # 接收 ListDataTuple, 5個 List[dict]
            filter_media = await self.fetch_filtered_media()
            filter_vod_list, filter_photo_list, filter_live_list, filter_post_list, filter_notice_list = filter_media

            if paramstore.get('notify_mod') is True:
                # notify_only
                filter_live_list = await NotifyFetcher().get_all_notify_lists(self.time_a, self.time_b)
                filter_vod_list, filter_photo_list, filter_post_list, filter_notice_list = [], [], [], []
        except TypeError as e:
            logger.error(e)
            return
        selected_media = await InquirerPySelector(filter_vod_list, filter_photo_list, filter_live_list, filter_post_list, filter_notice_list).run()
        return selected_media

    async def user_selected_media(self, selected_media: Dict[str, List[Dict[str, Any]]]) -> SelectedMediaDict:
        if selected_media is None:
            sys.exit(0)
        self.selected_media = selected_media
        return self.selected_media
    
    async def process_selected_media(self) -> SelectedMediaDict:
        processed_media: SelectedMediaDict = MediaJsonProcessor.process_selection(self.selected_media)
        custom_media_types = [
            ('vods', 'VOD'),
            ('lives', 'LIVE'), 
            ('photos', 'PHOTO'),
            ('post', 'POST'),
            ('notice', 'NOTICE')
        ]
        
        for k, type in custom_media_types:
            if self.selected_media.get(k):
                current_media_data = {k: self.selected_media[k]}
                MP: Callable = MediaProcessor(current_media_data).process_media_queue
                queue: MediaQueue = MediaQueue()
                queue.enqueue_batch(processed_media[k], type)
                await MP(queue)
        return self.selected_media

    def printer_user_choese(self):
        temp_messages = []
        media_types = [
            {'key': 'vods', 'color': 'khaki', 'label': 'VOD'},
            {'key': 'photos', 'color': 'khaki', 'label': 'PHOTO'},
            {'key': 'lives', 'color': 'khaki', 'label': 'Live'},
            {'key': 'post', 'color': 'khaki', 'label': 'Post'},
            {'key': 'notice', 'color': 'khaki', 'label': 'Notice'},
        ]
        for media in media_types:
            selected_list = self.selected_media.get(media['key'], [])
            if len(selected_list) > 0:
                count = len(selected_list)
                color_name = media['color']
                label = media['label']
                
                formatted_item = f"{Color.fg(color_name)}{count} {Color.fg('light_gray')}{label}"
                temp_messages.append(formatted_item)
        if temp_messages:
            combined_message = ", ".join(temp_messages)
            logger.info(
                f"{Color.fg('light_gray')}choese "f"{combined_message}"f"{Color.reset()}")
            
    def printer_time_filter(self):
        logger.info(f"{Color.fg('tomato')}choese "
                f"{Color.fg('sand')}{self.time_a} "
                f"{Color.fg('light_gray')}- "
                f"{Color.fg('sand')}{self.time_b}{Color.reset()}"
                )