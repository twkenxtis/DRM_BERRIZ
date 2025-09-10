import asyncio
import os
import shutil
from pathlib import Path

import aiofiles
import aiofiles.os as aios
import httpx

from lib.ffmpeg.videoinfo import VideoInfo
from lib.ffmpeg.mux import FFmpegMuxer
from static.color import Color
from static.PublicInfo import PublicInfo_Custom
from unit.handle_log import setup_logging
from unit.parameter import paramstore


logger = setup_logging('reName', 'violet')


class SUCCESS:
    def __init__(self, downloader, json_data, community_name):
        self.downloader = downloader
        self.json_data = json_data
        self.publicinfo = PublicInfo_Custom(json_data)
        self.community_name = community_name
        self.base_dir = self.downloader.base_dir
        self.tempname = "temp_output_DO_NOT_DEL.mp4"
        self.path = Path(self.base_dir / self.tempname)

    async def when_success(self, success, decryption_key, merge_type):
        if success:
            logger.info(f"{Color.fg('light_gray')}Video file: {self.base_dir / 'video.ts'}{Color.reset()}")
            logger.info(f"{Color.fg('light_gray')}Audio file: {self.base_dir / 'audio.ts'}{Color.reset()}")
            await self.dl_thumbnail()
        
        # Mux video and audio with FFmpeg
        muxer = FFmpegMuxer(self.base_dir, decryption_key)
        
        if await muxer.mux_to_mp4(merge_type, self.tempname):
            await SUCCESS.re_name(self)
            if paramstore.get('clean_dl') is not False:
                await SUCCESS.clean_file(self, decryption_key, merge_type)
            else:
                logger.info(f"{Color.fg('yellow')}Skipping file cleaning, keep segments after done{Color.reset()}")
        elif paramstore.get('skip_merge') is True: 
            logger.info(f"{Color.fg('yellow')}Skipping file cleaning, keep segments after done{Color.reset()}")

    async def clean_file(self, had_drm, merge_type):
        base_dir = self.base_dir
        if os.path.exists(base_dir / "audio.ts"):
            # Files to delete
            if had_drm is None:
                file_paths = [
                    base_dir / "video.ts",
                    base_dir / "audio.ts",
                ]
            elif merge_type == 'mpd':
                file_paths = [
                    base_dir / "video_decrypted.ts",
                    base_dir / "video.ts",
                    base_dir / "audio_decrypted.ts",
                    base_dir / "audio.ts",
                ]
            elif merge_type == 'hls' and os.path.exists(base_dir / "audio.ts"):
                file_paths = [
                    base_dir / "video.ts",
                    base_dir / "audio.ts",
                ]
            elif merge_type == 'hls' and not os.path.exists(base_dir / "audio.ts"):
                file_paths = [
                    base_dir / "video.ts",
                ]

            for fp in file_paths:
                try:
                    await asyncio.to_thread(fp.unlink)
                    logger.info(f"{Color.fg('light_gray')}Removed file: {fp}{Color.reset()}")
                except FileNotFoundError:
                    logger.warning(f"File not found, skipping: {fp}")
                except Exception as e:
                    logger.error(f"Error removing file {fp}: {e}")

            for subfolder in ["audio", "video"]:
                dir_path = base_dir / subfolder
                try:
                    await asyncio.to_thread(shutil.rmtree, dir_path)
                    logger.info(f"{Color.fg('light_gray')}Force-removed directory: {dir_path}{Color.reset()}")
                except FileNotFoundError:
                    logger.warning(f"Directory not found, skipping: {dir_path}")
                except Exception as e:
                    logger.error(f"Error force-removing directory {dir_path}: {e}")

    async def re_name(self):
        d = (
            self.publicinfo.formatted_published_at[2:-6].replace("-", "")
        )
        video_codec, video_quality_label, video_audio_codec = await self.extract_video_info()
        filename = (
            f"{d} {self.community_name} - "
            + self.publicinfo.media_title
            + f" WEB-DL.{video_quality_label}.{video_codec}.{video_audio_codec}.mp4"
        )
        await aios.rename(self.path, Path(self.base_dir).parent / filename)
        logger.info(f"{Color.fg('yellow')}Final output file: {Color.reset()}{Color.fg('aquamarine')}{self.base_dir / filename}{Color.reset()}")
        
    async def extract_video_info(self):
        vv = VideoInfo(self.path)
        async with asyncio.TaskGroup() as tg:
            codec_task = tg.create_task(asyncio.to_thread(lambda: vv.codec))
            quality_task = tg.create_task(asyncio.to_thread(lambda: vv.quality_label))
            audio_task = tg.create_task(asyncio.to_thread(lambda: vv.audio_codec))

        video_codec = codec_task.result()
        video_quality_label = quality_task.result()
        video_audio_codec = audio_task.result()

        return video_codec, video_quality_label, video_audio_codec


    async def dl_thumbnail(self):
        thumbnail_url = self.publicinfo.media_thumbnail_url
        if not thumbnail_url:
            logger.warning("No thumbnail URL found")
            return

        headers = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip, deflate, br, zstd"}

        async with httpx.AsyncClient(http2=True, verify=True) as client:
            try:
                response = await client.get(thumbnail_url, headers=headers)
            except httpx.RequestError as e:
                logger.error(f"Request failed: {e}")
                return

        thumbnail_name = os.path.basename(thumbnail_url)
        save_path = Path(self.base_dir).parent / thumbnail_name

        if response.status_code == 200:
            async with aiofiles.open(save_path, "wb") as f:
                await f.write(response.content)
        else:
            logger.error(f"{response.status_code} {thumbnail_url}")
            logger.error("Thumbnail download failed")