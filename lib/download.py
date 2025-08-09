import asyncio
import re
import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import aiohttp

from lib.ffmpeg.parse_mpd import MPDContent, MPDParser, MediaTrack
from lib.tools.reName import SUCCESS


USER_AGENT = "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36"


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("download")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "download.py.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)

    app_logger.addHandler(console_handler)
    app_logger.addHandler(app_file_handler)
    return app_logger


logger = setup_logging()


class MediaDownloader:
    def __init__(self, media_id: str, outout_dir: str):
        self.media_id = media_id
        self.base_dir = outout_dir
        self.session = None

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

    async def _download_file(self, url: str, save_path: Path) -> bool:
        await self._ensure_session()
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    with open(save_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(10240 * 10240):
                            f.write(chunk)
                    return True
                return False
        except Exception as e:
            logger.error(f"Download failed {url}: {str(e)}")
            return False

    async def download_track(self, track: MediaTrack, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        track_dir.mkdir(exist_ok=True)

        logger.info(
            f"Start downloading {track_type} track: {track.id} [Bitrate: {track.bandwidth}]"
        )

        # Get appropriate extension for files
        file_ext = self._get_file_extension(track.mime_type)

        # Download initialization segment
        init_path = track_dir / f"init{file_ext}"
        if not await self._download_file(track.init_url, init_path):
            logger.error(f"{track_type} Initialization file download failed")
            return False

        # Download media segments
        tasks = []
        for i, url in enumerate(track.segment_urls):
            seg_path = track_dir / f"seg_{i:05d}{file_ext}"
            tasks.append(self._download_file(url, seg_path))

        results = await asyncio.gather(*tasks)
        success_count = sum(results)

        logger.info(
            f"{track_type} Split download complete: Success {success_count}/{len(results)}"
        )
        return success_count == len(results)

    def _merge_track(self, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        output_file = self.base_dir / f"{track_type}.ts"

        init_files = list(track_dir.glob("init.*"))
        if not init_files:
            logger.warning(f"Could not find {track_type} initialization file")
            return False

        segments = sorted(
            track_dir.glob("seg_*.*"), key=lambda x: int(x.stem.split("_")[1])
        )
        if not segments:
            logger.warning(f"No {track_type} fragment files found")
            return False

        logger.info(f"Merge {track_type} tracks: {len(segments)} segments")
        bool = MediaDownloader.binary_merge(output_file, init_files, segments, track_type)
        return bool


    @staticmethod
    def binary_merge(output_file, init_files, segments, track_type):
        try:
            with open(output_file, "wb") as outfile:
                with open(init_files[0], "rb") as infile:
                    shutil.copyfileobj(infile, outfile)
                for seg in segments:
                    with open(seg, "rb") as infile:
                        shutil.copyfileobj(infile, outfile)

            logger.info(f"{track_type} Merger completed: {output_file}")
            return True
        except Exception as e:
            logger.error(f"{track_type} Merger failed: {str(e)}")
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


class Video_folder:
    def __init__(self, json_data):
        self.json_data = json_data
        self.media_id = self.parse_mediaid()
        self.title = self.parse_title()
        self.published_at = self.parse_published_at()
        self.time_str = self.formact_time()

    def video_folder_handle(self):
        base_dir = Path("downloads") / "videos"
        folder_name = f"{self.time_str} {self.media_id}"
        folder_name = re.sub(r'[\\/:\*\?"<>|]', "", folder_name).strip()
        output_dir = base_dir / folder_name

        if output_dir.exists() and output_dir.is_dir():
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def parse_mediaid(self):
        logger.info(f'mediaid: {self.json_data.get("media", {}).get("id", "")}')
        return self.json_data.get("media", {}).get("id", "")

    def parse_title(self):
        logger.info(f'title: {self.json_data.get("media", {}).get("title", "")}')
        return self.json_data.get("media", {}).get("title", "")

    def parse_published_at(self):
        return self.json_data.get("media", {}).get("published_at", "")

    def formact_time(self):
        time_str = DateTimeFormatter.format_published_at(self.published_at)
        return time_str


class DateTimeFormatter:
    """Formats datetime strings for folder naming."""

    @staticmethod
    def format_published_at(publishedAt: str) -> str:
        """Convert UTC publishedAt time to KST and format as string."""
        utc_time = datetime.strptime(publishedAt, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        kst_offset = timedelta(hours=9)  # KST is UTC+9
        kst_time = utc_time + kst_offset
        return kst_time.strftime("%y%m%d %H-%M")


async def start_download_queue(decryption_key, json_data, mpd_content):
    video_folder = Video_folder(json_data)
    media_id = video_folder.media_id
    output_dir = video_folder.video_folder_handle()
    if output_dir is None:
        title = video_folder.parse_title()
        logging.warning(f"{title} already exits skip downloads")
    elif output_dir is not None:
        downloader = MediaDownloader(media_id, output_dir)
        success = await downloader.download_content(mpd_content)
        s = SUCCESS(downloader, json_data)
        s.when_success(success, decryption_key)


async def run_dl(mpd_uri, decryption_key, json_data):
    parser = MPDParser(mpd_uri)
    mpd_content = parser.get_highest_quality_content()

    if not mpd_content.video_track and not mpd_content.audio_track:
        logger.error("Error: No valid audio or video tracks found in MPD.")
        return

    if mpd_content.drm_info and mpd_content.drm_info.get("default_KID"):
        logger.info(
            f"\nEncrypted content detected (KID: {mpd_content.drm_info['default_KID']})"
        )

    await start_download_queue(decryption_key, json_data, mpd_content)
