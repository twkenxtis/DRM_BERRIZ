from typing import Any, Dict, List, Optional, Tuple


async def parse_public_contexts(
    public_contexts: List[Dict[str, Any]]
) -> Tuple[Optional[Any], Optional[Any], Optional[Any], Optional[Any]]:
    if not public_contexts:
        raise ValueError("public_contexts is empty")

    ctx: Dict[str, Any] = public_contexts[0]

    # root
    code: Optional[Any] = ctx.get("code")
    message: Optional[Any] = ctx.get("message")
    data: Dict[str, Any] = ctx.get("data", {})

    # data
    media: Dict[str, Any] = data.get("media", {})
    community_artists: List[Dict[str, Any]] = data.get("communityArtists", [])
    media_categories: List[Dict[str, Any]] = data.get("mediaCategories", [])
    comment: Dict[str, Any] = data.get("comment", {})

    # media
    media_seq: Optional[Any] = media.get("mediaSeq")
    media_id: Optional[Any] = media.get("mediaId")
    media_type: Optional[Any] = media.get("mediaType")
    title: Optional[Any] = media.get("title")
    body: Optional[Any] = media.get("body")
    thumbnail_url: Optional[Any] = media.get("thumbnailUrl")
    published_at: Optional[Any] = media.get("publishedAt")
    community_id: Optional[Any] = media.get("communityId")
    is_fanclub_only: Optional[Any] = media.get("isFanclubOnly")

    # communityArtists
    artist_id: Optional[Any] = (
        community_artists[0].get("communityArtistId") if community_artists else None
    )
    artist_name: Optional[Any] = community_artists[0].get("name") if community_artists else None
    artist_image_url: Optional[Any] = (
        community_artists[0].get("imageUrl") if community_artists else None
    )

    # mediaCategories
    category_id: Optional[Any] = (
        media_categories[0].get("mediaCategoryId") if media_categories else None
    )
    category_name: Optional[Any] = (
        media_categories[0].get("mediaCategoryName") if media_categories else None
    )

    # comment
    content_type_code: Optional[Any] = comment.get("contentTypeCode")
    read_content_id: Optional[Any] = comment.get("readContentId")
    write_content_id: Optional[Any] = comment.get("writeContentId")

    return media_id, title, published_at, community_id