import sys
from datetime import datetime

from typing import Optional, List, Dict, Any, Tuple

from lib.artis.artis_menu import Board
from lib.media_queue import MediaQueue
from mystate.parse_my import request_my
from static.color import Color
from unit.getall.GetMediaList import MediaFetcher
from unit.handle.handle_log import setup_logging
from unit.main_process import MediaProcessor
from unit.media.media_json_process import MediaJsonProcessor
from unit.user_choice import InquirerPySelector
from unit.getall.GetNotifyList import NotifyFetcher
from static.parameter import paramstore


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
   
        
SelectedMediaDict = Dict[str, List[Dict[str, Any]]]
# get_list_data 和 fetch_filtered_media 的回傳型別
ListDataTuple = Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]
# Board.get_artis_board_list 的回傳型別
BoardListTuple = Tuple[List[Dict[str, Any]], str]


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
        
        vod_list: List[Dict[str, Any]]
        photo_list: List[Dict[str, Any]]
        live_list: List[Dict[str, Any]]
        data_list: List[Dict[str, Any]]
        TYPE: str
        if active_conditions_1 != 0 or active_conditions_1 + active_conditions_2 == 0: 
            vod_list, photo_list, live_list = await self.fetcher.get_all_media_lists()
        else:
            vod_list, photo_list, live_list = [], [], []
        if active_conditions_2 != 0 or active_conditions_1 + active_conditions_2 == 0:
            data_list, TYPE = await BO.get_artis_board_list()
        else:
            data_list, TYPE = [], 'null'
        post_list: List[Dict[str, Any]]
        notice_list: List[Dict[str, Any]]
        
        match TYPE:
            case 'artist':
                if noticeonly is False:
                    notice_list: List[Dict[str, Any]] = []
                    post_list = data_list
                    return vod_list, photo_list, live_list, post_list, notice_list
            case 'notice':
                post_list: List[Dict[str, Any]] = []
                notice_list = data_list
                return vod_list, photo_list, live_list, post_list, notice_list
            case 'notice+board':
                post_list: List[Dict[str, Any]] = []
                notice_list: List[Dict[str, Any]] = []
                post_list, notice_list = data_list[0], data_list[1]
                return vod_list, photo_list, live_list, post_list, notice_list
            case _:
                post_list, notice_list = [], []
                return vod_list, photo_list, live_list, post_list, notice_list
            
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
        #result_notice_list: List[Dict[str, Any]] = notice_list if noticeonly else []
        return result_vod_list, result_photo_list, result_live_list, result_post_list, notice_list

    # 根據 selected_media 的結構，回傳型別應為 SelectedMediaDict
    async def handle_choice(self) -> Optional[SelectedMediaDict]:
        
        # 假設 paramstore.get 返回 bool
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
            vod_list: List[Dict[str, Any]]
            photo_list: List[Dict[str, Any]]
            live_list: List[Dict[str, Any]]
            post_list: List[Dict[str, Any]]
            notice_list: List[Dict[str, Any]]
            # 接收 ListDataTuple, 5個 List[dict]
            vod_list, photo_list, live_list, post_list, notice_list = await self.fetch_filtered_media()
            
            # 假設 paramstore.get 返回 bool
            if paramstore.get('notify_mod') is True:
                # notify_only
                live_list = await NotifyFetcher().get_all_notify_lists(self.time_a, self.time_b)
                vod_list, photo_list, post_list, notice_list = [], [], [], []
        except TypeError as e:
            logger.error(e)
            return
        selected_media = await InquirerPySelector(vod_list, photo_list, live_list, post_list, notice_list).run()
        return selected_media

    async def user_selected_media(self, selected_media: Dict[str, List[Dict[str, Any]]]) -> SelectedMediaDict:
        if selected_media is None:
            sys.exit(0)
        self.selected_media = selected_media
        return self.selected_media
    
    async def process_selected_media(self) -> SelectedMediaDict:
        MP: Any = MediaProcessor(self.selected_media).process_media_queue
        MJ: Any = MediaJsonProcessor.process_selection
        processed_media: SelectedMediaDict = MJ(self.selected_media)
        
        # Process VOD items
        if self.selected_media['vods']:
            vod_queue: MediaQueue = MediaQueue()
            vod_queue.enqueue_batch(processed_media["vods"], 'VOD')
            await MP(vod_queue)
            
        # Process Live-replay items
        if self.selected_media['lives']:
            live_replay_queue: MediaQueue = MediaQueue()
            live_replay_queue.enqueue_batch(processed_media["lives"], 'LIVE')
            await MP(live_replay_queue)

        # Process PHOTO items
        if self.selected_media['photos']:
            photo_queue: MediaQueue = MediaQueue()
            photo_queue.enqueue_batch(processed_media["photos"], 'PHOTO')
            await MP(photo_queue)

        # Process POST items
        if self.selected_media['post']:
            post_queue: MediaQueue = MediaQueue()
            post_queue.enqueue_batch(processed_media["post"], 'POST')
            await MP(post_queue)

        # Process Notice items
        if self.selected_media['notice']:
            notice_queue: MediaQueue = MediaQueue()
            notice_queue.enqueue_batch(processed_media["notice"], 'NOTICE')
            await MP(notice_queue)
            
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