import re
from pathlib import Path

from lib.download import logger
from lib.download import DateTimeFormatter

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