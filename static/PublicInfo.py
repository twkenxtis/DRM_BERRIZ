from typing import Optional, List, Dict, Any

import orjson

from lib.load_yaml_config import CFG
from unit.data.data import get_formatted_publish_date


class PublicInfo:
    def __init__(self, public_context: Dict[str, Any]):
        if isinstance(public_context, dict):
            public_context = public_context
        else:
            public_context: tuple[Dict[str, Any]]
            public_context = public_context[1]
        self.code: Optional[int] = public_context.get("code")
        self.status: Optional[str] = public_context.get("message")

        self.data: dict = public_context.get("data", {})
        self.media_data: dict = self.data.get("media", {})
        
        self.media_seq: Optional[int] = self.media_data.get("mediaSeq")
        self.media_id: Optional[int] = self.media_data.get("mediaId")
        self.media_type: Optional[str] = self.media_data.get("mediaType")
        self.title: Optional[str] = self.media_data.get("title")
        self.body: Optional[str] = self.media_data.get("body")
        self.thumbnail_url: Optional[str] = self.media_data.get("thumbnailUrl")
        self.published_at: Optional[str] = self.media_data.get("publishedAt")
        self.community_id: Optional[str] = self.media_data.get("communityId")
        self.is_fanclub_only: Optional[bool] = self.media_data.get("isFanclubOnly")

        self.artists: List[Dict] = []
        self.artists_data: List[Dict] = self.data.get("communityArtists", [])
        for artist in self.artists_data:
            self.artists.append(
                {
                    "id": artist.get("communityArtistId"),
                    "name": artist.get("name"),
                    "image_url": artist.get("imageUrl"),
                }
            )

        self.categories: List[Dict] = []
        categories_data: List[Dict] = self.data.get("mediaCategories", [])
        for category in categories_data:
            self.categories.append(
                {
                    "id": category.get("mediaCategoryId"),
                    "name": category.get("mediaCategoryName"),
                }
            )
        
        self.comment_data: dict = self.data.get("comment", {})
        self.comment_info: Dict = {
            "content_type": self.comment_data.get("contentTypeCode"),
            "read_content_id": self.comment_data.get("readContentId"),
            "write_content_id": self.comment_data.get("writeContentId"),
        }

    def get_primary_artist(self) -> Optional[Dict]:
        """回傳第一個藝術家字典（如果存在的話）"""
        return self.artists[0] if self.artists else None

    def get_category_names(self) -> List[str]:
        """回傳所有類別名稱的清單"""
        return [cat["name"] for cat in self.categories if cat.get("name")]

    def __str__(self):
        return f"PublicInfo(media_id={self.media_id}, title={self.title}, artists={[a['name'] for a in self.artists]})"

    def to_dict(self):
        """Convert all data to dictionary"""
        if self.code != "0000":
            return {"error": "Invalid status code"}

        return {
            "code": self.code,
            "status": self.status,
            "media": {
                "seq": self.media_seq,
                "id": self.media_id,
                "type": self.media_type,
                "title": self.title,
                "published_at": self.published_at,
                "formatted_published_at": get_formatted_publish_date(self.published_at, CFG['output_template']['date_formact']),
                "community_id": self.community_id,
                "is_fanclub_only": self.is_fanclub_only,
                "thumbnail_url": self.thumbnail_url,
                "description": self.body,
            },
            "artists": self.artists,
            "categories": self.categories,
            "comment_info": self.comment_info,
        }

    def to_json(self):
        """Convert to JSON string with pretty formatting"""
        return orjson.dumps(self.to_dict(), option=orjson.OPT_INDENT_2).decode("utf-8")


class PublicInfo_Custom:
    def __init__(self, public_context: Dict[str, Any]):
        public_context = public_context[0]
        self.code: Optional[str] = public_context.get("code")
        self.status: Optional[str] = public_context.get("status")

        media = public_context.get("media", {})
        self.media_seq: Optional[int] = media.get("seq")
        self.media_id: Optional[str] = media.get("id")
        self.media_type: Optional[str] = media.get("type")
        self.media_title: Optional[str] = media.get("title")
        self.media_published_at: Optional[str] = media.get("published_at")
        self.formatted_published_at: Optional[str] = media.get("formatted_published_at")
        self.media_community_id: Optional[int] = media.get("community_id")
        self.media_is_fanclub_only: Optional[bool] = media.get("is_fanclub_only")
        self.media_thumbnail_url: Optional[str] = media.get("thumbnail_url")
        self.media_description: Optional[str] = media.get("description")

        artists = public_context.get("artists", [])
        self.artist_list: List[Dict[str, Optional[str]]] = [
            {
                "id": str(artist.get("id")),
                "name": artist.get("name"),
                "image_url": artist.get("image_url")
            }
            for artist in artists
        ]

        comment_info = public_context.get("comment_info", {})
        self.comment_content_type: Optional[str] = comment_info.get("content_type")
        self.comment_read_content_id: Optional[str] = comment_info.get("read_content_id")
        self.comment_write_content_id: Optional[str] = comment_info.get("write_content_id")

