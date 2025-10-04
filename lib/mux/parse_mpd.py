from dataclasses import dataclass
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from typing import Dict, List, Optional, Any, Callable, Union


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
    # 屬性類型註釋
    mpd_url: str
    root: ET.Element
    namespaces: Dict[str, str]

    def __init__(self, raw_mpd_text: Any, mpd_url: str):
        self.mpd_url: str = mpd_url
        self.root: ET.Element = self.str_to_lxml(raw_mpd_text)
        self.namespaces: Dict[str, str] = {
            "": "urn:mpeg:dash:schema:mpd:2011",
            "cenc": "urn:mpeg:cenc:2013",
            "mspr": "urn:microsoft:playready",
        }
    
    # 註釋輸入 obj 應具有 .text 屬性，回傳 ElementTree.Element
    def str_to_lxml(self, obj: Any) -> ET.Element:
        # 假設 obj.text 是一個 str
        return ET.fromstring(obj.text)

    # 註釋回傳值為字典
    def _parse_drm_info(self) -> Dict[str, Any]:
        drm_info: Dict[str, Any] = {}

        # 1. 尋找 cenc:default_KID
        kid_prot_info: Optional[ET.Element] = self.root.find(
            ".//ContentProtection[@schemeIdUri='urn:mpeg:dash:mp4protection:2011']",
            self.namespaces,
        )
        if kid_prot_info is not None:
            # 確保 get() 的回傳值被處理為 str，以防為 None
            kid: str = kid_prot_info.get("{urn:mpeg:cenc:2013}default_KID", "").strip().replace('-', '')
            drm_info["default_KID"] = kid if len(kid) == 32 else None

        # 2. 尋找 PlayReady 資訊
        playready_prot_info: Optional[ET.Element] = self.root.find(
            ".//ContentProtection[@schemeIdUri='urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95']",
            self.namespaces,
        )
        widevine_prot_info: Optional[ET.Element] = self.root.find(
            ".//ContentProtection[@schemeIdUri='urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed']",
            self.namespaces,
        )
        if playready_prot_info is not None or widevine_prot_info is not None:
            # findtext 回傳 str 或 default 值 (這裡為 "")
            pro_value: str = playready_prot_info.findtext("./mspr:pro", "", namespaces=self.namespaces)
            if pro_value:
                drm_info["playready_pssh"] = pro_value

            pssh_value: str = widevine_prot_info.findtext("./cenc:pssh", "", namespaces=self.namespaces)
            if pssh_value and len(pssh_value) == 76 and pssh_value.endswith("="):
                drm_info["widevine_pssh"] = pssh_value
        
        return drm_info

    # 註釋參數和回傳值
    def _parse_segment_timeline(self, seg_template: ET.Element) -> List[Segment]:
        seg_timeline: Optional[ET.Element] = seg_template.find("./SegmentTimeline", self.namespaces)
        if seg_timeline is None:
            return []
        
        # 使用 Union[str, Any] 處理 get() 可能回傳 None 的情況，但在 int() 轉換前被處理為 str 或 int
        return [
            Segment(
                # get() 回傳 str 或 None，但這裡提供 default value (0)
                t=int(s.get("t", 0)), 
                d=int(s.get("d")),
                r=int(s.get("r", 0)),
            )
            for s in seg_timeline.findall("./S", self.namespaces)
        ]

    # 註釋參數和回傳值
    def _generate_segment_urls(
        self, rep_id: str, media_template: str, segments: List[Segment], base_url: str
    ) -> List[str]:
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

    # 註釋參數和回傳值
    def _parse_representation(
        self,
        rep: ET.Element,
        adapt_set: ET.Element,
        base_url: str,
    ) -> Optional[MediaTrack]:
        
        # SegmentTemplate 可能在 Representation 或 AdaptationSet 層級
        seg_template: Optional[ET.Element] = rep.find(
            "./SegmentTemplate", self.namespaces
        ) or adapt_set.find("./SegmentTemplate", self.namespaces)

        if seg_template is None:
            return None

        segments: List[Segment] = self._parse_segment_timeline(seg_template)
        rep_id: str = rep.get("id")
        
        init_template: str = seg_template.get("initialization")
        init_url: str = urljoin(
            base_url,
            init_template.replace("$RepresentationID$", rep_id),
        )
        media_template: str = seg_template.get("media")
        
        segment_urls: List[str] = self._generate_segment_urls(
            rep_id, media_template, segments, base_url
        )

        # 處理 Optional 屬性和 int 轉換
        width: Optional[str] = rep.get("width")
        height: Optional[str] = rep.get("height")
        audio_sampling_rate: Optional[str] = rep.get("audioSamplingRate")
        
        # 假設 get("timescale") 總是可以轉換為 int
        timescale_str: str = seg_template.get("timescale", "1")

        return MediaTrack(
            id=rep_id,
            bandwidth=int(rep.get("bandwidth")),
            codecs=rep.get("codecs"),
            segments=segments,
            init_url=init_url,
            segment_urls=segment_urls,
            mime_type=adapt_set.get("mimeType", ""),
            width=int(width) if width else None,
            height=int(height) if height else None,
            timescale=int(timescale_str),
            audio_sampling_rate=(
                int(audio_sampling_rate)
                if audio_sampling_rate
                else None
            ),
        )

    # 註釋回傳值為 MPDContent
    def get_highest_mpd_content(self) -> MPDContent:
        base_url: str = self.mpd_url.rsplit("/", 1)[0] + "/"
        
        period: ET.Element = self.root.find("./Period", self.namespaces)
        
        video_reps: List[MediaTrack] = []
        audio_reps: List[MediaTrack] = []

        for adapt_set in period.findall("./AdaptationSet", self.namespaces):
            mime_type: str = adapt_set.get("mimeType", "")
            for rep_element in adapt_set.findall("./Representation", self.namespaces):
                track: Optional[MediaTrack] = self._parse_representation(rep_element, adapt_set, base_url)
                if track is None:
                    continue

                if mime_type.startswith("video"):
                    video_reps.append(track)
                elif mime_type.startswith("audio"):
                    audio_reps.append(track)


        highest_video: Optional[MediaTrack] = (
            max(video_reps, key=lambda x: x.bandwidth) if video_reps else None
        )
        highest_audio: Optional[MediaTrack] = (
            max(audio_reps, key=lambda x: x.bandwidth) if audio_reps else None
        )
        drm_info: Dict[str, Any] = self._parse_drm_info()

        return MPDContent(
            video_track=highest_video,
            audio_track=highest_audio,
            base_url=base_url,
            drm_info=drm_info,
        )