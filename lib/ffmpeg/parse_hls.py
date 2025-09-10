import re
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse, urljoin

from unit.handle_log import setup_logging

from static.color import Color
from unit.http.request_berriz_api import GetRequest


logger = setup_logging('parse_hls', 'periwinkle')

@dataclass
class Segment:
    t: int
    d: int
    r: int


@dataclass
class MediaTrack:
    id: str
    bandwidth: int
    codecs: str
    segments: List[Segment]
    init_url: str
    segment_urls: List[str]
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    timescale: Optional[int] = None
    audio_sampling_rate: Optional[int] = None


@dataclass
class HLSContent:
    video_track: MediaTrack
    audio_track: MediaTrack
    base_url: str
    drm_info: Dict


class HLS_Paser:
    def __init__(self):
        self.m3u8_highest = None
        self.video_is_encrypted = False
        self.video_encryption_key_uri: Optional[str] = None
        self.video_encryption_key: Optional[bytes] = None
        self.audio_is_encrypted = False
        self.audio_encryption_key_uri: Optional[str] = None
        self.audio_encryption_key: Optional[bytes] = None
        self._logged_key_iv = False

    async def make_obj(self, highest_video, highest_audio, base_url):
        return HLSContent(
            video_track=highest_video,
            audio_track=highest_audio,
            base_url=base_url,
            drm_info={},
        )

    async def _parse_media_m3u8(self, m3u8_content_str: str, prefix: str = "video") -> Tuple[List[Tuple[str, int, float]], Optional[str], bool, float]:
        """Main method to parse M3U8 playlist and orchestrate processing."""
        list_m3u8 = self._preprocess_content(m3u8_content_str)
        if self._check_master_playlist(list_m3u8):
            prefix = await self._process_master_playlist(list_m3u8, m3u8_content_str, prefix)
            
        playlist = await GetRequest().get_request(self.m3u8_highest)
        playlist = playlist.text
        playlist = [line.strip() for line in re.findall(r'#.*|.*\.ts', playlist) if line.strip()]
        ts_segments, audio_url = await self._process_media_playlist(playlist, self.m3u8_highest, prefix)
        base_url = re.sub(r'/\d+/playlist\.m3u8$', '', self.m3u8_highest)
        return await self.make_obj(tuple(ts_segments), audio_url, base_url)
        
    
    def _preprocess_content(self, content: str) -> List[str]:
        """Split and clean M3U8 content into a list of non-empty lines."""
        return [line.strip() for line in content.splitlines() if line.strip()]

    def _check_master_playlist(self, lines: List[str]) -> bool:
        """Determine if the playlist is a master playlist."""
        return any(line.startswith("#EXT-X-STREAM-INF:") for line in lines)
    
    async def _process_master_playlist(
            self, lines: List[str], m3u8_str: str, prefix: str
        ) -> Tuple[List[Tuple[str, int, float]], Optional[str], bool, float]:
            """Select and parse the best resolution sub-playlist from a master playlist."""
            
            best_height, best_link, best_info = -1, None, ""
            for i, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF:"):
                    height = self._extract_resolution_height(line)
                    if (
                        height > best_height
                        and i + 1 < len(lines)
                        and not lines[i + 1].startswith("#")
                    ):
                        best_height = height
                        best_link = urljoin(m3u8_str, lines[i + 1])
                        best_info = line

            if best_link:
                logger.info(
                    f"{Color.fg('light_gray')}{prefix}:{Color.reset()} "
                    f"{Color.fg('beige')}{best_info} {Color.reset()}\n"
                    f"{Color.fg('khaki')}choese m3u8: {Color.reset()}"
                    f"{Color.fg('ivory')}{best_link}{Color.reset()}"
                )
                if prefix == "video":
                    self.m3u8_highest = best_link

                return prefix

            logger.error(f"No valid sub-playlist links found for {prefix}")
            return [], None, False, 0.0

    async def _process_media_playlist(
        self, lines: List[str], m3u8_url: str, prefix: str
    ) -> Tuple[List[Tuple[str, int, float]], Optional[str], bool, float]:
        """Extract segments, audio track, and metadata from a media playlist."""
        ts_segments = []
        audio_url = None
        durations = []

        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith("#EXT-X-MEDIA:TYPE=AUDIO") and prefix == "video":
                audio_url = self._extract_audio_url(line, m3u8_url)
            elif line.startswith("#EXT-X-KEY:"):
                self._handle_encryption(line, m3u8_url, prefix)
            elif line.startswith("#EXTINF:"):
                current_duration = self._extract_segment_duration(line)
                durations.append(current_duration)
            elif not line.startswith("#") and re.search(r"\.(ts|aac|mp4|m4a|m4v)\b", line):
                segment_url= self._process_segment(line, m3u8_url)
                ts_segments.append(segment_url)
        if not durations:
            return (), None, False
        
        return self._finalize_results(ts_segments, audio_url)
    
    def _extract_segment_duration(self, line: str) -> float:
        """Extract segment duration from an EXTINF line."""
        duration_match = re.search(r"^#EXTINF:([\d.]+)", line)
        return float(duration_match.group(1)) if duration_match else 0
    
    def _process_segment(self, line: str, m3u8_url: str) -> Tuple[str, int]:
        """Process a segment line to extract URL and sequence number."""
        segment_url = urljoin(m3u8_url, line)
        return segment_url

    def _extract_resolution_height(self, line: str) -> int:
        """Extract the resolution height from a STREAM-INF line."""
        resolution_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
        return int(resolution_match.group(2)) if resolution_match else -1

    def _finalize_results(
        self,
        ts_segments: List[Tuple[str, int, float]],
        audio_url: Optional[str],
    ) -> Tuple[List[Tuple[str, int, float]], Optional[str], bool, float]:
        """Sort segments and compute average duration."""
        ts_segments.sort(key=lambda x: x[1])
        return ts_segments, audio_url

    def _extract_audio_url(self, highest_url: str) -> Optional[str]:
        """Extract audio track URL from an EXT-X-MEDIA line."""
        uri_match = re.search(r'URI="([^"]+)"', highest_url)
        if uri_match:
            audio_url = urljoin(highest_url, uri_match.group(1))
            logger.info(f"Found audio track: {audio_url}")
            return audio_url
        return None

    def _handle_encryption(self, line: str, m3u8_url: str, prefix: str) -> None:
        """Process encryption key information from an EXT-X-KEY line."""
        if "METHOD=AES-128" in line:
            setattr(self, f"{prefix}_is_encrypted", True)
            uri_match = re.search(r'URI="([^"]+)"', line)
            if uri_match:
                key_uri = urljoin(m3u8_url, uri_match.group(1))
                setattr(self, f"{prefix}_encryption_key_uri", key_uri)
                logger.info(
                    f"{Color.fg('ruby')}{prefix}{Color.reset()} {Color.fg('light_gray')}encryption key URI: {Color.reset()} "
                    f"{Color.fg('bright_cyan')}{key_uri}{Color.reset()}"
                )
        if "METHOD=SAMPLE-AES" in line:
            key_format = re.search(r'KEYFORMAT="([^"]+)"', line).group(1) if re.search(r'KEYFORMAT="([^"]+)"', line) else None
            if key_format == 'com.apple.streamingkeydelivery':
                logger.info(
                    f"{Color.fg('light_gray')}encryption support:{Color.reset()} "
                    f"{Color.fg('bright_cyan')}FairPlay{Color.reset()}"
                )
        else:
            logger.warning(f"Unsupported {prefix} encryption method: {line}")