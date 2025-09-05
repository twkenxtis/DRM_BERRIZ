import asyncio
import logging
import os
import shutil
from pathlib import Path

from logging.handlers import TimedRotatingFileHandler

import aiohttp

from lib.ffmpeg.parse_mpd import MPDContent, MPDParser, MediaTrack
from lib.video_folder import start_download_queue
from static.color import Color


USER_AGENT = "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36"


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    os.makedirs("logs", exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    logger = logging.getLogger("download")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    logger.propagate = False

    # console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # rotating file handler
    app_file_handler = TimedRotatingFileHandler(
        filename="logs/download.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)
    logger.addHandler(app_file_handler)

    return logger


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
            connector = aiohttp.TCPConnector(limit_per_host=10)
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
            f"{Color.fg('light_gray')}Start downloading{Color.reset()} {Color.bg('cyan')}{track_type}{Color.reset()} track: {track.id} [Bitrate: {Color.fg('violet')}{track.bandwidth}{Color.reset()}]"
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
            f"{Color.fg('plum')}{track_type} Split download complete: Success {Color.fg('light_yellow')}{success_count}{Color.reset()}/{len(results)}{Color.reset()}"
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

        logger.info(f"{Color.fg('light_gray')}Merge{Color.reset()} {Color.fg('light_gray')}{track_type} {Color.reset()}{Color.fg('light_gray')}tracks{Color.reset()}: {len(segments)} {Color.fg('yellow')}{Color.reset()}{Color.fg('light_gray')}segments{Color.reset()}")
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

            logger.info(f"{Color.fg('light_gray')}{track_type} Merger completed: {output_file}{Color.reset()}")
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
