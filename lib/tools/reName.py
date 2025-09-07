import logging
import os
import shutil

from logging.handlers import TimedRotatingFileHandler

import requests

from lib.ffmpeg.parse_mpd import MPDParser, MediaTrack, MPDContent
from lib.ffmpeg.videoinfo import VideoInfo
from lib.ffmpeg.mux import FFmpegMuxer
from static.color import Color
from unit.handle_log import setup_logging
from unit.parameter import paramstore
from unit.community import get_community


logger = setup_logging('reName', 'violet')


class SUCCESS:
    def __init__(self, downloader, json_data, community_name):
        self.downloader = downloader
        self.json_data = json_data
        self.community_name = community_name

    def when_success(self, success, decryption_key):
        if success:
            logger.info(f"{Color.fg('light_gray')}Video file: {self.downloader.base_dir / 'video.ts'}{Color.reset()}")
            logger.info(f"{Color.fg('light_gray')}Audio file: {self.downloader.base_dir / 'audio.ts'}{Color.reset()}")
            SUCCESS.dl_thumbnail(self)

        # Mux video and audio with FFmpeg
        muxer = FFmpegMuxer(self.downloader.base_dir, decryption_key)
        if muxer.mux_to_mp4():
            SUCCESS.re_name(self)
            if paramstore.get('clean_dl') is not False:
                SUCCESS.clean_file(self, decryption_key)
            else:
                logger.info(f"{Color.fg('yellow')}Skipping file cleaning, keep segments after done{Color.reset()}")
        elif paramstore.get('skip_merge') is True: 
            logger.info(f"{Color.fg('yellow')}Skipping file cleaning, keep segments after done{Color.reset()}")

    def clean_file(self, had_drm):
        base_dir = self.downloader.base_dir
        # Files to delete
        if had_drm is None:
            file_paths = [
                base_dir / "video.ts",
                base_dir / "audio.ts",
            ]
        else:
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
                logger.info(f"{Color.fg('light_gray')}Removed file: {fp}{Color.reset()}")
            except FileNotFoundError:
                logger.warning(f"File not found, skipping: {fp}")
            except Exception as e:
                logger.error(f"Error removing file {fp}: {e}")

        # Force-remove non-empty directories
        for subfolder in ["audio", "video"]:
            dir_path = base_dir / subfolder
            try:
                shutil.rmtree(dir_path)
                logger.info(f"{Color.fg('light_gray')}Force-removed directory: {dir_path}{Color.reset()}")
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
            f"{t} {self.community_name} - "
            + self.json_data.get("media", {}).get("title")
            + f" WEB-DL.{video_quality_label}.{video_codec}.{video_audio_codec}.mp4"
        )
        os.rename(
            self.downloader.base_dir / "output.mp4", self.downloader.base_dir / filename
        )
        logger.info(f"{Color.fg('yellow')}Final output file: {Color.reset()}{Color.fg('aquamarine')}{self.downloader.base_dir / filename}{Color.reset()}")

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
            
    async def get_community_name(self, community_id:int):
        n = await get_community(community_id)
        n = f"{n}"
        return n