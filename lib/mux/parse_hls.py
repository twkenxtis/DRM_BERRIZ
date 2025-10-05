import asyncio
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from rich.console import Console
from rich.table import Table
from rich import box

from static.color import Color
from unit.handle.handle_log import setup_logging
from unit.http.request_berriz_api import GetRequest


logger = setup_logging('parse_hls', 'periwinkle')


REGEX_HLS_PATTERN: str = r'#.*|.*\.(?:ts|mp4|m4a|m4v|aac)'


@dataclass
class HLSContent:
    video_track: Any
    audio_track: Any
    base_url: Optional[str]
    audio_link: str
    best_info: str


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

    def make_obj(self, highest_video: Any, highest_audio: Any, base_url: Optional[str], best_info:str) -> HLSContent:
        return HLSContent(
            video_track=highest_video,
            audio_track=highest_audio,
            base_url=base_url,
            audio_link=self.audio_link,
            best_info=best_info
        )

    async def _parse_media_m3u8(
        self,
        m3u8_content_str: str,
    ) -> HLSContent:
        """Main method to parse M3U8 playlist and orchestrate processing."""
        # Master Playlist 分支
        lines: List[str] = self._preprocess_content(m3u8_content_str)
        if self._check_master_playlist(lines):
            best_info = await self._process_master_playlist(lines, m3u8_content_str)

        # 定義共用 helper：取回並過濾出 ts 與 tag
        async def _fetch_and_filter(url: str) -> List[str]:
            resp = await GetRequest().get_request(url)
            return [line.strip() for line in re.findall(REGEX_HLS_PATTERN, resp.text) if line.strip()]
        tasks: Dict[str, "asyncio.Task[List[str]]"] = {}
        async with asyncio.TaskGroup() as tg:
            if self.m3u8_highest:
                tasks["video"] = tg.create_task(_fetch_and_filter(self.m3u8_highest), name="video")
            if self.audio_link:
                tasks["audio"] = tg.create_task(_fetch_and_filter(self.audio_link), name="audio")

        video_list: Optional[List[str]] = tasks.get("video").result() if "video" in tasks else None
        audio_list: Optional[List[str]] = tasks.get("audio").result() if "audio" in tasks else None

        video_segments: tuple[str] = []
        audio_segments: tuple[str] = []

        if video_list:
            video_segments = self._process_media_playlist(video_list, self.m3u8_highest or "")
        elif audio_list:
            audio_segments = self._process_media_playlist(audio_list, self.audio_link or "")

        # 組出 base_url 並回傳最終物件
        base_url: Optional[str] = (
            re.sub(r'/\d+/playlist\.m3u8$', '', self.m3u8_highest)
            if self.m3u8_highest else None
        )
        return self.make_obj(
            tuple(video_segments),
            tuple(audio_segments),
            base_url,
            best_info
        )
    
    def _preprocess_content(self, content: str) -> List[str]:
        """Split and clean M3U8 content into a list of non-empty lines."""
        return [line.strip() for line in content.splitlines() if line.strip()]

    def _check_master_playlist(self, lines: List[str]) -> bool:
        """Determine if the playlist is a master playlist."""
        return any(line.startswith("#EXT-X-STREAM-INF:") for line in lines)
    
    async def _process_master_playlist(
            self, lines: List[str], m3u8_str: str
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
                self.m3u8_highest = best_link
                if audio_link:
                    self.audio_link = audio_link
                return best_info

            return ""

    def _process_media_playlist(
        self, lines: List[str], m3u8_url: str
    ) -> List[str]:
        """Extract segments, audio track, and metadata from a media playlist."""
        ts_segments: List[str] = []
        durations: List[float] = []

        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith("#EXT-X-KEY:"):
                self._handle_encryption(line, m3u8_url)
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

    def _handle_encryption(self, line: str, m3u8_url: str) -> None:
        """Process encryption key information from an EXT-X-KEY line."""
        if "METHOD=AES-128" in line:
            prefix: str = "video" if "URI" in line else "audio"
            setattr(self, f"{prefix}_is_encrypted", True)
            uri_match = re.search(r'URI="([^"]+)"', line)
            if uri_match:
                key_uri: str = urljoin(m3u8_url, uri_match.group(1))
                setattr(self, f"{prefix}_encryption_key_uri", key_uri)
                logger.info(
                    f"{Color.fg('ruby')}{prefix}{Color.reset()} {Color.fg('light_gray')}encryption key URI: {Color.reset()} "
                    f"{Color.fg('bright_cyan')}{key_uri}{Color.reset()}"
                )
        elif "METHOD=SAMPLE-AES" in line:
            key_format: Optional[str] = re.search(r'KEYFORMAT="([^"]+)"', line).group(1) if re.search(r'KEYFORMAT="([^"]+)"', line) else None
            if key_format == 'com.apple.streamingkeydelivery':
                logger.info(
                    f"{Color.fg('light_gray')}encryption support:{Color.reset()} "
                    f"{Color.fg('bright_cyan')}FairPlay{Color.reset()}"
                )
        else:
            logger.warning(f"Unsupported {prefix} encryption method: {line}")
            
    def rich_table_print(self, obj: HLSContent):
        """Print rich table of HLS content."""
        console = Console()
        
        info = obj.best_info.split(":", 1)[1]
        pairs = [p.strip() for p in info.split(",")]
        kv = {}
        for p in pairs:
            if "=" in p:
                k, v = p.split("=", 1)
                kv[k.strip()] = v.strip('"')

        table = Table(
            title="HLS Parsing Result",
            box=box.ROUNDED,
            show_header=False,
            border_style="bright_blue",
        )

        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        colored_values = []
        for key, value in kv.items():
            color = {
                "BANDWIDTH": "orange_red1",
                "CODECS": "light_salmon1",
                "AUDIO": "light_steel_blue",
                "RESOLUTION": "light_goldenrod2",
            }.get(key, "white")
            colored_values.append(f"[{color}]{value}[/]")

        joined_values = " | ".join(colored_values)
        table.add_row("[bold magenta]INFO[/bold magenta]", joined_values)
        table.add_row("[bold yellow]Playlist[/bold yellow]", f"[cornsilk1]{obj.base_url}[/]")
        table.add_row("[bold blue]Audio Link[/bold blue]", f"[cornsilk1]{obj.audio_link}[/]")

        console.print(table)