from typing import Any, Dict


def parse_playback_contexts(playback_contexts: Dict[str, Any]) -> None:
    if not playback_contexts:
        raise ValueError("public_contexts is empty")

    ctx = playback_contexts[0]

    # root
    code = ctx.get("code")
    message = ctx.get("message")
    data = ctx.get("data", {})

    # data
    vod = data.get("vod")
    photo = data.get("photo", {})
    youtube = data.get("youtube")
    tracking = data.get("tracking")
    settlement = data.get("settlement")

    # photo
    image_count = photo.get("imageCount")
    images = photo.get("images", [])

    return images
