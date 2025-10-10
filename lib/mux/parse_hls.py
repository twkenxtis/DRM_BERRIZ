import asyncio
import re
from pprint import pprint
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from InquirerPy import inquirer
from rich.console import Console
from rich.table import Table
from rich import box

from lib.__init__ import use_proxy, CFG
from static.parameter import paramstore
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
    video_link: str
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
        self.GetRequest = GetRequest()

    def make_obj(self, highest_video: Any, highest_audio: Any, base_url: Optional[str], best_info:str) -> HLSContent:
        try:
            return HLSContent(
                video_track=highest_video,
                audio_track=highest_audio,
                base_url=base_url,
                audio_link=self.audio_link,
                video_link=self.m3u8_highest,
                best_info=best_info
            )
        except AttributeError:
            pass

    async def _parse_media_m3u8(self, m3u8_content_str: str) -> HLSContent:
        """Main method to parse M3U8 playlist and orchestrate processing"""
        # Master Playlist 分支
        lines: List[str] = self._preprocess_content(m3u8_content_str)
        v_resolution_choice: str = CFG['HLS or MPEG-DASH']['Video_Resolution_Choice']
        a_resolution_choice: str = CFG['HLS or MPEG-DASH']['Audio_Resolution_Choice']
        try:
            if self._check_master_playlist(lines):
                best_info = await self._process_master_playlist(lines, m3u8_content_str, v_resolution_choice, a_resolution_choice)
        except ValueError as e:
            logger.error(f"Error parsing master playlist: {e}")
            return None
            
        # 定義共用 helper：取回並過濾出 ts 與 tag
        async def _fetch_and_filter(url: str) -> List[str]:
            resp = await self.GetRequest.get_request(url, use_proxy)
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
        # 不可使用elif，避免條件只符合一個就退出判斷
        if audio_list:
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
        """Split and clean M3U8 content into a list of non-empty lines"""
        return [line.strip() for line in content.splitlines() if line.strip()]

    def _check_master_playlist(self, lines: List[str]) -> bool:
        """Determine if the playlist is a master playlist."""
        return any(line.startswith("#EXT-X-STREAM-INF:") for line in lines)
    
    async def _select_video_track(
        self, lines: List[str], m3u8_str: str, v_resolution_choice: str) -> Optional[str]:
        """Select video track based on user choice or input"""
        if v_resolution_choice.lower() == "none":
            return None
        
        resolution_list: List[Tuple[int, int]] = self.extract_sorted_resolutions(lines)
        if v_resolution_choice.lower() in {"ask", "as"}:
            choices = [f"{w}x{h}" for w, h in resolution_list]
            print(choices)
            answer = await inquirer.select(
                message="Select video resolution:",
                choices=choices,
                default=choices[-1]
            ).execute_async()
            selected_resolution = tuple(map(int, answer.split("x")))
        elif v_resolution_choice.isdigit():
            target_height = int(v_resolution_choice)
            filtered = [(w, h) for w, h in resolution_list if target_height in (w, h)]
            if not filtered:
                raise ValueError(f"No resolution found with height {target_height}")
            selected_resolution = filtered[0]
        else:
            raise ValueError(f"Invalid resolution choice: {v_resolution_choice}")
        
        # Find the corresponding playlist link
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF:"):
                resolutions = self.extract_all_resolutions(line)
                if selected_resolution in resolutions:
                    if i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                        best_link = urljoin(m3u8_str, lines[i + 1])
                        self.m3u8_highest = best_link
                        return line
        
        raise ValueError(f"Resolution {selected_resolution} not found in playlist")

    async def _select_audio_track(self, lines: List[str], m3u8_str: str, choice: str) -> Optional[str]:
        """選擇 HLS 音訊 URI，支援 ask 或 bitrate 匹配，找不到則 fallback 第一軌"""

        # 抽出所有 EXT-X-MEDIA 音訊軌道
        audio_tracks = []
        for line in lines:
            if line.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in line:
                uri_match = re.search(r'URI="([^"]+)"', line)
                name_match = re.search(r'NAME="([^"]+)"', line)
                bandwidth = self._extract_bandwidth_kbps(line)
                if uri_match:
                    uri = urljoin(m3u8_str, uri_match.group(1))
                    name = name_match.group(1) if name_match else uri
                    audio_tracks.append((bandwidth, name, uri))

        if not audio_tracks:
            return None
        
        if choice == "none":
            return []
        
        if choice.lower() in {"ask", "as"}:
            choices = [f"{name} ({bw}) - {link}" for bw, name, link in audio_tracks]
            answer = await inquirer.select(
                message="Select audio stream:",
                choices=choices,
                default=choices[0]
            ).execute_async()
            selected = next(uri for bw, name, uri in audio_tracks if name in answer)
            return selected

        elif choice.isdigit():
            target_kbps = int(choice)
            matched = [uri for bw, _, uri in audio_tracks if bw == target_kbps]
            return matched[0] if matched else audio_tracks[0][2]

        raise ValueError(f"Invalid audio choice: {choice}")

    def _extract_bandwidth_kbps(self, line: str) -> int:
        """從 EXT-X-MEDIA 標籤中抽出 BANDWIDTH（以 kbps 回傳）"""
        bw_match = re.search(r'BANDWIDTH=(\d+)', line)
        if bw_match:
            return int(bw_match.group(1)) // 1000
        return 0

    async def _process_master_playlist(
        self, lines: List[str], m3u8_str: str, v_resolution_choice: str, a_resolution_choice: str) -> str:
        """Select and parse a specific resolution sub-playlist from a master playlist"""
        # Select audio track
        if a_resolution_choice != "none": 
            paramstore._store["hls_audio"] = True
            audio_line = await self._select_audio_track(lines, m3u8_str, a_resolution_choice)
            self.audio_link = audio_line
        else:
            paramstore._store["hls_audio"] = False
        # Select video track
        if v_resolution_choice != "none": 
            paramstore._store["hls_video"] = True
            video_line = await self._select_video_track(lines, m3u8_str, v_resolution_choice)
            return video_line # EXT-X--STREAM-INFO # Video_link at funcation not here
        else:
            paramstore._store["hls_video"] = False

    def extract_sorted_resolutions(self, lines: List[str]) -> List[Tuple[int, int]]:
        """Extract all resolution pairs (width, height) from the playlist, sorted by height ascending. Duplicates preserved."""
        resolutions: List[Tuple[int, int]] = []
        for line in lines:
            if line.startswith("#EXT-X-STREAM-INF:"):
                matches = re.findall(r"RESOLUTION=(\d+)x(\d+)", line)
                for w, h in matches:
                    resolutions.append((int(w), int(h)))
        return sorted(resolutions, key=lambda r: r[1])

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
    
    def extract_all_resolutions(self, text: str) -> List[Tuple[int, int]]:
        """Extract all resolution pairs (width, height) from the input text, preserving duplicates and order."""
        matches = re.findall(r"RESOLUTION=(\d+)x(\d+)", text)
        return [(int(w), int(h)) for w, h in matches]
    
    def extract_all_audio_tracks(self, lines: List[str], m3u8_str: str) -> List[str]:
        """Extract all audio track URIs from the playlist, preserving order."""
        audio_links = []
        for line in lines:
            if line.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in line:
                m = re.search(r'URI="([^"]+)"', line)
                if m:
                    audio_links.append(urljoin(m3u8_str, m.group(1)))
        return audio_links

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
        """Print rich table of HLS content"""
        try:
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
                    "CODECS": "light_salmon1",
                    "BANDWIDTH": "orange_red1",
                    "RESOLUTION": "light_goldenrod2",
                    "AUDIO": "light_steel_blue",
                }.get(key, "white")
                colored_values.append(f"[{color}]{value}[/]")

            joined_values = " | ".join(colored_values)
            table.add_row("[bold magenta]INFO[/bold magenta]", joined_values)
            table.add_row("[bold yellow]Base Url[/bold yellow]", f"[cornsilk1]{obj.base_url}[/]")
            table.add_row("[bold cyan]Video Link[/bold cyan]", f"[cornsilk1]{obj.video_link}[/]")
            table.add_row("[bold blue]Audio Link[/bold blue]", f"[cornsilk1]{obj.audio_link}[/]")

            console.print(table)
        except AttributeError:
            pass