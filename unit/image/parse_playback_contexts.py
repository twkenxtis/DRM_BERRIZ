from typing import Any, Dict, List


async def parse_playback_contexts(playback_contexts: List[Dict[str, Any]]) -> List[Any]:
    if not playback_contexts:
        raise ValueError("public_contexts is empty")

    ctx: Dict[str, Any] = playback_contexts[0]

    # root
    code: Any = ctx.get("code")
    message: Any = ctx.get("message")
    data: Dict[str, Any] = ctx.get("data", {})

    # data
    vod: Any = data.get("vod")
    photo: Dict[str, Any] = data.get("photo", {})
    youtube: Any = data.get("youtube")
    tracking: Any = data.get("tracking")
    settlement: Any = data.get("settlement")

    # photo
    image_count: Any = photo.get("imageCount")
    images: List[Any] = photo.get("images", [])

    return images