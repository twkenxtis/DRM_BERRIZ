from dataclasses import dataclass
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from typing import Dict, List, Optional


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
    video_track: MediaTrack
    audio_track: MediaTrack
    base_url: str
    drm_info: Dict


class MPDParser:
    def __init__(self, raw_mpd: ET, mpd_url: str):
        self.mpd_url = mpd_url
        self.root = self.str_to_lxml(raw_mpd.text)
        self.namespaces = {
            "": "urn:mpeg:dash:schema:mpd:2011",
            "cenc": "urn:mpeg:cenc:2013",
            "mspr": "urn:microsoft:playready",
        }
        
    def str_to_lxml(self, obj):
        return ET.fromstring(obj)

    def _parse_drm_info(self) -> Dict:
        drm_info = {}
        prot_info = self.root.find(
            ".//ContentProtection[@schemeIdUri='urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95']",
            self.namespaces,
        )
        if prot_info is not None:
            drm_info = {
                "default_KID": prot_info.get("cenc:default_KID"),
                "playready_pro": prot_info.findtext(
                    "./mspr:pro", "", namespaces=self.namespaces
                ),
                "pssh": prot_info.findtext(
                    "./cenc:pssh", "", namespaces=self.namespaces
                ),
            }
        return drm_info

    def _parse_segment_timeline(self, seg_template: ET.Element) -> List[Segment]:
        seg_timeline = seg_template.find("./SegmentTimeline", self.namespaces)
        if seg_timeline is None:
            return []
        return [
            Segment(
                t=int(s.get("t", 0)),
                d=int(s.get("d")),
                r=int(s.get("r", 0)),
            )
            for s in seg_timeline.findall("./S", self.namespaces)
        ]

    def _generate_segment_urls(
        self, rep_id: str, media_template: str, segments: List[Segment], base_url: str
    ) -> List[str]:
        segment_urls = []
        for seg in segments:
            current_time = seg.t
            for _ in range(seg.r + 1):
                url = media_template.replace("$RepresentationID$", rep_id).replace(
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
        seg_template = rep.find(
            "./SegmentTemplate", self.namespaces
        ) or adapt_set.find("./SegmentTemplate", self.namespaces)

        if not seg_template:
            return None

        segments = self._parse_segment_timeline(seg_template)
        rep_id = rep.get("id")
        init_url = urljoin(
            base_url,
            seg_template.get("initialization").replace("$RepresentationID$", rep_id),
        )
        media_template = seg_template.get("media")
        segment_urls = self._generate_segment_urls(
            rep_id, media_template, segments, base_url
        )

        return MediaTrack(
            id=rep_id,
            bandwidth=int(rep.get("bandwidth")),
            codecs=rep.get("codecs"),
            segments=segments,
            init_url=init_url,
            segment_urls=segment_urls,
            mime_type=adapt_set.get("mimeType", ""),
            width=int(rep.get("width")) if rep.get("width") else None,
            height=int(rep.get("height")) if rep.get("height") else None,
            timescale=int(seg_template.get("timescale", 1)),
            audio_sampling_rate=(
                int(rep.get("audioSamplingRate"))
                if rep.get("audioSamplingRate")
                else None
            ),
        )

    def get_highest_quality_content(self) -> MPDContent:
        base_url = self.mpd_url.rsplit("/", 1)[0] + "/"
        period = self.root.find("./Period", self.namespaces)

        video_reps = []
        audio_reps = []

        for adapt_set in period.findall("./AdaptationSet", self.namespaces):
            mime_type = adapt_set.get("mimeType", "")
            for rep_element in adapt_set.findall("./Representation", self.namespaces):
                track = self._parse_representation(rep_element, adapt_set, base_url)
                if not track:
                    continue

                if mime_type.startswith("video"):
                    video_reps.append(track)
                elif mime_type.startswith("audio"):
                    audio_reps.append(track)

        highest_video = (
            max(video_reps, key=lambda x: x.bandwidth) if video_reps else None
        )
        highest_audio = (
            max(audio_reps, key=lambda x: x.bandwidth) if audio_reps else None
        )
        drm_info = self._parse_drm_info()

        return MPDContent(
            video_track=highest_video,
            audio_track=highest_audio,
            base_url=base_url,
            drm_info=drm_info,
        )