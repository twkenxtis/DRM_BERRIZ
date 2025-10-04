from typing import Any, Dict, List, Optional

import orjson

from lib.load_yaml_config import CFG
from unit.data.data import get_formatted_publish_date


class PlaybackInfo:
    def __init__(self, info_context: Dict[str, Any]):
        # Top-level info
        self.code: Optional[str] = info_context.get("code")
        self.status: Optional[str] = info_context.get("message")

        # Access data from the 'data' key
        data: Dict[str, Any] = info_context.get("data", {})

        # Media data
        self.media_seq: Optional[int] = data.get("mediaSeq")
        self.media_id: Optional[str] = data.get("mediaId")
        self.media_type: Optional[str] = data.get("mediaType")
        self.title: Optional[str] = data.get("title")
        self.published_at: Optional[str] = data.get("publishedAt")
        self.community_id: Optional[str] = data.get("communityId")
        self.is_fanclub_only: Optional[bool] = data.get("isFanclubOnly")
        self.thumbnail_url: Optional[str] = data.get("thumbnailUrl")
        self.body: Optional[str] = data.get("description")

        # Related data
        self.artists: List[Dict[str, Any]] = data.get("artists", [])
        self.categories: List[Dict[str, Any]] = data.get("categories", [])
        self.comment_info: Dict[str, Any] = data.get("commentInfo", {})

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


class LivePlaybackInfo:
    def __init__(self, playback_context: Dict[str, Any]):
        # Top-level info
        self.code: Optional[str] = playback_context.get("code")
        self.status: Optional[str] = playback_context.get("message")

        # Access data from the 'data' key
        data: Dict[str, Any] = playback_context.get("data", {})

        # Media info
        media: Dict[str, Any] = data.get("media", {})
        self.media_seq: Optional[int] = media.get("mediaSeq")
        self.media_id: Optional[int] = media.get("mediaId")
        self.media_type: Optional[str] = media.get("mediaType")
        self.title: Optional[str] = media.get("title")
        self.thumbnail_url: Optional[str] = media.get("thumbnailUrl")
        self.published_at: Optional[str] = media.get("publishedAt")
        self.community_id: Optional[int] = media.get("communityId")
        self.is_fanclub_only: Optional[bool] = media.get("isFanclubOnly")

        # Live replay info
        live: Dict[str, Any] = media.get("live", {})
        self.live_status: Optional[str] = live.get("liveStatus")

        replay: Dict[str, Any] = live.get("replay", {})
        self.duration: Optional[int] = replay.get("duration")
        self.orientation: Optional[str] = replay.get("orientation")
        self.is_drm: Optional[bool] = replay.get("isDrm")
        self.drm_info: Optional[Dict[str, Any]] = replay.get("drmInfo")

        # DASH playback
        dash: Dict[str, Any] = replay.get("dash", {})
        self.dash_playback_url: Optional[str] = dash.get("playbackUrl")

        if self.drm_info and self.drm_info.get("assertion"):
            self.assertion: Optional[str] = self.drm_info["assertion"]

            if "widevine" in self.drm_info:
                self.widevine_license: Optional[str] = self.drm_info["widevine"].get("licenseUrl")
            else:
                self.widevine_license = None

            if "playready" in self.drm_info:
                self.playready_license: Optional[str] = self.drm_info["playready"].get("licenseUrl")
            else:
                self.playready_license = None

            if "fairplay" in self.drm_info:
                self.fairplay_data: Dict[str, Any] = self.drm_info.get("fairplay")  # type: ignore[assignment]
                self.fairplay_license: Optional[str] = self.fairplay_data.get("licenseUrl")
                self.fairplay_cert: Optional[str] = self.fairplay_data.get("certUrl")
            else:
                self.fairplay_license = None
                self.fairplay_cert = None
        else:
            self.assertion = None
            self.widevine_license = None
            self.playready_license = None
            self.fairplay_license = None
            self.fairplay_cert = None
        
        # HLS playback
        hls: Dict[str, Any] = replay.get("hls", {})
        self.hls_playback_url: Optional[str] = hls.get("playbackUrl")
        self.hls_adaptation_set: List[Dict[str, Any]] = []
        for stream in hls.get("adaptationSet", []):
            self.hls_adaptation_set.append({
                "width": stream.get("width"),
                "height": stream.get("height"),
                "playback_url": stream.get("playbackUrl")
            })

        # Artist info
        artists: List[Dict[str, Any]] = data.get("communityArtists", [])
        self.community_artists: List[Dict[str, Any]] = []
        for artist in artists:
            self.community_artists.append({
                "id": artist.get("communityArtistId"),
                "name": artist.get("name"),
                "image_url": artist.get("imageUrl")
            })

        # Tracking
        tracking: Dict[str, Any] = data.get("tracking", {})
        self.tracking_interval_sec: Optional[int] = tracking.get("trackingPlaybackPollingIntervalSec")

        # Settlement
        settlement: Dict[str, Any] = data.get("settlement", {})
        self.settlement_token: Optional[str] = settlement.get("mediaSettlementToken")

        # External link
        self.link: Optional[str] = data.get("link")

        # Optional rating assessment
        self.video_rating_assessment: Optional[Dict[str, Any]] = data.get("videoRatingAssessment")