import logging
import os
import requests
import shutil
from logging.handlers import TimedRotatingFileHandler

from lib.ffmpeg.parse_mpd import MPDParser, MediaTrack, MPDContent
from lib.ffmpeg.videoinfo import VideoInfo
from lib.ffmpeg.mux import FFmpegMuxer


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("reName")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "reName.py.log"),
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


class SUCCESS:
    def __init__(self, downloader, json_data):
        self.downloader = downloader
        self.json_data = json_data

    def when_success(self, success, decryption_key):
        if success:
            logger.info(
                f"\nDownload complete! File saved to: {self.downloader.base_dir}"
            )
            logger.info(f"Video file: {self.downloader.base_dir / 'video.ts'}")
            logger.info(f"Audio file: {self.downloader.base_dir / 'audio.ts'}")
            SUCCESS.dl_thumbnail(self)

        # Mux video and audio with FFmpeg
        muxer = FFmpegMuxer(self.downloader.base_dir, decryption_key)
        if muxer.mux_to_mp4():
            SUCCESS.re_name(self)
            SUCCESS.clean_file(self)
        else:
            logger.error("\nAn error occurred during loading.")

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
                logger.info(f"Removed file: {fp}")
            except FileNotFoundError:
                logger.warning(f"File not found, skipping: {fp}")
            except Exception as e:
                logger.error(f"Error removing file {fp}: {e}")

        # Force-remove non-empty directories
        for subfolder in ["audio", "video"]:
            dir_path = base_dir / subfolder
            try:
                shutil.rmtree(dir_path)
                logger.info(f"Force-removed directory: {dir_path}")
            except FileNotFoundError:
                logger.warning(f"Directory not found, skipping: {dir_path}")
            except Exception as e:
                logger.error(f"Error force-removing directory {dir_path}: {e}")

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
        logger.info(f"Final output file: {self.downloader.base_dir / filename}")

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
            logger.error(f"{response.status_code} {thumbnail_url}")
            logger.error("Thumbnail donwload fail")