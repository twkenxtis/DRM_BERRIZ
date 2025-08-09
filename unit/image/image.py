import logging
import os
import re
from datetime import datetime, timedelta, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Union

import httpx

from unit.http.request_berriz_api import Playback_info, Public_context
from unit.image.parse_public_contexts import parse_public_contexts
from unit.image.parse_playback_contexts import parse_playback_contexts


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("image")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "image.py.log"),
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


class FilenameSanitizer:
    """Handles sanitization of filenames to remove invalid characters."""

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Remove invalid characters from a filename and strip whitespace."""
        cleaned = re.sub(r'[\\/:\*\?"<>|]', "", name)
        return cleaned.strip()


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


class FolderManager:
    """Manages folder creation for image downloads."""

    def __init__(self, base_dir: Path = Path.cwd() / "downloads" / "images"):
        self.base_dir = base_dir

    def create_image_folder(self, title: str, publishedAt: str) -> str | None:
        """Create a folder for images based on title and published time."""
        time_str = DateTimeFormatter.format_published_at(publishedAt)
        safe_title = FilenameSanitizer.sanitize_filename(title)
        folder_path = self.base_dir / f"{time_str} IVE - {safe_title}"

        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            if folder_path.exists():
                return "Already exists"
            folder_path.mkdir()
            return str(folder_path.resolve())
        except Exception as e:
            logger.error(f"Failed to create folder: {folder_path!r}, reason: {e}")
            return None


class ImageDownloader:
    """Handles downloading images from URLs."""

    @staticmethod
    def download_image(url: str, file_path: Union[str, Path]) -> None:
        headers = {"User-Agent": "Mozilla/5.0"}
        timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=30.0)
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)

        try:
            with httpx.Client(
                headers=headers, timeout=timeout, limits=limits, http2=True
            ) as client:
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, "wb") as f:
                        for chunk in resp.iter_bytes(65536):
                            f.write(chunk)
            logger.info(f"Downloaded {file_path}")
        except httpx.HTTPStatusError as e:
            logger.error(f"{url} download failed with code {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Failed to download {url}: {e}")
            raise


class ImageUrlParser:
    """Parses image URLs and manages their download."""

    def __init__(self, downloader: ImageDownloader):
        self.downloader = downloader

    def parse_and_download(self, images: List[Dict[str, Any]], folder: str) -> None:
        """Parse image URLs and download them to the specified folder."""
        folder_path = Path(folder)
        for idx, image in enumerate(images):
            url = image.get("imageUrl")
            if not url:
                continue
            name = Path(url).name or f"image_{idx}.jpg"
            name = name.split("?")[0]
            file_path = folder_path / name
            self.downloader.download_image(url, file_path)


class MediaDownloadOrchestrator:
    """Orchestrates the media download process."""

    def __init__(self):
        self.folder_manager = FolderManager()
        self.image_parser = ImageUrlParser(ImageDownloader())

    async def run_download(self, media_id: str) -> None:
        """Run the download process for a given media ID."""
        public_contexts = Public_context().get_public_context(media_id)
        playback_contexts = Playback_info().get_playback_context(media_id)
        media_id, title, publishedAt = parse_public_contexts(public_contexts)
        images = parse_playback_contexts(playback_contexts)

        path = self.folder_manager.create_image_folder(title, publishedAt)
        if path == "Already exists":
            logger.info(f"[IMG] {title} Already exists skip download.")
        elif path:
            self.image_parser.parse_and_download(images, path)


async def run_image_dl(media_id: str):
    orchestrator = MediaDownloadOrchestrator()
    await orchestrator.run_download(media_id)
