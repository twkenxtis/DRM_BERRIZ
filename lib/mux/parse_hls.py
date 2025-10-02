import asyncio
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from static.color import Color
from unit.handle_log import setup_logging
from unit.http.request_berriz_api import GetRequest

logger = setup_logging('parse_hls', 'periwinkle')

regex_pattern: str = r'#.*|.*\.(?:ts|m4a|m4v|aac)'


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
    video_track: Any
    audio_track: Any
    base_url: Optional[str]
    drm_info: Dict[str, Any]


class HLS_Paser:
    def __init__(self):
        self.m3u8_highest: Optional[str] = None
        self.audio_link: Optional[str] = None
        self.video_is_encrypted: bool = False
        self.video_encryption_key_uri: Optional[str] = None
        self.video_encryption_key: Optional[bytes] = None
        self.audio_is_encrypted: bool = False
        self.audio_encryption_key_uri: Optional[str] = None
        self.audio_encryption_key: Optional[bytes] = None
        self._logged_key_iv: bool = False

    async def make_obj(self, highest_video: Any, highest_audio: Any, base_url: Optional[str]) -> HLSContent:
        return HLSContent(
            video_track=highest_video,
            audio_track=highest_audio,
            base_url=base_url,
            drm_info={},
        )

    async def _parse_media_m3u8(
        self,
        m3u8_content_str: str,
        prefix: str = "video"
    ) -> HLSContent:
        """Main method to parse M3U8 playlist and orchestrate processing."""
        # Master Playlist 分支
        lines: List[str] = self._preprocess_content(m3u8_content_str)
        if self._check_master_playlist(lines):
            prefix = await self._process_master_playlist(lines, m3u8_content_str, prefix)

        # 定義共用 helper：取回並過濾出 ts 與 tag
        async def _fetch_and_filter(url: str) -> List[str]:
            resp = await GetRequest().get_request(url)
            return [line.strip() for line in re.findall(regex_pattern, resp.text) if line.strip()]
        tasks: Dict[str, "asyncio.Task[List[str]]"] = {}
        async with asyncio.TaskGroup() as tg:
            if self.m3u8_highest:
                tasks["video"] = tg.create_task(_fetch_and_filter(self.m3u8_highest), name="video")
            if self.audio_link:
                tasks["audio"] = tg.create_task(_fetch_and_filter(self.audio_link), name="audio")

        video_list: Optional[List[str]] = tasks.get("video").result() if "video" in tasks else None
        audio_list: Optional[List[str]] = tasks.get("audio").result() if "audio" in tasks else None

        video_segments: List[str] = []
        audio_segments: List[str] = []

        if video_list:
            video_segments = await self._process_media_playlist(
                video_list, self.m3u8_highest or "", prefix
            )  # type: ignore[arg-type]

        if audio_list:
            audio_segments = await self._process_media_playlist(
                audio_list, self.audio_link or "", prefix
            )  # type: ignore[arg-type]

        # 組出 base_url 並回傳最終物件
        base_url: Optional[str] = (
            re.sub(r'/\d+/playlist\.m3u8$', '', self.m3u8_highest)
            if self.m3u8_highest else None
        )
        return await self.make_obj(
            tuple(video_segments),
            tuple(audio_segments),
            base_url
        )
    
    def _preprocess_content(self, content: str) -> List[str]:
        """Split and clean M3U8 content into a list of non-empty lines."""
        return [line.strip() for line in content.splitlines() if line.strip()]

    def _check_master_playlist(self, lines: List[str]) -> bool:
        """Determine if the playlist is a master playlist."""
        return any(line.startswith("#EXT-X-STREAM-INF:") for line in lines)
    
    async def _process_master_playlist(
            self, lines: List[str], m3u8_str: str, prefix: str
        ) -> str:
            """Select and parse the best resolution sub-playlist from a master playlist."""
            
            best_height: int = -1
            best_link: Optional[str] = None
            best_info: str = ""
            audio_link: Optional[str] = None
            for i, line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF:"):
                    height: int = self._extract_resolution_height(line)
                    if (
                        height > best_height
                        and i + 1 < len(lines)
                        and not lines[i + 1].startswith("#")
                    ):
                        best_height = height
                        best_link = urljoin(m3u8_str, lines[i + 1])
                        m = re.search(r'URI="([^"]*)"', urljoin(m3u8_str, lines[i-1]))
                        audio_link = m.group(1) if m else None
                        best_info = line

            if best_link:
                logger.info(
                    f"{Color.fg('light_gray')}{prefix}:{Color.reset()} "
                    f"{Color.fg('beige')}{best_info} {Color.reset()}\n"
                    f"{Color.fg('khaki')}choese m3u8: {Color.reset()}"
                    f"{Color.fg('ivory')}{best_link}{Color.reset()} "
                    f"{Color.fg('ivory')}{audio_link}{Color.reset()}"
                )
                if prefix == "video":
                    self.m3u8_highest = best_link
                if audio_link:
                    self.audio_link = audio_link

                return prefix

            logger.error(f"No valid sub-playlist links found for {prefix}")
            return prefix

    async def _process_media_playlist(
        self, lines: List[str], m3u8_url: str, prefix: str
    ) -> List[str]:
        """Extract segments, audio track, and metadata from a media playlist."""
        ts_segments: List[str] = []
        durations: List[float] = []

        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith("#EXT-X-KEY:"):
                self._handle_encryption(line, m3u8_url, prefix)
            elif line.startswith("#EXTINF:"):
                current_duration: float = self._extract_segment_duration(line)
                durations.append(current_duration)
            elif not line.startswith("#") and re.search(r"\.(ts|aac|mp4|m4a|m4v)\b", line):
                segment_url: str = self._process_segment(line, m3u8_url)
                ts_segments.append(segment_url)
        if not durations:
            return []
        
        return self._finalize_results(ts_segments)
    
    def _extract_segment_duration(self, line: str) -> float:
        """Extract segment duration from an EXTINF line."""
        duration_match = re.search(r"^#EXTINF:([\d.]+)", line)
        return float(duration_match.group(1)) if duration_match else 0.0
    
    def _process_segment(self, line: str, m3u8_url: str) -> str:
        """Process a segment line to extract URL and sequence number."""
        segment_url: str = urljoin(m3u8_url, line)
        return segment_url

    def _extract_resolution_height(self, line: str) -> int:
        """Extract the resolution height from a STREAM-INF line."""
        resolution_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
        return int(resolution_match.group(2)) if resolution_match else -1

    def _finalize_results(
        self,
        ts_segments: List[str],
    ) -> List[str]:
        """Sort segments and compute average duration."""
        # Original code sorts by sequence index tuple; here segments are strings, so keep as-is
        return ts_segments

    def _handle_encryption(self, line: str, m3u8_url: str, prefix: str) -> None:
        """Process encryption key information from an EXT-X-KEY line."""
        if "METHOD=AES-128" in line:
            setattr(self, f"{prefix}_is_encrypted", True)
            uri_match = re.search(r'URI="([^"]+)"', line)
            if uri_match:
                key_uri: str = urljoin(m3u8_url, uri_match.group(1))
                setattr(self, f"{prefix}_encryption_key_uri", key_uri)
                logger.info(
                    f"{Color.fg('ruby')}{prefix}{Color.reset()} {Color.fg('light_gray')}encryption key URI: {Color.reset()} "
                    f"{Color.fg('bright_cyan')}{key_uri}{Color.reset()}"
                )
        if "METHOD=SAMPLE-AES" in line:
            key_format: Optional[str] = re.search(r'KEYFORMAT="([^"]+)"', line).group(1) if re.search(r'KEYFORMAT="([^"]+)"', line) else None
            if key_format == 'com.apple.streamingkeydelivery':
                logger.info(
                    f"{Color.fg('light_gray')}encryption support:{Color.reset()} "
                    f"{Color.fg('bright_cyan')}FairPlay{Color.reset()}"
                )
        else:
            logger.warning(f"Unsupported {prefix} encryption method: {line}")