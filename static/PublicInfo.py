import json


class PublicInfo:
    def __init__(self, public_context):
        # Top-level info
        self.code = public_context.get("code")
        self.status = public_context.get("message")

        # Access data from the 'data' key
        data = public_context.get("data", {})
        media_data = data.get("media", {})

        # Media basic info
        self.media_seq = media_data.get("mediaSeq")
        self.media_id = media_data.get("mediaId")
        self.media_type = media_data.get("mediaType")
        self.title = media_data.get("title")
        self.body = media_data.get("body")
        self.thumbnail_url = media_data.get("thumbnailUrl")
        self.published_at = media_data.get("publishedAt")
        self.community_id = media_data.get("communityId")
        self.is_fanclub_only = media_data.get("isFanclubOnly")

        # Community artists
        self.artists = []
        artists_data = data.get("communityArtists", [])
        for artist in artists_data:
            self.artists.append(
                {
                    "id": artist.get("communityArtistId"),
                    "name": artist.get("name"),
                    "image_url": artist.get("imageUrl"),
                }
            )

        # Media categories
        self.categories = []
        categories_data = data.get("mediaCategories", [])
        for category in categories_data:
            self.categories.append(
                {
                    "id": category.get("mediaCategoryId"),
                    "name": category.get("mediaCategoryName"),
                }
            )

        # Comment info
        comment_data = data.get("comment", {})
        self.comment_info = {
            "content_type": comment_data.get("contentTypeCode"),
            "read_content_id": comment_data.get("readContentId"),
            "write_content_id": comment_data.get("writeContentId"),
        }

    def get_primary_artist(self):
        """Returns the first artist if available"""
        return self.artists[0] if self.artists else None

    def get_category_names(self):
        """Returns list of category names"""
        return [cat["name"] for cat in self.categories]

    def get_formatted_publish_date(self, format_str="%Y-%m-%d %H:%M"):
        """Returns formatted publish date string"""
        from datetime import datetime

        if self.published_at:
            dt = datetime.strptime(self.published_at, "%Y-%m-%dT%H:%M:%SZ")
            return dt.strftime(format_str)
        return None

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
                "formatted_published_at": self.get_formatted_publish_date(),
                "community_id": self.community_id,
                "is_fanclub_only": self.is_fanclub_only,
                "thumbnail_url": self.thumbnail_url,
                "description": self.body,
            },
            "artists": self.artists,
            "categories": self.categories,
            "comment_info": self.comment_info,
        }

    def to_json(self, indent=2):
        """Convert to JSON string with pretty formatting"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
