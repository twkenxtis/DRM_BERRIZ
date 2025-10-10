import asyncio
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Tuple

import aiofiles
import aiofiles.os as aios
import httpx

from lib.__init__ import container, FilenameSanitizer, OutputFormatter, get_artis_list, use_proxy
from lib.mux.videoinfo import VideoInfo
from lib.mux.mux import FFmpegMuxer
from lib.load_yaml_config import CFG
from static.color import Color
from static.PublicInfo import PublicInfo_Custom
from static.parameter import paramstore
from unit.http.request_berriz_api import GetRequest
from unit.date.date import get_timestamp_formact
from unit.community.community import custom_dict
from unit.handle.handle_log import setup_logging


logger = setup_logging('reName', 'violet')


class SUCCESS:
    def __init__(self, downloader: Any, json_data: Dict[str, Any], community_name: str, custom_community_name: str) -> None:
        self.downloader: Any = downloader
        self.json_data: Dict[str, Any] = json_data
        self.publicinfo: PublicInfo_Custom = PublicInfo_Custom(json_data)
        self.community_name: str = community_name
        self.custom_community_name: str = custom_community_name
        self.base_dir: Path = self.downloader.base_dir
        self.tempname: str = f"temp_mux_{self.publicinfo.media_id}.{container}"
        self.path: Path = self.base_dir / self.tempname
        self.artis_list: List[Dict[str, Optional[str]]] = self.publicinfo.artist_list
        self.filenameSanitizer = FilenameSanitizer.sanitize_filename

    async def when_success(self, success: bool, decryption_key: Optional[Union[bytes, str]], merge_type: str) -> str | bool:
        """處理下載成功後的邏輯：下載縮圖、混流、重新命名與清理檔案"""
        if success:
            logger.info(f"{Color.fg('light_gray')}Video file: {self.base_dir / f'video.{container}'}{Color.reset()}")
            logger.info(f"{Color.fg('light_gray')}Audio file: {self.base_dir / f'audio.{container}'}{Color.reset()}")
        await self.dl_thumbnail()
        # Mux video and audio with FFmpeg
        muxer: FFmpegMuxer = FFmpegMuxer(self.base_dir, decryption_key)
        video_file_name = ''
        mux_bool_status = await muxer.mux_main(merge_type, self.path)
        if paramstore.get('skip_mux') is not True and paramstore.get('skip_merge') is not True:
            if mux_bool_status is True and not paramstore.get('nodl') is True:
                video_file_name = await SUCCESS.re_name(self)
            elif paramstore.get('nodl') is True:
                video_file_name = '[ SKIP-DL ]'
            elif paramstore.get('slice_path_fail') is True:
                video_file_name = '[ Fail to create folder for download slice ]'
            else:
                logger.warning("Mux failed, check console output for details")
                video_file_name = '[ Mux failed ]' + f'\n{Color.bg("ruby")}Keep all segments in temp folder{Color.reset()}'
            # 傳遞給 clean_file 的 had_drm 實際上是 decryption_key
            if paramstore.get('clean_dl') is not False and mux_bool_status is True:
                await SUCCESS.clean_file(self, decryption_key, merge_type)
            else:
                logger.info(f"{Color.fg('yellow')}Skipping file cleaning, keep segments after done{Color.reset()}")
        elif paramstore.get('skip_merge') is True and mux_bool_status is False:
            logger.info(f"{Color.fg('yellow')}Skipping file cleaning, keep segments after done{Color.reset()}")
            
        match video_file_name:
            case '':
                if paramstore.get('skip_merge'):
                    video_file_name = '[ User choese SKIP MERGE ]'
                    mux_bool_status = True
                if paramstore.get('skip_mux'):
                    video_file_name = '[ User choese SKIP MUX ]'
                    mux_bool_status = True
            case _:
                pass
        return video_file_name, mux_bool_status

    async def clean_file(self, had_drm: Optional[Union[bytes, str]], merge_type: str) -> None:
        """清理下載過程中的暫存檔案、加密檔案和暫存目錄"""
        base_dir: Path = self.base_dir
        if os.path.exists(base_dir / f"audio.{container}"):
            file_paths: List[Path] = []
            # Files to delete
            if had_drm is None:
                file_paths = [
                    base_dir / f"video.{container}",
                    base_dir / f"audio.{container}",
                ]
            elif merge_type == 'mpd':
                file_paths = [
                    base_dir / f"video_decrypted.{container}",
                    base_dir / f"video.{container}",
                    base_dir / f"audio_decrypted.{container}",
                    base_dir / f"audio.{container}",
                ]
            elif merge_type == 'hls' and os.path.exists(base_dir / f"audio.{container}"):
                file_paths = [
                    base_dir / f"video.{container}",
                    base_dir / f"audio.{container}",
                ]
            elif merge_type == 'hls' and not os.path.exists(base_dir / f"audio.{container}"):
                file_paths = [
                    base_dir / f"video.{container}",
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
                dir_path: Path = base_dir / subfolder
                try:
                    await asyncio.to_thread(shutil.rmtree, dir_path)
                    logger.info(f"{Color.fg('light_gray')}Force-removed directory: {dir_path}{Color.reset()}")
                except FileNotFoundError:
                    logger.warning(f"Directory not found, skipping: {dir_path}")
                except Exception as e:
                    logger.error(f"Error force-removing directory {dir_path}: {e}")

    async def re_name(self) -> str:
        """根據影片元數據和命名規則重新命名最終的 MP4 檔案"""
        fmt = CFG['output_template']['date_formact']
        fm:str = get_timestamp_formact(fmt) # %y%m%d_%H-%M
        dt: datetime = datetime.strptime(self.publicinfo.formatted_published_at, fm)
        d:str = dt.strftime(fm)
        safe_title: str = self.filenameSanitizer(self.publicinfo.media_title)
        video_codec: str
        video_quality_label: str
        video_audio_codec: str
        video_codec, video_quality_label, video_audio_codec = await self.extract_video_info()
        if get_artis_list(self.artis_list) == self.community_name or get_artis_list(self.artis_list) == self.custom_community_name:
            video_meta: Dict[str, str] = {
                "date": d,
                "title": safe_title,
                "artis": get_artis_list(self.artis_list).lower(),
                "community_name": self.custom_community_name,
                "quality": video_quality_label,
                "source": "Berriz",
                "video": video_codec,
                "audio": video_audio_codec,
                "tag": CFG['output_template']['tag']
            }
        elif get_artis_list(self.artis_list) != self.community_name or get_artis_list(self.artis_list) != self.custom_community_name:
            video_meta: Dict[str, str] = {
                "date": d,
                "title": safe_title,
                "artis": get_artis_list(self.artis_list),
                "community_name": self.custom_community_name,
                "quality": video_quality_label,
                "source": "Berriz",
                "video": video_codec,
                "audio": video_audio_codec,
                "tag": CFG['output_template']['tag']
            }
        filename_formact: str = CFG['output_template']['video']
        if video_codec == "{video}":
            filename_formact = filename_formact.replace('.{quality}', '')
            filename_formact = filename_formact.replace('.{video}', '')
        if video_audio_codec == "{audio}":
            filename_formact = filename_formact.replace('.{audio}', '')
        filename = OutputFormatter(filename_formact).format(video_meta) + f'.{container}'
        # 重新命名並移動到上級目錄
        await aios.rename(self.path, Path(self.base_dir).parent / filename)
        return filename

    async def extract_video_info(self) -> Tuple[str, str, str]:
        """異步提取最終 MP4 檔案的編解碼器、畫質標籤和音頻編解碼器"""
        vv: VideoInfo = VideoInfo(self.path)
        
        # 使用 TaskGroup 並將 FFmpeg 探針的同步操作包裝成異步
        async with asyncio.TaskGroup() as tg:
            codec_task: asyncio.Task[str] = tg.create_task(asyncio.to_thread(lambda: vv.codec))
            quality_task: asyncio.Task[str] = tg.create_task(asyncio.to_thread(lambda: vv.quality_label))
            audio_task: asyncio.Task[str] = tg.create_task(asyncio.to_thread(lambda: vv.audio_codec))
        video_codec: str = codec_task.result()
        video_quality_label: str = quality_task.result()
        video_audio_codec: str = audio_task.result()
        if video_audio_codec == 'unknown':
            if paramstore.get('no_video_audio') is True:
                video_audio_codec = '{audio}'
            else:
                logger.warning(f"Unknown audio codec: {video_audio_codec}")
                video_audio_codec = 'x'
        if video_codec == 'unknown':
            if paramstore.get('no_video_audio') is True:
                video_codec = '{video}'
            else:
                logger.warning(f"Unknown video codec: {video_codec}")
                video_codec = 'x'
        return video_codec, video_quality_label, video_audio_codec

    async def dl_thumbnail(self) -> None:
        """下載影片縮圖到上級目錄"""
        match paramstore.get('nothumbnails'):
            case True:
                logger.info(f"{Color.fg('light_gray')}Skip downloading{Color.reset()} {Color.fg('light_gray')}Vido Thumbnails")
            case _:
                thumbnail_url: Optional[str] = self.publicinfo.media_thumbnail_url
                if not thumbnail_url:
                    logger.warning("No thumbnail URL found")
                    return
                response: httpx.Response = await GetRequest().get_request(thumbnail_url, use_proxy)
                thumbnail_name: str = os.path.basename(thumbnail_url)
                save_path: Path = Path(self.base_dir).parent / f"thumbnails_{thumbnail_name}"
                try:
                    content: str = response.content
                    async with aiofiles.open(save_path, "wb") as f:
                        await f.write(content)
                except Exception as e:
                    logger.error(f"Thumbnail download failed: {e}")
                    raise RuntimeError("Thumbnail download failed") from e
