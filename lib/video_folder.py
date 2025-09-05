import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from logging.handlers import TimedRotatingFileHandler


from lib.tools.reName import SUCCESS
from static.color import Color


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    os.makedirs("logs", exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    logger = logging.getLogger("video_folder")
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
        filename="logs/video_folder.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)
    logger.addHandler(app_file_handler)

    return logger


logger = setup_logging()


class Video_folder:
    def __init__(self, json_data):
        self.json_data = json_data
        self.media_id = self.parse_mediaid()
        self.title = self.parse_title()
        self.published_at = self.parse_published_at()
        self.time_str = self.formact_time()
        self.output_dir = self.video_folder_handle()

    def video_folder_handle(self):
        base_dir = Path("downloads") / "videos"
        folder_name = f"{self.time_str} {self.media_id}"
        folder_name = re.sub(r'[\\/:\*\?"<>|]', "", folder_name).strip()
        output_dir = base_dir / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def parse_mediaid(self):
        logger.info(
            f"{Color.fg('light_gray')}title:{Color.reset()} "
            f"{Color.fg('bright_magenta')}{self.json_data.get('media', {}).get('title', '')}{Color.reset()}"
        )
        return self.json_data.get("media", {}).get("id", "")

    def parse_title(self):
        logger.info(
            f"{Color.fg('light_gray')}title:{Color.reset()} "
            f"{Color.fg('olive')}{self.json_data.get('media', {}).get('title', '')}{Color.reset()}"
        )
        return self.json_data.get("media", {}).get("title", "")

    def parse_published_at(self):
        return self.json_data.get("media", {}).get("published_at", "")

    def formact_time(self):
        time_str = DateTimeFormatter.format_published_at(self.published_at)
        return time_str

    def get_unique_folder_name(self, base_name: str, parent_dir: Path) -> Path:
        new_path = parent_dir / base_name
        counter = 1
        while new_path.exists():
            new_path = parent_dir / f"{base_name} ({counter})"
            counter += 1
        return new_path

    def re_name_folder(self):
        full_path = Path.cwd() / Path(self.output_dir)
        original_name = full_path.name
        parent_dir = full_path.parent

        if self.media_id in original_name:
            base_name = original_name.replace(self.media_id, self.title)
            new_path = self.get_unique_folder_name(base_name, parent_dir)

            try:
                full_path.rename(new_path)
                logger.info(f"{Color.fg('light_blue')}Renamed folder: From: {Color.reset()}{full_path}\nTo: {Color.fg('light_yellow')}{new_path}{Color.reset()}")
            except Exception as e:
                logger.error(f"Failed to rename folder: {e}")
        else:
            logger.warning(
                f"UUID '{self.media_id}' not found in folder name: {original_name}"
            )


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
    if output_dir is not None:
        from lib.download import MediaDownloader

        downloader = MediaDownloader(media_id, output_dir)
        success = await downloader.download_content(mpd_content)
        s = SUCCESS(downloader, json_data)
        s.when_success(success, decryption_key)
        video_folder.re_name_folder()
    else:
        logger.error("Failed to create output directory.")
        raise ValueError
