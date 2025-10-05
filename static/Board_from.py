from typing import Any, Dict, List, Optional, Union


PhotoDict = Dict[str, Union[str, int, None]]
LinkDict = Dict[str, Any]
AnalysisDict = Dict[str, Union[str, int, None]]
Hashtag = str


class Board_from:
    """
    從 board_list_data 字典初始化貼文資料的類別。
    
    將巢狀字典資料攤平（Flatten）為類別屬性。
    """
    
    # Post core
    post_id: Optional[int]
    post_user_id: Optional[int]
    post_community_id: Optional[int]
    title: Optional[str]
    body: Optional[str]
    plain_body: Optional[str]
    language_code: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    is_active: Optional[bool]
    is_baned: Optional[bool]
    status: Optional[str]
    is_updated: Optional[bool]
    
    # Post media
    photos: List[PhotoDict]
    links: List[LinkDict]
    analyses: List[AnalysisDict]
    
    # Hashtags
    hashtags: List[Hashtag]
    
    # Writer
    writer_user_id: Optional[int]
    writer_community_id: Optional[int]
    writer_type: Optional[str]
    writer_community_artist_id: Optional[int]
    writer_is_artist: Optional[bool]
    writer_name: Optional[str]
    writer_image_url: Optional[str]
    writer_bg_image_url: Optional[str]
    writer_is_fanclub_user: Optional[bool]
    
    # Count info
    comment_count: Optional[int]
    like_count: Optional[int]
    
    # Board info
    board_id: Optional[int]
    board_type: Optional[str]
    board_community_id: Optional[int]
    board_name: Optional[str]
    board_is_fanclub_only: Optional[bool]

    def __init__(self, board_list_data: Dict[str, Any]) -> None:
        # Top-level containers
        post: Dict[str, Any] = board_list_data.get("post", {})
        writer: Dict[str, Any] = board_list_data.get("writer", {})
        count_info: Dict[str, Any] = board_list_data.get("countInfo", {})
        board_info: Dict[str, Any] = board_list_data.get("boardInfo", {})

        # Post core
        self.post_id = post.get("postId")  # type: Optional[int]
        self.post_user_id = post.get("userId")  # type: Optional[int]
        self.post_community_id = post.get("communityId")  # type: Optional[int]
        self.title = post.get("title")  # type: Optional[str]
        self.body = post.get("body")  # type: Optional[str]
        self.plain_body = post.get("plainBody")  # type: Optional[str]
        self.language_code = post.get("languageCode")  # type: Optional[str]
        self.created_at = post.get("createdAt")  # type: Optional[str]
        self.updated_at = post.get("updatedAt")  # type: Optional[str]
        self.is_active = post.get("isActive")  # type: Optional[bool]
        self.is_baned = post.get("isBaned")  # type: Optional[bool]
        self.status = post.get("status")  # type: Optional[str]
        self.is_updated = post.get("isUpdated")  # type: Optional[bool]

        # Post media
        media: Dict[str, Any] = post.get("media", {})
        photos: List[Any] = media.get("photo", [])
        links: List[Any] = media.get("link", [])
        analyses: List[Any] = media.get("analysis", [])

        # Photos normalized
        self.photos: List[PhotoDict] = []
        for p in photos:
            if not isinstance(p, dict):
                continue
            meta: Dict[str, Any] = p.get("imageMetadata", {})
            self.photos.append({
                "media_id": p.get("mediaId"),  # type: Optional[int]
                "image_url": p.get("imageUrl"),  # type: Optional[str]
                "width": meta.get("width"),  # type: Optional[int]
                "height": meta.get("height"),  # type: Optional[int]
                "published_at": meta.get("publishedAt"),  # type: Optional[str]
            })

        # Links normalized (kept as-is if later schema extends)
        self.links: List[LinkDict] = []
        for l in links:
            if not isinstance(l, dict):
                continue
            self.links.append(l)

        # Analyses normalized
        self.analyses: List[AnalysisDict] = []
        for a in analyses:
            if not isinstance(a, dict):
                continue
            self.analyses.append({
                "media_id": a.get("mediaId"),  # type: Optional[int]
                "description": a.get("description"),  # type: Optional[str]
            })

        # Hashtags
        hashtags: List[Any] = post.get("hashtags", [])
        self.hashtags: List[Hashtag] = []
        for h in hashtags:
            # 假設標籤是字串
            if isinstance(h, str):
                self.hashtags.append(h)

        # Writer
        self.writer_user_id = writer.get("userId")  # type: Optional[int]
        self.writer_community_id = writer.get("communityId")  # type: Optional[int]
        self.writer_type = writer.get("type")  # type: Optional[str]
        self.writer_community_artist_id = writer.get("communityArtistId")  # type: Optional[int]
        self.writer_is_artist = writer.get("isArtist")  # type: Optional[bool]
        self.writer_name = writer.get("name")  # type: Optional[str]
        self.writer_image_url = writer.get("imageUrl")  # type: Optional[str]
        self.writer_bg_image_url = writer.get("bgImageUrl")  # type: Optional[str]
        self.writer_is_fanclub_user = writer.get("isFanclubUser")  # type: Optional[bool]

        # Count info
        self.comment_count = count_info.get("commentCount")  # type: Optional[int]
        self.like_count = count_info.get("likeCount")  # type: Optional[int]

        # Board info
        self.board_id = board_info.get("boardId")  # type: Optional[int]
        self.board_type = board_info.get("boardType")  # type: Optional[str]
        self.board_community_id = board_info.get("communityId")  # type: Optional[int]
        self.board_name = board_info.get("name")  # type: Optional[str]
        self.board_is_fanclub_only = board_info.get("isFanclubOnly")  # type: Optional[bool]