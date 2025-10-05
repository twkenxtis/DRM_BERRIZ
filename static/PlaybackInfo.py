from typing import Any, Dict, List, Optional
import orjson

class PlaybackInfo:
    def __init__(self, playback_context: Dict[str, Any]):
        if isinstance(playback_context, dict):
            playback_context = playback_context
        else:
            playback_context: tuple[Dict[str, Any]]
            playback_context = playback_context[1]
        # Top-level info
        self.code: Optional[str] = playback_context.get("code")
        self.status: Optional[str] = playback_context.get("message")

        # Access data from the 'data' key
        data: Dict[str, Any] = playback_context.get("data", {})

        # VOD data
        vod_data: Dict[str, Any] = data.get("vod", {})
        if vod_data:
            self.duration: Optional[int] = vod_data.get("duration")
            self.orientation: Optional[str] = vod_data.get("orientation")
            self.is_drm: Optional[bool] = vod_data.get("isDrm")

            # DRM info
            self.drm_info: Dict[str, Any] = vod_data.get("drmInfo", {})
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

            # HLS data
            hls_data: Dict[str, Any] = vod_data.get("hls", {})
            if hls_data:
                self.hls_playback_url: Optional[str] = hls_data.get("playbackUrl")
                self.hls_adaptations: List[Dict[str, Any]] = hls_data.get("adaptationSet", [])
            else:
                self.hls_playback_url = None
                self.hls_adaptations = []

            # DASH data
            dash_data: Dict[str, Any] = vod_data.get("dash", {})
            if dash_data:
                self.dash_playback_url: Optional[str] = dash_data.get("playbackUrl")
            else:
                self.dash_playback_url = None

        # Tracking info
        tracking_data: Dict[str, Any] = data.get("tracking", {})
        self.tracking_interval: Optional[int] = tracking_data.get("trackingPlaybackPollingIntervalSec")

        # Settlement info
        settlement_data: Dict[str, Any] = data.get("settlement", {})
        self.settlement_token: Optional[str] = settlement_data.get("mediaSettlementToken")

    def to_dict(self) -> Dict[str, Any]:
        """Convert all data to dictionary"""
        if self.code != "0000":
            return {"error": "Invalid status code"}

        return {
            "code": self.code,
            "status": self.status,
            "vod": {
                "duration": self.duration,
                "orientation": self.orientation,
                "is_drm": self.is_drm,
                "drm_info": {
                    "assertion": getattr(self, "assertion", None),
                    "widevine_license": getattr(self, "widevine_license", None),
                    "playready_license": getattr(self, "playready_license", None),
                    "fairplay": {
                        "license": getattr(self, "fairplay_license", None),
                        "cert": getattr(self, "fairplay_cert", None),
                    },
                },
                "hls": {
                    "playback_url": self.hls_playback_url,
                    "adaptations": self.hls_adaptations,
                },
                "dash": {
                    "playback_url": self.dash_playback_url,
                },
            },
            "tracking_interval": self.tracking_interval,
            "settlement_token": self.settlement_token,
        }

    def to_json(self) -> str:
        """Convert to JSON string with pretty formatting"""
        return orjson.dumps(self.to_dict(), option=orjson.OPT_INDENT_2).decode("utf-8")

    def __str__(self) -> str:
        """String representation of the object"""
        return f"PlaybackInfo(code={self.code}, status={self.status}, duration={self.duration})"


class LivePlaybackInfo:
    def __init__(self, playback_context: Dict[str, Any]):
        if isinstance(playback_context, dict):
            playback_context = playback_context
        else:
            playback_context: tuple[Dict[str, Any]]
            playback_context = playback_context[1]
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

    def to_dict(self) -> Dict[str, Any]:
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
                "thumbnail_url": self.thumbnail_url,
                "published_at": self.published_at,
                "community_id": self.community_id,
                "is_fanclub_only": self.is_fanclub_only,
                "live": {
                    "status": self.live_status,
                    "replay": {
                        "duration": self.duration,
                        "orientation": self.orientation,
                        "is_drm": self.is_drm,
                        "drm_info": {
                            "assertion": getattr(self, "assertion", None),
                            "widevine_license": getattr(self, "widevine_license", None),
                            "playready_license": getattr(self, "playready_license", None),
                            "fairplay": {
                                "license": getattr(self, "fairplay_license", None),
                                "cert": getattr(self, "fairplay_cert", None),
                            },
                        },
                        "dash": {
                            "playback_url": self.dash_playback_url,
                        },
                        "hls": {
                            "playback_url": self.hls_playback_url,
                            "adaptation_set": self.hls_adaptation_set,
                        },
                    },
                },
            },
            "community_artists": self.community_artists,
            "tracking_interval_sec": self.tracking_interval_sec,
            "settlement_token": self.settlement_token,
            "link": self.link,
            "video_rating_assessment": self.video_rating_assessment,
        }

    def to_json(self) -> str:
        """Convert to JSON string with pretty formatting"""
        return orjson.dumps(self.to_dict(), option=orjson.OPT_INDENT_2).decode("utf-8")

    def __str__(self) -> str:
        """String representation of the object"""
        return f"LivePlaybackInfo(media_id={self.media_id}, title={self.title}, live_status={self.live_status})"
