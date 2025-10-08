from typing import Any, Dict, List, Optional

import orjson

class IMG_PublicContext:
    def __init__(self, public_contexts: List[Dict[str, Any]]) -> None:
        if not public_contexts:
            raise ValueError("public_contexts is empty")

        ctx: Dict[str, Any] = public_contexts[0]

        # root
        self.code: Optional[Any] = ctx.get("code")
        self.message: Optional[Any] = ctx.get("message")
        data: Dict[str, Any] = ctx.get("data", {})

        # data
        media: Dict[str, Any] = data.get("media", {})
        community_artists: List[Dict[str, Any]] = data.get("communityArtists", [])
        media_categories: List[Dict[str, Any]] = data.get("mediaCategories", [])
        comment: Dict[str, Any] = data.get("comment", {})

        # media
        self.media_seq: Optional[Any] = media.get("mediaSeq")
        self.media_id: Optional[Any] = media.get("mediaId")
        self.media_type: Optional[Any] = media.get("mediaType")
        self.title: Optional[Any] = media.get("title")
        self.body: Optional[Any] = media.get("body")
        self.thumbnail_url: Optional[Any] = media.get("thumbnailUrl")
        self.published_at: Optional[Any] = media.get("publishedAt")
        self.community_id: Optional[Any] = media.get("communityId")
        self.is_fanclub_only: Optional[Any] = media.get("isFanclubOnly")

        # communityArtists
        self.community_artists_id: Optional[Any] = (
            community_artists[0].get("communityArtistId") if community_artists else None
        )
        self.community_name: Optional[Any] = community_artists[0].get("name") if community_artists else None
        self.community_artist_image_url: Optional[Any] = (
            community_artists[0].get("imageUrl") if community_artists else None
        )

        # mediaCategories
        self.category_id: Optional[Any] = (
            media_categories[0].get("mediaCategoryId") if media_categories else None
        )
        self.category_name: Optional[Any] = (
            media_categories[0].get("mediaCategoryName") if media_categories else None
        )

        # comment
        self.content_type_code: Optional[Any] = comment.get("contentTypeCode")
        self.read_content_id: Optional[Any] = comment.get("readContentId")
        self.write_content_id: Optional[Any] = comment.get("writeContentId")

    def to_dict(self):
        """Convert all data to dictionary"""
        if self.code != "0000":
            return {"error": "Invalid status code"}

        return {
            # Root level
            "code": self.code,
            "message": self.message,
            
            # Media fields
            "media_seq": self.media_seq,
            "media_id": self.media_id,
            "media_type": self.media_type,
            "title": self.title,
            "body": self.body,
            "thumbnail_url": self.thumbnail_url,
            "published_at": self.published_at,
            "community_id": self.community_id,
            "is_fanclub_only": self.is_fanclub_only,
            
            # Community artists fields
            "community_artists_id": self.community_artists_id,
            "community_name": self.community_name,
            "community_artist_image_url": self.community_artist_image_url,
            
            # Media categories fields
            "category_id": self.category_id,
            "category_name": self.category_name,
            
            # Comment fields
            "content_type_code": self.content_type_code,
            "read_content_id": self.read_content_id,
            "write_content_id": self.write_content_id,
        }
        
    def to_json(self):
        """Convert to JSON string with pretty formatting"""
        return orjson.dumps(self.to_dict(), option=orjson.OPT_INDENT_2).decode("utf-8")