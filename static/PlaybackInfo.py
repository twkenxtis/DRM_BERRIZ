class PlaybackInfo:
    def __init__(self, playback_context):
        # Top-level info
        self.code = playback_context.get("code")
        self.status = playback_context.get("message")

        # Access data from the 'data' key
        data = playback_context.get("data", {})

        # VOD data
        vod_data = data.get("vod", {})
        if vod_data:
            self.duration = vod_data.get("duration")
            self.orientation = vod_data.get("orientation")
            self.is_drm = vod_data.get("isDrm")

            # DRM info
            drm_info = vod_data.get("drmInfo", {})
            if drm_info and drm_info.get("assertion"):
                self.assertion = drm_info["assertion"]

                if "widevine" in drm_info:
                    self.widevine_license = drm_info["widevine"].get("licenseUrl")
                else:
                    self.widevine_license = None

                if "playready" in drm_info:
                    self.playready_license = drm_info["playready"].get("licenseUrl")
                else:
                    self.playready_license = None

                if "fairplay" in drm_info:
                    self.fairplay_data = drm_info.get("fairplay")
                    self.fairplay_license = self.fairplay_data.get("licenseUrl")
                    self.fairplay_cert = self.fairplay_data.get("certUrl")
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
            hls_data = vod_data.get("hls", {})
            if hls_data:
                self.hls_playback_url = hls_data.get("playbackUrl")
                self.hls_adaptations = hls_data.get("adaptationSet", [])
            else:
                self.hls_playback_url = None
                self.hls_adaptations = []

            # DASH data
            dash_data = vod_data.get("dash", {})
            if dash_data:
                self.dash_playback_url = dash_data.get("playbackUrl")
            else:
                self.dash_playback_url = None

        # Tracking info
        tracking_data = data.get("tracking", {})
        self.tracking_interval = tracking_data.get("trackingPlaybackPollingIntervalSec")

        # Settlement info
        settlement_data = data.get("settlement", {})
        self.settlement_token = settlement_data.get("mediaSettlementToken")
        
        
class LivePlaybackInfo:
    def __init__(self, playback_context):
        # Top-level info
        self.code = playback_context.get("code")
        self.status = playback_context.get("message")

        # Access data from the 'data' key
        data = playback_context.get("data", {})

        # Media info
        media = data.get("media", {})
        self.media_seq = media.get("mediaSeq")
        self.media_id = media.get("mediaId")
        self.media_type = media.get("mediaType")
        self.title = media.get("title")
        self.thumbnail_url = media.get("thumbnailUrl")
        self.published_at = media.get("publishedAt")
        self.community_id = media.get("communityId")
        self.is_fanclub_only = media.get("isFanclubOnly")

        # Live replay info
        live = media.get("live", {})
        self.live_status = live.get("liveStatus")

        replay = live.get("replay", {})
        self.duration = replay.get("duration")
        self.orientation = replay.get("orientation")
        self.is_drm = replay.get("isDrm")
        self.drm_info = replay.get("drmInfo")

        # HLS playback
        hls = replay.get("hls", {})
        self.hls_playback_url = hls.get("playbackUrl")
        self.hls_adaptation_set = []
        for stream in hls.get("adaptationSet", []):
            self.hls_adaptation_set.append({
                "width": stream.get("width"),
                "height": stream.get("height"),
                "playback_url": stream.get("playbackUrl")
            })

        # DASH playback
        dash = replay.get("dash", {})
        self.dash_playback_url = dash.get("playbackUrl")

        # Artist info
        artists = data.get("communityArtists", [])
        self.community_artists = []
        for artist in artists:
            self.community_artists.append({
                "id": artist.get("communityArtistId"),
                "name": artist.get("name"),
                "image_url": artist.get("imageUrl")
            })

        # Tracking
        tracking = data.get("tracking", {})
        self.tracking_interval_sec = tracking.get("trackingPlaybackPollingIntervalSec")

        # Settlement
        settlement = data.get("settlement", {})
        self.settlement_token = settlement.get("mediaSettlementToken")

        # External link
        self.link = data.get("link")

        # Optional rating assessment
        self.video_rating_assessment = data.get("videoRatingAssessment")
