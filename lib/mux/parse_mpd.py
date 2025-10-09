import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from rich import box
from rich.console import Console
from rich.table import Table
from InquirerPy import inquirer

from static.parameter import paramstore
from unit.handle.handle_log import setup_logging


logger = setup_logging('parse_mpd', 'periwinkle')


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
class MPDContent:
    video_track: Optional[MediaTrack]
    audio_track: Optional[MediaTrack]
    base_url: str
    drm_info: Dict[str, Any]


class MPDParser:
    mpd_url: str
    root: ET.Element
    namespaces: Dict[str, str]

    def __init__(self, raw_mpd_text: Any, mpd_url: str):
        self.mpd_url: str = mpd_url
        self.root: ET.Element = self._parse_xml(raw_mpd_text)
        self.namespaces: Dict[str, str] = {
            "": "urn:mpeg:dash:schema:mpd:2011",
            "cenc": "urn:mpeg:cenc:2013",
            "mspr": "urn:microsoft:playready",
        }

    def _parse_xml(self, obj: object) -> ET.Element:
        """解析 XML 文本為 ElementTree Element"""
        if hasattr(obj, 'text'):
            xml_text = getattr(obj, 'text')
            if not isinstance(xml_text, str):
                raise TypeError(f"Expected text attribute to be str, got {type(xml_text)}")
            return ET.fromstring(xml_text)
        raise TypeError(f"Object must have 'text' attribute, got {type(obj)}")

    def _get_required_attr(self, element: ET.Element, attr: str, elem_name: str = "Element") -> str:
        """獲取必需屬性，若缺失則拋出描述性錯誤"""
        value = element.get(attr)
        if value is None:
            raise ValueError(f"{elem_name} missing required attribute '{attr}'")
        return value

    def _get_int_attr(
        self, element: ET.Element, attr: str, default: Optional[int] = None
    ) -> Optional[int]:
        """安全獲取整數屬性"""
        value = element.get(attr)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"Invalid integer value '{value}' for attribute '{attr}'")

    def _parse_drm_info(self) -> Dict[str, Any]:
        """從 MPD 解析 DRM/ContentProtection 資訊"""
        drm_info: Dict[str, Any] = {}

        # 解析 default_KID
        kid_prot = self.root.find(
            ".//ContentProtection[@schemeIdUri='urn:mpeg:dash:mp4protection:2011']",
            self.namespaces,
        )
        if kid_prot is not None:
            kid_raw = kid_prot.get("{urn:mpeg:cenc:2013}default_KID", "")
            kid = kid_raw.strip().replace('-', '')
            if len(kid) == 32:
                drm_info["default_KID"] = kid

        # 解析 PlayReady
        playready_prot = self.root.find(
            ".//ContentProtection[@schemeIdUri='urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95']",
            self.namespaces,
        )
        if playready_prot is not None:
            pro_value = playready_prot.findtext("./mspr:pro", "", namespaces=self.namespaces)
            if pro_value:
                drm_info["playready_pssh"] = pro_value

        # 解析 Widevine
        widevine_prot = self.root.find(
            ".//ContentProtection[@schemeIdUri='urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed']",
            self.namespaces,
        )
        if widevine_prot is not None:
            pssh_value = widevine_prot.findtext("./cenc:pssh", "", namespaces=self.namespaces)
            if pssh_value and len(pssh_value) == 76 and pssh_value.endswith("="):
                drm_info["widevine_pssh"] = pssh_value
        return drm_info

    def _parse_segment_timeline(self, seg_template: ET.Element) -> List[Segment]:
        """解析 SegmentTimeline 為 Segment 列表"""
        seg_timeline = seg_template.find("./SegmentTimeline", self.namespaces)
        if seg_timeline is None:
            return []

        segments = []
        for s_elem in seg_timeline.findall("./S", self.namespaces):
            try:
                t = self._get_int_attr(s_elem, "t", default=0)
                d = self._get_int_attr(s_elem, "d")
                r = self._get_int_attr(s_elem, "r", default=0)

                if d is None:
                    raise ValueError("Segment 'S' element missing required 'd' attribute")

                segments.append(Segment(t=t, d=d, r=r))
            except ValueError as e:
                logger.warning(f"Warning: Skipping invalid segment: {e}")
                continue
        return segments

    def _generate_segment_urls(
        self, rep_id: str, media_template: str, segments: List[Segment], base_url: str
    ) -> List[str]:
        """生成所有片段的 URL 列表"""
        segment_urls: List[str] = []
        for seg in segments:
            current_time: int = seg.t
            for _ in range(seg.r + 1):
                url: str = media_template.replace("$RepresentationID$", rep_id).replace(
                    "$Time$", str(current_time)
                )
                segment_urls.append(urljoin(base_url, url))
                current_time += seg.d
        return segment_urls

    def _parse_representation(
        self,
        rep: ET.Element,
        adapt_set: ET.Element,
        base_url: str,
    ) -> Optional[MediaTrack]:
        """解析單個 Representation 為 MediaTrack"""
        seg_template: Optional[ET.Element] = rep.find(
            "./SegmentTemplate", self.namespaces
        ) or adapt_set.find("./SegmentTemplate", self.namespaces)

        if seg_template is None:
            return None

        segments: List[Segment] = self._parse_segment_timeline(seg_template)

        # 安全屬性提取
        rep_id = self._get_required_attr(rep, "id", "Representation")
        bandwidth = self._get_int_attr(rep, "bandwidth")
        if bandwidth is None:
            raise ValueError(f"Representation {rep_id} missing required 'bandwidth'")

        codecs = self._get_required_attr(rep, "codecs", f"Representation {rep_id}")

        # 模板 URL
        init_template = seg_template.get("initialization")
        if not init_template:
            raise ValueError(f"SegmentTemplate missing 'initialization' attribute")

        media_template = seg_template.get("media")
        if not media_template:
            raise ValueError(f"SegmentTemplate missing 'media' attribute")

        init_url: str = urljoin(
            base_url,
            init_template.replace("$RepresentationID$", rep_id),
        )

        segment_urls: List[str] = self._generate_segment_urls(
            rep_id, media_template, segments, base_url
        )

        # 可選屬性處理
        width = self._get_int_attr(rep, "width")
        height = self._get_int_attr(rep, "height")
        audio_sampling_rate = self._get_int_attr(rep, "audioSamplingRate")
        timescale = self._get_int_attr(seg_template, "timescale", default=1)

        mime_type = adapt_set.get("mimeType", "")

        return MediaTrack(
            id=rep_id,
            bandwidth=bandwidth,
            codecs=codecs,
            segments=segments,
            init_url=init_url,
            segment_urls=segment_urls,
            mime_type=mime_type,
            width=width,
            height=height,
            timescale=timescale,
            audio_sampling_rate=audio_sampling_rate,
        )

    async def get_selected_mpd_content(self, v_resolution_choice: str, a_resolution_choice: str) -> MPDContent:
        """根據使用者選擇的解析度與音訊軌道 提取 MPD 中對應內容"""
        base_url: str = self.mpd_url.rsplit("/", 1)[0] + "/"

        period = self.root.find("./Period", self.namespaces)
        if period is None:
            raise ValueError("MPD contains no Period elements")

        video_reps: List[MediaTrack] = []
        audio_reps: List[MediaTrack] = []

        for adapt_set in period.findall("./AdaptationSet", self.namespaces):
            mime_type = adapt_set.get("mimeType", "")

            for rep_element in adapt_set.findall("./Representation", self.namespaces):
                try:
                    track = self._parse_representation(rep_element, adapt_set, base_url)
                    if track is None:
                        continue

                    if mime_type.startswith("video"):
                        video_reps.append(track)
                    elif mime_type.startswith("audio"):
                        audio_reps.append(track)
                except (ValueError, TypeError) as e:
                    rep_id = rep_element.get("id", "unknown")
                    logger.warning(f"Warning: Failed to parse Representation {rep_id}: {e}")
                    continue

        # 分離的選擇邏輯
        selected_video = MediaTrack(id='', bandwidth=0, codecs='', segments=[], init_url='', segment_urls=[], mime_type='', width=0, height=0, timescale=0, audio_sampling_rate=0)
        selected_audio = MediaTrack(id='', bandwidth=0, codecs='', segments=[], init_url='', segment_urls=[], mime_type='', width=0, height=0, timescale=0, audio_sampling_rate=0)
        
        if a_resolution_choice != "none":
            paramstore._store["mpd_audio"] = True
            selected_audio = await self._select_audio_track(audio_reps, a_resolution_choice)
        else:
            paramstore._store["mpd_audio"] = False
            
        if v_resolution_choice != "none":
            paramstore._store["mpd_video"] = True
            selected_video = await self._select_video_track(video_reps, v_resolution_choice)
        else:
            paramstore._store["mpd_video"] = False
            
        drm_info = self._parse_drm_info()
        
        return MPDContent(
            video_track=selected_video,
            audio_track=selected_audio,
            base_url=base_url,
            drm_info=drm_info,
        )


    async def _select_audio_track(self, audio_reps: List[MediaTrack], a_resolution_choice: str) -> Optional[MediaTrack]:
        """選擇音訊軌道"""
        audio_rates = [(t.bandwidth, t.audio_sampling_rate, t.id) for t in audio_reps if t.audio_sampling_rate]

        if not audio_rates:
            return None

        if str(a_resolution_choice).lower() in ("ask", "as"):
            choices = [f"{id} ({bandwidth // 1000}kbps / {rate}Hz)" for bandwidth, rate, id in audio_rates]
            answer = await inquirer.select(
                message="Select audio track:",
                choices=choices,
                default=choices[0]
            ).execute_async()
            return next(t for t in audio_reps if t.id in answer)
        
        elif str(a_resolution_choice).isdigit():
            target_kbps = int(a_resolution_choice)
            matched = [
                t for t in audio_reps
                if t.bandwidth and (t.bandwidth // 1000) == target_kbps
            ]
            if not matched:
                raise ValueError(f"No audio track found with bandwidth {target_kbps}kbps")
            return matched[0]
        
        else:
            raise ValueError(f"Invalid audio resolution choice: {a_resolution_choice}")


    async def _select_video_track(self, video_reps: List[MediaTrack], v_resolution_choice: str) -> MediaTrack:
        """選擇影像軌道"""
        resolution_list = [(t.width, t.height) for t in video_reps if t.width and t.height]
        
        if v_resolution_choice.lower() == "ask":
            choices = [f"{w}x{h}" for w, h in resolution_list]
            answer = await inquirer.select(
                message="Select video resolution:",
                choices=choices,
                default=choices[-1]
            ).execute_async()
            selected_resolution = tuple(map(int, answer.split("x")))
        
        elif v_resolution_choice.isdigit():
            target = int(v_resolution_choice)
            matched = [res for res in resolution_list if target in res]
            if not matched:
                raise ValueError(f"Resolution {v_resolution_choice} not found")
            selected_resolution = matched[0]
        
        else:
            raise ValueError(f"Invalid resolution choice: {v_resolution_choice}")

        selected_video = next(
            (t for t in video_reps if (t.width, t.height) == selected_resolution),
            None
        )
        if not selected_video:
            raise ValueError(f"No video track found for resolution {selected_resolution}")
        
        return selected_video


    def validate_mpd_structure(self) -> List[str]:
        """Validate MPD structure and return warnings/errors list"""
        issues = []

        if self.root.find("./Period", self.namespaces) is None:
            issues.append("ERROR: No Period element found")
        return issues

    def rich_table_print(self, mpd_content: Optional[MPDContent] = None) -> None:
        """Print MPD content details using a single Rich Table"""
        try:
            console = Console()

            table = Table(
                title="MPEG-DASH MPD Parsing Result",
                box=box.ROUNDED,
                show_header=False,
                border_style="bright_blue",
            )

            table.add_column("Field", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")

            table.add_row("[bold magenta]Basic Info[/bold magenta]", "")
            table.add_row("MPD URL", mpd_content.base_url)
            table.add_row("Video Track", "[green]Present[/green]" if mpd_content.video_track else "[red]Not Present[/red]")
            table.add_row("Audio Track", "[green]Present[/green]" if mpd_content.audio_track else "[red]Not Present[/red]")

            if mpd_content.video_track:
                vt = mpd_content.video_track
                table.add_row("[bold green]Video Track Info[/bold green]", "")
                table.add_row("ID", f"[cyan]{vt.id}[/]")
                table.add_row("Bandwidth", f"[orange_red1]{vt.bandwidth:,}[/] bps")
                table.add_row("Codec", f"[light_salmon1]{vt.codecs}[/]")
                table.add_row("MIME Type", f"[light_goldenrod2]{vt.mime_type}[/]")
                table.add_row("Resolution", f"[green]{vt.width} × {vt.height}[/]" if vt.width and vt.height else "[red]N/A[/]")
                table.add_row("Timescale", f"[yellow]{vt.timescale}[/]" if vt.timescale else "[red]N/A[/]")
                table.add_row("Segment Count", f"[magenta]{len(vt.segments)}[/]")
                table.add_row("URL Count", f"[magenta]{len(vt.segment_urls)}[/]")
                table.add_row("Init URL", f"[white]{vt.init_url}[/]")

                if mpd_content.audio_track:
                    at = mpd_content.audio_track
                    table.add_row("[bold blue]Audio Track Info[/bold blue]", "")
                    table.add_row("ID", f"[cyan]{at.id}[/]")
                    table.add_row("Bandwidth", f"[orange_red1]{at.bandwidth:,}[/] bps")
                    table.add_row("Codec", f"[light_salmon1]{at.codecs}[/]")
                    table.add_row("MIME Type", f"[light_goldenrod2]{at.mime_type}[/]")
                    table.add_row("Sampling Rate", f"[green]{at.audio_sampling_rate} Hz[/]" if at.audio_sampling_rate else "[red]N/A[/]")
                    table.add_row("Timescale", f"[yellow]{at.timescale}[/]" if at.timescale else "[red]N/A[/]")
                    table.add_row("Segment Count", f"[magenta]{len(at.segments)}[/]")
                    table.add_row("URL Count", f"[magenta]{len(at.segment_urls)}[/]")
                    table.add_row("Init URL", f"[white]{at.init_url}[/]")


            if mpd_content.drm_info:
                table.add_row("[bold red]DRM Protection Info[/bold red]", "")
                for key, value in mpd_content.drm_info.items():
                    display_value = value
                    table.add_row(key, display_value)

            if mpd_content.video_track and mpd_content.video_track.segments:
                table.add_row("[bold yellow]Video Segment Info (first 5)[/bold yellow]", "")
                for idx, seg in enumerate(mpd_content.video_track.segments[:5], 1):
                    table.add_row(f"Segment {idx}", f"t={seg.t}, d={seg.d}, r={seg.r}")
                if len(mpd_content.video_track.segments) > 5:
                    table.add_row("...", f"[dim]{len(mpd_content.video_track.segments) - 5} more segments[/dim]")

            issues = self.validate_mpd_structure()
            if issues:
                table.add_row("[bold red]Validation Issues[/bold red]", "")
                for issue in issues:
                    table.add_row("•", issue)

            console.print(table)
        except AttributeError:
            pass