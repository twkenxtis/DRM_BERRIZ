import asyncio
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import aiofiles
import aiofiles.os as aios
import orjson

from lib.tools.reName import SUCCESS
from static.color import Color
from static.PublicInfo import PublicInfo_Custom
from unit.community import custom_dict, get_community
from unit.handle_log import setup_logging


logger = setup_logging('video_folder', 'chocolate')


class Video_folder:
    def __init__(self, json_data):
        self.mpd_url = None
        self.json_data = json_data
        self.publicinfo = PublicInfo_Custom(json_data)
        self.media_id = self.publicinfo.media_id
        self.title = self.publicinfo.media_title
        self.published_at = self.publicinfo.media_published_at
        self.time_str = self.formact_time()
        self.output_dir = None

    async def video_folder_handle(self, community_name):
        base_dir = Path("downloads") / community_name / "videos"
        folder_name = f"{self.time_str} {self.media_id}"
        folder_name = re.sub(r'[\\/:\*\?"<>|]', "", folder_name).strip()
        output_dir = base_dir / folder_name / "temp"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = str(output_dir.resolve())
        return output_dir

    def formact_time(self):
        time_str = DateTimeFormatter.format_published_at(self.published_at)
        return time_str

    def get_unique_folder_name(self, base_name: str, full_path: Path) -> Path:
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            base_name = base_name.replace(char, '_')
            new_path = Path(full_path).parent / base_name
            counter = 1
            while new_path.exists():
                new_path = Path(full_path).parent / f"{base_name} ({counter})"
                counter += 1
            return new_path

    async def re_name_folder(self):
        full_path = Path.cwd() / Path(self.output_dir)
        original_name = full_path.parent.name
        if self.media_id not in original_name:
            logger.warning(
                f"UUID '{self.media_id}' not found in folder name: {original_name}"
            )
            return
        await self.del_temp_folder(full_path)
        base_name = original_name.replace(self.media_id, self.title).strip()
        new_path = self.get_unique_folder_name(base_name, full_path.parent)

        max_retries = 5
        delay_seconds = 1
        for attempt in range(1, max_retries + 1):
            try:
                await aios.rename(full_path.parent, new_path)
                logger.info(
                    f"{Color.fg('light_blue')}Renamed folder From: {Color.reset()}"
                    f"{Color.fg('light_gray')}{full_path}\n⤷ "
                    f"{Color.fg('light_yellow')}{new_path}{Color.reset()}"
                )
                break
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"All {max_retries} retries failed. Last error: {e}")
                else:
                    logger.warning(
                        f"Attempt {attempt} failed: {e}.")
                    logger.info(f"Retrying in {Color.fg('mist')}{delay_seconds}s {Color.reset()}")
                    time.sleep(delay_seconds)
                    
    async def del_temp_folder(self, temp_path):
        try:
            if temp_path.exists():
                    await aios.rmdir(temp_path)
        except TypeError:
            logger.warning(f'Fail to del temp folder -> {temp_path}')
            return
        except Exception as e:
            logger.error(f"Failed to delete folder: {e}")
            sys.exit(1)
        
    async def save_json_to_folder(self, output_dir: str):
        output_path = Path(output_dir).parent
        save_path = output_path / f"{self.media_id}.json"
        try:
            serialized = orjson.dumps(
                self.json_data,
                option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS
            ).decode('utf-8')

            async with aiofiles.open(save_path, mode='w', encoding='utf-8') as f:
                await f.write(serialized)
        except Exception as e:
            logger.error(f"Save JSON file error: {e}")
            sys.exit(1)

    async def get_community_name(self):
        n = await get_community(self.publicinfo.media_community_id)
        return n


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


class save_hls_mpd:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir).parent
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    async def mpd_to_folder(self, raw_mpd: object):
        if raw_mpd is not None:
            save_path = self.output_dir / 'manifest.mpd'
            save_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(save_path, 'w') as f:
                await f.write(raw_mpd.text)

    async def hls_to_folder(self, raw_hls: object):
        if raw_hls is not None:
            save_path = self.output_dir / 'manifest.m3u8'
            save_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(save_path, 'w') as f:
                await f.write(raw_hls)
                
    async def play_list_to_folder(self, raw_play_list: object):
        json_bytes = orjson.dumps(
            raw_play_list,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
        )
        save_path = self.output_dir / "meta.json"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = save_path.with_suffix(".json.part")

        async with aiofiles.open(tmp_path, "wb") as f:
            await f.write(json_bytes)
        tmp_path.replace(save_path)


async def start_download_queue(decryption_key, json_data, mpd_content, raw_mpd, hls_playback_url, raw_hls):
    
    if mpd_content is None:
        logger.error("Failed to parse MPD content.")
        return
    
    video_folder_obj = Video_folder(json_data)
    
    media_id = video_folder_obj.media_id
    community_name = await video_folder_obj.get_community_name()

    if type(community_name) == str:
        community_name = custom_dict(community_name)
    if community_name is None:
        community_name = await video_folder_obj.get_community_name()
        
    output_dir = await video_folder_obj.video_folder_handle(community_name)
    if output_dir is not None:
        s_obhect = save_hls_mpd(output_dir)
        await asyncio.gather(
            asyncio.create_task(s_obhect.mpd_to_folder(raw_mpd)),
            asyncio.create_task(s_obhect.hls_to_folder(raw_hls)),
            asyncio.create_task(video_folder_obj.save_json_to_folder(output_dir)),
            asyncio.create_task(s_obhect.play_list_to_folder(mpd_content))
        )
        from lib.download import MediaDownloader

        downloader = MediaDownloader(media_id, output_dir)
        success, merge_type = await downloader.download_content(mpd_content)
        s = SUCCESS(downloader, json_data, community_name)
        await s.when_success(success, decryption_key, merge_type)
        await video_folder_obj.re_name_folder()
    else:
        logger.error("Failed to create output directory.")
        raise ValueError