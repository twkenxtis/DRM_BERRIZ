import asyncio
from datetime import datetime
import logging
import os
from pathlib import Path
import shutil

import aiohttp
import requests
from tqdm.asyncio import tqdm

from lib.ffmpeg.parse_mpd import MPDParser, MediaTrack, MPDContent
from lib.ffmpeg.videoinfo import VideoInfo
from lib.ffmpeg.mux import FFmpegMuxer

USER_AGENT = "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36"


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class MediaDownloader:
    def __init__(self, media_id: str):
        self.media_id = media_id
        self.base_dir = self._create_output_dir()
        self.session = None

    def _create_output_dir(self) -> Path:
        base_dir = Path("downloads")
        folder_name = f"{self.media_id} {datetime.now().strftime('%y%m%d_%H%M%S')}"
        output_dir = base_dir / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _get_file_extension(self, mime_type: str) -> str:
        """Determine file extension based on MIME type for DASH streaming"""
        mime_type = mime_type.lower()
        if "application/dash+xml" in mime_type:
            return ".m4v"
        if "video/mp4" in mime_type:
            return ".mp4"
        if "audio/mp4" in mime_type:
            return ".m4a"
        if "video/webm" in mime_type:
            return ".webm"
        if "audio/webm" in mime_type:
            return ".weba"
        if "text/vtt" in mime_type or "application/x-subrip" in mime_type:
            return ".vtt"
        if "application/octet-stream" in mime_type:
            return ".m4s"
        return ".ts"

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit_per_host=25)
            timeout = aiohttp.ClientTimeout(total=1200)
            self.session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, headers={"User-Agent": USER_AGENT}
            )

    async def _download_file(self, url: str, save_path: Path, desc: str = "Downloading") -> bool:
        await self._ensure_session()
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    # Get total size for progress bar (if available)
                    total_size = int(response.headers.get("content-length", 0))
                    
                    # Initialize tqdm progress bar
                    progress_bar = tqdm(
                        total=total_size,
                        unit="B",
                        unit_scale=True,
                        desc=desc,
                        leave=False
                    )
                    
                    with open(save_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(10240 * 10240):
                            f.write(chunk)
                            progress_bar.update(len(chunk))
                    
                    progress_bar.close()
                    return True
                return False
        except Exception as e:
            logging.error(f"Download failed {url}: {str(e)}")
            return False

    async def download_track(self, track: MediaTrack, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        track_dir.mkdir(exist_ok=True)

        logging.info(
            f"Start downloading {track_type} track: {track.id} [Bitrate: {track.bandwidth}]"
        )

        # Get appropriate extension for files
        file_ext = self._get_file_extension(track.mime_type)

        # Download initialization segment
        init_path = track_dir / f"init{file_ext}"
        if not await self._download_file(track.init_url, init_path, desc=f"{track_type} init"):
            logging.error(f"{track_type} Initialization file download failed")
            return False

        # Download media segments with a progress bar for the entire track
        tasks = []
        with tqdm(total=len(track.segment_urls), desc=f"{track_type} segments", unit="segment") as pbar:
            for i, url in enumerate(track.segment_urls):
                seg_path = track_dir / f"seg_{i:05d}{file_ext}"
                tasks.append(self._download_file(url, seg_path, desc=f"Segment {i:05d}"))
            
            results = await asyncio.gather(*tasks)
            for _ in results:
                pbar.update(1)  # Update progress bar after each task completes

        success_count = sum(results)

        logging.info(
            f"{track_type} Split download complete: Success {success_count}/{len(results)}"
        )
        return success_count == len(results)

    def _merge_track(self, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        output_file = self.base_dir / f"{track_type}.ts"

        init_files = list(track_dir.glob("init.*"))
        if not init_files:
            logging.warning(f"Could not find {track_type} initialization file")
            return False

        segments = sorted(
            track_dir.glob("seg_*.*"), key=lambda x: int(x.stem.split("_")[1])
        )
        if not segments:
            logging.warning(f"No {track_type} fragment files found")
            return False

        logging.info(f"Merge {track_type} tracks: {len(segments)} segments")

        try:
            with open(output_file, "wb") as outfile:
                with open(init_files[0], "rb") as infile:
                    shutil.copyfileobj(infile, outfile)
                for seg in segments:
                    with open(seg, "rb") as infile:
                        shutil.copyfileobj(infile, outfile)

            logging.info(f"{track_type} Merger completed: {output_file}")
            return True
        except Exception as e:
            logging.error(f"{track_type} Merger failed: {str(e)}")
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
            if mpd_content.audio_track and (
                len(download_results) > 1 and download_results[1]
            ):
                merge_results.append(self._merge_track("audio"))

            return all(merge_results)
        finally:
            if self.session:
                await self.session.close()


class SUCCESS:
    def __init__(self, downloader, json_data):
        self.downloader = downloader
        self.json_data = json_data

    def when_success(self, success, decryption_key):
        if success:
            logging.info(
                f"\nDownload complete! File saved to: {self.downloader.base_dir}"
            )
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
            base_dir / "video_decrypted.ts",
            base_dir / "video.ts",
            base_dir / "audio_decrypted.ts",
            base_dir / "audio.ts",
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
        for subfolder in ["audio", "video"]:
            dir_path = base_dir / subfolder
            try:
                shutil.rmtree(dir_path)
                logging.info(f"Force-removed directory: {dir_path}")
            except FileNotFoundError:
                logging.warning(f"Directory not found, skipping: {dir_path}")
            except Exception as e:
                logging.error(f"Error force-removing directory {dir_path}: {e}")

    def re_name(self):
        t = (
            self.json_data.get("media", {})
            .get("formatted_published_at", "")[2:-6]
            .replace("-", "")
        )
        video_codec = VideoInfo(self.downloader.base_dir / "output.mp4").codec
        video_quality_label = VideoInfo(
            self.downloader.base_dir / "output.mp4"
        ).quality_label
        video_audio_codec = VideoInfo(
            self.downloader.base_dir / "output.mp4"
        ).audio_codec
        filename = (
            f"{t} IVE - "
            + self.json_data.get("media", {}).get("title")
            + f" WEB-DL.{video_quality_label}.{video_codec}.{video_audio_codec}.mp4"
        )
        os.rename(
            self.downloader.base_dir / "output.mp4", self.downloader.base_dir / filename
        )
        logging.info(f"Final output file: {self.downloader.base_dir / filename}")

    def dl_thumbnail(self):
        thumbnail_url = self.json_data.get("media", {}).get("thumbnail_url", "")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
            "Accept-Encoding": "gzip, deflate, br, zstd",
        }
        response = requests.get(thumbnail_url, headers=headers)
        thumbnail_name = os.path.basename(thumbnail_url)
        save_path = self.downloader.base_dir / thumbnail_name
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

    if mpd_content.drm_info and mpd_content.drm_info.get("default_KID"):
        logging.info(
            f"\nEncrypted content detected (KID: {mpd_content.drm_info['default_KID']})"
        )

    foldername = json_data.get("media", {}).get("id", "")
    downloader = MediaDownloader(f"{foldername}")
    success = await downloader.download_content(mpd_content)
    s = SUCCESS(downloader, json_data)
    s.when_success(success, decryption_key)
