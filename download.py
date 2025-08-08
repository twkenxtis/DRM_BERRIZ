import requests
import os
import aiohttp
import asyncio
import shutil
import logging
import subprocess
from xml.etree import ElementTree as ET
from urllib.parse import urljoin
from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
import json
import ffmpeg

USER_AGENT = "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36"


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

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
    def __init__(self, mpd_url: str):
        self.mpd_url = mpd_url
        self.namespaces = {
            '': 'urn:mpeg:dash:schema:mpd:2011',
            'cenc': 'urn:mpeg:cenc:2013',
            'mspr': 'urn:microsoft:playready'
        }
        self.root = self._load_mpd()

    def _load_mpd(self) -> ET.Element:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(self.mpd_url, headers=headers)
        response.raise_for_status()
        return ET.fromstring(response.text)

    def get_highest_quality_content(self) -> MPDContent:
        base_url = self.mpd_url.rsplit('/', 1)[0] + '/'
        period = self.root.find('./Period', self.namespaces)
        
        video_reps = []
        audio_reps = []
        
        for adapt_set in period.findall('./AdaptationSet', self.namespaces):
            mime_type = adapt_set.get('mimeType', '')
            
            for rep in adapt_set.findall('./Representation', self.namespaces):
                seg_template = rep.find('./SegmentTemplate', self.namespaces) or adapt_set.find('./SegmentTemplate', self.namespaces)
                if not seg_template:
                    continue
                
                seg_timeline = seg_template.find('./SegmentTimeline', self.namespaces)
                segments = [
                    Segment(
                        t=int(s.get('t', 0)),
                        d=int(s.get('d')),
                        r=int(s.get('r', 0))
                    ) for s in seg_timeline.findall('./S', self.namespaces)
                ] if seg_timeline else []
                
                init_url = urljoin(base_url, seg_template.get('initialization').replace('$RepresentationID$', rep.get('id')))
                media_template = seg_template.get('media')
                segment_urls = []
                
                for seg in segments:
                    current_time = seg.t
                    for _ in range(seg.r + 1):
                        url = media_template.replace('$RepresentationID$', rep.get('id')).replace('$Time$', str(current_time))
                        segment_urls.append(urljoin(base_url, url))
                        current_time += seg.d
                
                track = MediaTrack(
                    id=rep.get('id'),
                    bandwidth=int(rep.get('bandwidth')),
                    codecs=rep.get('codecs'),
                    segments=segments,
                    init_url=init_url,
                    segment_urls=segment_urls,
                    mime_type=mime_type,
                    width=int(rep.get('width')) if rep.get('width') else None,
                    height=int(rep.get('height')) if rep.get('height') else None,
                    timescale=int(seg_template.get('timescale', 1)),
                    audio_sampling_rate=int(rep.get('audioSamplingRate')) if rep.get('audioSamplingRate') else None
                )
                
                if mime_type.startswith('video'):
                    video_reps.append(track)
                elif mime_type.startswith('audio'):
                    audio_reps.append(track)
        
        highest_video = max(video_reps, key=lambda x: x.bandwidth) if video_reps else None
        highest_audio = max(audio_reps, key=lambda x: x.bandwidth) if audio_reps else None
        
        drm_info = {}
        prot_info = self.root.find(".//ContentProtection[@schemeIdUri='urn:uuid:9a04f079-9840-4286-ab92-e65be0885f95']", self.namespaces)
        if prot_info:
            drm_info = {
                'default_KID': prot_info.get('cenc:default_KID'),
                'playready_pro': prot_info.findtext('./mspr:pro', '', namespaces=self.namespaces),
                'pssh': prot_info.findtext('./cenc:pssh', '', namespaces=self.namespaces)
            }
        
        return MPDContent(
            video_track=highest_video,
            audio_track=highest_audio,
            base_url=base_url,
            drm_info=drm_info
        )

class MediaDownloader:
    def __init__(self, media_id: str):
        self.media_id = media_id
        
        self.base_dir = self._create_output_dir()
        self.session = None

    def _create_output_dir(self) -> Path:
        output_dir = Path(f"{self.media_id} {datetime.now().strftime('%y%m%d_%H%M%S')}")
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def _get_file_extension(self, mime_type: str) -> str:
        """Determine file extension based on MIME type for DASH streaming"""
        mime_type = mime_type.lower()

        if 'application/dash+xml' in mime_type:
            return '.m4v'  # DASH manifest (custom override)
    
        if 'video/mp4' in mime_type:
            return '.mp4'  # ISO BMFF video

        if 'audio/mp4' in mime_type:
            return '.m4a'  # ISO BMFF audio

        if 'video/webm' in mime_type:
            return '.webm'  # WebM video

        if 'audio/webm' in mime_type:
            return '.weba'  # WebM audio

        if 'text/vtt' in mime_type or 'application/x-subrip' in mime_type:
            return '.vtt'  # Subtitles

        if 'application/octet-stream' in mime_type:
            return '.m4s'  # Fragmented MP4 segment (common in DASH)

        return '.ts'  # Default fallback

    
    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit_per_host=25)
            timeout = aiohttp.ClientTimeout(total=1200)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': USER_AGENT}
            )
        
    async def _download_file(self, url: str, save_path: Path) -> bool:
        await self._ensure_session()
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    with open(save_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(10240*10240):
                            f.write(chunk)
                    return True
                return False
        except Exception as e:
            logging.error(f"Download failed {url}: {str(e)}")
            return False
    
    async def download_track(self, track: MediaTrack, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        track_dir.mkdir(exist_ok=True)
        
        logging.info(f"Start downloading {track_type} track: {track.id} [Bitrate: {track.bandwidth}]")
        
        # Get appropriate extension for files
        file_ext = self._get_file_extension(track.mime_type)
        
        # Download initialization segment
        init_path = track_dir / f"init{file_ext}"
        if not await self._download_file(track.init_url, init_path):
            logging.error(f"{track_type}Initialization file download failed")
            return False
        
        # Download media segments
        tasks = []
        for i, url in enumerate(track.segment_urls):
            seg_path = track_dir / f"seg_{i:05d}{file_ext}"
            tasks.append(self._download_file(url, seg_path))
        
        results = await asyncio.gather(*tasks)
        success_count = sum(results)
        
        logging.info(f"{track_type}Split download complete: Success{success_count}/{len(results)}")
        return success_count == len(results)
    
    def _merge_track(self, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        output_file = self.base_dir / f"{track_type}.ts"  # Temporary TS file
        
        # Find init file (should be only one)
        init_files = list(track_dir.glob("init.*"))
        if not init_files:
            logging.warning(f"Could not find {track_type} initialization file")
            return False
        
        # Find all segment files and sort them numerically
        segments = sorted(track_dir.glob("seg_*.*"), key=lambda x: int(x.stem.split('_')[1]))
        if not segments:
            logging.warning(f"No {track_type} fragment files found")
            return False
        
        logging.info(f"Merge {track_type} tracks: {len(segments)} segments")
        
        try:
            with open(output_file, 'wb') as outfile:
                # Copy init file first
                with open(init_files[0], 'rb') as infile:
                    shutil.copyfileobj(infile, outfile)
                
                # Copy all segments in order
                for seg in segments:
                    with open(seg, 'rb') as infile:
                        shutil.copyfileobj(infile, outfile)
            
            logging.info(f"{track_type}Merger completed: {output_file}")
            return True
        except Exception as e:
            logging.error(f"{track_type}Merger failed: {str(e)}")
            return False
    
    async def download_content(self, mpd_content: MPDContent):
        try:
            tasks = []
            if mpd_content.video_track:
                tasks.append(self.download_track(mpd_content.video_track, "video"))
            if mpd_content.audio_track:
                tasks.append(self.download_track(mpd_content.audio_track, "audio"))
            
            download_results = await asyncio.gather(*tasks)
            
            merge_results = []
            if mpd_content.video_track and download_results[0]:
                merge_results.append(self._merge_track("video"))
            if mpd_content.audio_track and (len(download_results) > 1 and download_results[1]):
                merge_results.append(self._merge_track("audio"))
            
            return all(merge_results)
        finally:
            if self.session:
                await self.session.close()
        
class FFmpegMuxer:
    def __init__(self, base_dir: Path, decryption_key: Optional[str] = None):
        self.base_dir = base_dir
        self.decryption_key = decryption_key
    
    def _prepare_track(self, track_type: str) -> Optional[Path]:
        """Handle decryption if needed and return final file path"""
        input_file = self.base_dir / f"{track_type}.ts"
        
        if not input_file.exists():
            return None
            
        # Check for encryption
        kid = self._check_encryption(input_file)
        
        if kid and self.decryption_key:
            logging.info(f"Detected {track_type} track encryption (KID: {kid}), decrypting...")
            decrypted_file = self.base_dir / f"{track_type}_decrypted.ts"
            if self._decrypt_file(input_file, decrypted_file, self.decryption_key, kid):
                return decrypted_file
            return None
        elif kid:
            logging.warning(f"Warning: {track_type} track is encrypted but no decryption key is provided.")
            return None
        
        # No encryption, use original file
        return input_file
    
    def _check_encryption(self, file_path: Path) -> Optional[str]:
        """Check if file is encrypted using mp4info and return KID if found"""
        try:
            result = subprocess.run(
                ['mp4info', str(file_path)],
                capture_output=True,
                text=True
            )
            
            if 'encrypted' in result.stdout.lower():
                # Extract KID from output
                for line in result.stdout.splitlines():
                    if 'default_KID' in line:
                        return line.split('=')[1].strip().strip('{}')
                return "encrypted_unknown_kid"
            return None
        except Exception as e:
            logging.error(f"Encryption check failed {file_path}: {str(e)}")
            return None

    def _decrypt_file(
        self,
        input_path: Path,
        output_path: Path,
        key: str,
        kid: str,
    ) -> bool:
        tools_dir = Path(__file__).parent / "tools"
        mp4decrypt_path = tools_dir / "mp4decrypt.exe"
        
        if not mp4decrypt_path.exists():
            logging.error(f"mp4decrypt.exe not found at: {mp4decrypt_path}")
            return False

        try:
            subprocess.run(
                [
                    str(mp4decrypt_path),
                    "--key", key,
                    str(input_path),
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return True

        except subprocess.CalledProcessError as e:
            logging.error(f"Decryption failed for {input_path}: {e.stderr or e.stdout}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error decrypting {input_path}: {str(e)}")
            return False


    def mux_to_mp4(self, output_name: str = "output.mp4") -> bool:
        # Prepare video and audio tracks
        video_file = self._prepare_track("video")
        audio_file = self._prepare_track("audio")
        
        if not video_file or not audio_file:
            logging.warning("Error: Valid video and audio must exist simultaneously for multiplexing.")
            return False
        
        output_file = self.base_dir / output_name
        
        logging.info("Start using FFmpeg to mix video and audio...")
        
        # Standard FFmpeg command without modification
        cmd = [
            'ffmpeg',
            '-i', str(video_file),
            '-i', str(audio_file),
            '-c', 'copy',
            '-map_metadata', '-1',
            '-map_chapters', '-1',
            '-metadata', 'title=',
            '-metadata', 'comment=',
            '-f', 'mp4',
            '-movflags', '+faststart+frag_keyframe+empty_moov+default_base_moof',
            '-fflags', '+genpts',
            '-y',
            str(output_file)
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            if result.returncode != 0:
                logging.error(f"FFmpeg multiplexing failed:\n{result.stderr}")
                return False
            
            logging.info(f"Mixed flow completed: {output_file}")
            return True
        except Exception as e:
            logging.error(f"FFmpeg mixing error: {str(e)}")
            return False

class VideoInfo:
    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"檔案未找到: {path}")
        self.path = path
        try:
            self._probe_data = ffmpeg.probe(self.path)
        except ffmpeg.Error as e:
            raise RuntimeError(f"FFmpeg 探測錯誤: {e.stderr.decode('utf-8')}")

        self._format = self._probe_data["format"]
        self._streams = self._probe_data["streams"]

        self._size_bytes = int(self._format.get("size", 0))
        self._duration_sec = float(self._format.get("duration", 0.0))

    @property
    def size(self) -> str:
        size_gb = self._size_bytes / (1024**3)
        size_mb = self._size_bytes / (1024**2)
        if size_gb >= 1:
            return f"{size_gb:.2f} GB"
        else:
            return f"{int(size_mb)} MB"

    @property
    def duration(self) -> str:
        total_seconds = int(self._duration_sec)
        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        else:
            return f"{m:02d}:{s:02d}"

    @property
    def codec(self) -> str:
        for stream in self._streams:
            if stream["codec_type"] == "video":
                codec = stream.get("codec_name", "unknown").upper()
                return "H265" if "hevc" in codec.lower() else "H264"
        return "unknown"

    @property
    def quality_label(self) -> str:
        resolution_map = {
            144: "144p",
            256: "144p",
            240: "240p",
            426: "240p",
            360: "360p",
            640: "360p",
            480: "480p",
            854: "480p",
            540: "540p",
            960: "540p",
            720: "720p",
            1280: "720p",
            1080: "1080p",
            1920: "1080p",
            1440: "1440p",
            2560: "1440p",
            2160: "2160p",
            3840: "2160p",
            2880: "2880p",
        }
        for stream in self._streams:
            if stream["codec_type"] == "video":
                height = int(stream.get("height", 0))
                return resolution_map.get(height, f"{height}p")
        return "unknown"

    @property
    def audio_codec(self) -> str:
        for stream in self._streams:
            if stream["codec_type"] == "audio":
                return stream.get("codec_name", "unknown").upper()
        return "unknown"

    def as_dict(self) -> dict:
        return {
            "size": self.size,
            "duration": self.duration,
            "video_codec": self.codec,
            "quality": self.quality_label,
            "audio_codec": self.audio_codec,
        }

class SUCCESS:
    def __init__(self, downloader, json_data):
        self.downloader=downloader
        self.json_data=json_data
    
    def when_success(self, success, decryption_key):
        if success:
            logging.info(f"\nDownload complete! File saved to: {self.downloader.base_dir}")
            logging.info(f"Video file: {self.downloader.base_dir / 'video.ts'}")
            logging.info(f"Audio file: {self.downloader.base_dir / 'audio.ts'}")
            SUCCESS.dl_thumbnail(self)
        
        # Mux video and audio with FFmpeg
        muxer = FFmpegMuxer(self.downloader.base_dir, decryption_key)
        if muxer.mux_to_mp4():
            SUCCESS.re_name(self)
            SUCCESS.clean_file(self)
        else:
            logging.error("\nAn error occurred during loading.")
        
    def clean_file(self):
        base_dir = self.downloader.base_dir
        # Files to delete
        file_paths = [
            base_dir / 'video_decrypted.ts',
            base_dir / 'video.ts',
            base_dir / 'audio_decrypted.ts',
            base_dir / 'audio.ts',
        ]

        # Remove files with try/except
        for fp in file_paths:
            try:
                fp.unlink()
                logging.info(f"Removed file: {fp}")
            except FileNotFoundError:
                logging.warning(f"File not found, skipping: {fp}")
            except Exception as e:
                logging.error(f"Error removing file {fp}: {e}")

        # Force-remove non-empty directories
        for subfolder in ['audio', 'video']:
            dir_path = base_dir / subfolder
            try:
                shutil.rmtree(dir_path)
                logging.info(f"Force-removed directory: {dir_path}")
            except FileNotFoundError:
                logging.warning(f"Directory not found, skipping: {dir_path}")
            except Exception as e:
                logging.error(f"Error force-removing directory {dir_path}: {e}")

    def re_name(self):
        t = self.json_data.get("media", {}).get("formatted_published_at", "")[2:-6].replace('-', '')
        video_codec = VideoInfo(self.downloader.base_dir / 'output.mp4').codec
        video_quality_label = VideoInfo(self.downloader.base_dir / 'output.mp4').quality_label
        video_audio_codec = VideoInfo(self.downloader.base_dir / 'output.mp4').audio_codec
        filename = f'{t} IVE - ' + self.json_data.get("media", {}).get("title") + f" WEB-DL.{video_quality_label}.{video_codec}.{video_audio_codec}.mp4"
        os.rename(self.downloader.base_dir / 'output.mp4', self.downloader.base_dir / filename)
        logging.info(f"Final output file: {self.downloader.base_dir / filename}")
        
    def dl_thumbnail(self):
        thumbnail_url = self.json_data.get("media", {}).get("thumbnail_url", "")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
        }
        response = requests.get(thumbnail_url, headers=headers)
        thumbnail_name = os.path.basename(thumbnail_url)
        save_path = self.downloader.base_dir  / thumbnail_name
        if response.status_code == 200:
            save_path.write_bytes(response.content)
        else:
            logging.error(f"{response.status_code} {thumbnail_url}")
            logging.error("Thumbnail donwload fail")
    
    
async def run_dl(mpd_uri, decryption_key, json_data):
    parser = MPDParser(mpd_uri)
    mpd_content = parser.get_highest_quality_content()
    
    if not mpd_content.video_track and not mpd_content.audio_track:
        logging.error("Error: No valid audio or video tracks found in MPD.")
        return
    
    if mpd_content.drm_info and mpd_content.drm_info.get('default_KID'):
        logging.info(f"\nEncrypted content detected (KID: {mpd_content.drm_info['default_KID']})")

    foldername = json_data.get("media", {}).get("id", "")
    downloader = MediaDownloader(f'{foldername}')
    success = await downloader.download_content(mpd_content)
    s = SUCCESS(downloader, json_data)
    s.when_success(success, decryption_key)
    

