from typing import Any, Dict, List


async def parse_public_contexts(public_contexts: List[Dict[str, Any]]) -> str:
    if not public_contexts:
        raise ValueError("public_contexts is empty")

    ctx = public_contexts[0]

    # root
    code = ctx.get("code")
    message = ctx.get("message")
    data = ctx.get("data", {})

    # data
    media = data.get("media", {})
    community_artists = data.get("communityArtists", [])
    media_categories = data.get("mediaCategories", [])
    comment = data.get("comment", {})

    # media
    media_seq = media.get("mediaSeq")
    media_id = media.get("mediaId")
    media_type = media.get("mediaType")
    title = media.get("title")
    body = media.get("body")
    thumbnail_url = media.get("thumbnailUrl")
    published_at = media.get("publishedAt")
    community_id = media.get("communityId")
    is_fanclub_only = media.get("isFanclubOnly")

    # communityArtists
    artist_id = (
        community_artists[0].get("communityArtistId") if community_artists else None
    )
    artist_name = community_artists[0].get("name") if community_artists else None
    artist_image_url = (
        community_artists[0].get("imageUrl") if community_artists else None
    )

    # mediaCategories
    category_id = (
        media_categories[0].get("mediaCategoryId") if media_categories else None
    )
    category_name = (
        media_categories[0].get("mediaCategoryName") if media_categories else None
    )

    # comment
    content_type_code = comment.get("contentTypeCode")
    read_content_id = comment.get("readContentId")
    write_content_id = comment.get("writeContentId")

    return media_id, title, published_at
