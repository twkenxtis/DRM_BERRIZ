class Board_from:
    def __init__(self, board_list_data):
        # Top-level containers
        post = board_list_data.get("post", {})
        writer = board_list_data.get("writer", {})
        count_info = board_list_data.get("countInfo", {})
        board_info = board_list_data.get("boardInfo", {})

        # Post core
        self.post_id = post.get("postId")
        self.post_user_id = post.get("userId")
        self.post_community_id = post.get("communityId")
        self.title = post.get("title")
        self.body = post.get("body")
        self.plain_body = post.get("plainBody")
        self.language_code = post.get("languageCode")
        self.created_at = post.get("createdAt")
        self.updated_at = post.get("updatedAt")
        self.is_active = post.get("isActive")
        self.is_baned = post.get("isBaned")
        self.status = post.get("status")
        self.is_updated = post.get("isUpdated")

        # Post media
        media = post.get("media", {})
        photos = media.get("photo", [])
        links = media.get("link", [])
        analyses = media.get("analysis", [])

        # Photos normalized
        self.photos = []
        for p in photos:
            if not isinstance(p, dict):
                continue
            meta = p.get("imageMetadata", {})
            self.photos.append({
                "media_id": p.get("mediaId"),
                "image_url": p.get("imageUrl"),
                "width": meta.get("width"),
                "height": meta.get("height"),
                "published_at": meta.get("publishedAt"),
            })

        # Links normalized (kept as-is if later schema extends)
        self.links = []
        for l in links:
            if not isinstance(l, dict):
                continue
            self.links.append(l)

        # Analyses normalized
        self.analyses = []
        for a in analyses:
            if not isinstance(a, dict):
                continue
            self.analyses.append({
                "media_id": a.get("mediaId"),
                "description": a.get("description"),
            })

        # Hashtags
        hashtags = post.get("hashtags", [])
        self.hashtags = []
        for h in hashtags:
            self.hashtags.append(h)

        # Writer
        self.writer_user_id = writer.get("userId")
        self.writer_community_id = writer.get("communityId")
        self.writer_type = writer.get("type")
        self.writer_community_artist_id = writer.get("communityArtistId")
        self.writer_is_artist = writer.get("isArtist")
        self.writer_name = writer.get("name")
        self.writer_image_url = writer.get("imageUrl")
        self.writer_bg_image_url = writer.get("bgImageUrl")
        self.writer_is_fanclub_user = writer.get("isFanclubUser")

        # Count info
        self.comment_count = count_info.get("commentCount")
        self.like_count = count_info.get("likeCount")

        # Board info
        self.board_id = board_info.get("boardId")
        self.board_type = board_info.get("boardType")
        self.board_community_id = board_info.get("communityId")
        self.board_name = board_info.get("name")
        self.board_is_fanclub_only = board_info.get("isFanclubOnly")
