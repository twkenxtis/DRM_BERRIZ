import asyncio
import re
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import aiofiles
import xml.etree.ElementTree as ET

from lib.tools.reName import SUCCESS
from static.color import Color
from unit.handle_log import setup_logging
from unit.community import get_community, custom_dict


logger = setup_logging('video_folder', 'chocolate')


class Video_folder:
    def __init__(self, json_data):
        self.mpd_url = None
        self.json_data = json_data
        self.media_id = self.parse_mediaid()
        self.title = self.parse_title()
        self.published_at = self.parse_published_at()
        self.time_str = self.formact_time()
        self.output_dir = None

    async def video_folder_handle(self, community_name):
        base_dir = Path("downloads") / community_name / "videos"
        folder_name = f"{self.time_str} {self.media_id}"
        folder_name = re.sub(r'[\\/:\*\?"<>|]', "", folder_name).strip()
        output_dir = base_dir / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = str(output_dir.resolve())
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
                logger.info(f"{Color.fg('light_blue')}Renamed folder: From: {Color.reset()}{full_path}\n⤷ {Color.fg('light_yellow')}{new_path}{Color.reset()}")
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


async def mpd_to_folder(output_dir: str, raw_mpd: object):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    save_path = output_path / 'manifest.mpd'
    async with aiofiles.open(save_path, 'w') as f:
        await f.write(raw_mpd.text)

async def save_json_to_folder(output_dir: str, json_data: dict):
    output_path = Path(output_dir)
    media_id = json_data.get("media", {}).get("id")
    if not media_id:
        return 'json_data'
    save_path = output_path / f"{media_id}.json"
    try:
        async with aiofiles.open(save_path, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(json_data, indent=5, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Save JSON file error: {e}")

    
async def start_download_queue(decryption_key, json_data, mpd_content, raw_mpd):
    video_folder = Video_folder(json_data)
    media_id = video_folder.media_id
    community_name = await get_community_name(json_data)

    if type(community_name) == str:
        community_name = custom_dict(community_name)
    if community_name is None:
        community_name = await get_community_name(json_data)
        
    output_dir = await video_folder.video_folder_handle(community_name)
    if output_dir is not None:
        
        await asyncio.gather(
            asyncio.create_task(mpd_to_folder(output_dir, raw_mpd)),
            asyncio.create_task(save_json_to_folder(output_dir, json_data))
        )
        from lib.download import MediaDownloader

        downloader = MediaDownloader(media_id, output_dir)
        success = await downloader.download_content(mpd_content)
        s = SUCCESS(downloader, json_data, community_name)
        s.when_success(success, decryption_key)
        video_folder.re_name_folder()
    else:
        logger.error("Failed to create output directory.")
        raise ValueError

            
async def get_community_name(json_data):
    community_id = json_data.get('media', {}).get('community_id')
    n = await get_community(community_id)
    n = f"{n}"
    return n
