import asyncio
import re
import sys
import shutil
import time
import random
from pathlib import Path
from typing import Any, Dict, Optional, Union, List

import aiofiles
import aiofiles.os as aios
import orjson

from lib.__init__ import dl_folder_name, OutputFormatter, get_artis_list
from lib.load_yaml_config import CFG
from lib.rename import SUCCESS
from lib.save_json_data import save_json_data
from static.color import Color
from static.PublicInfo import PublicInfo_Custom
from unit.community.community import custom_dict, get_community
from unit.handle.handle_log import setup_logging
from static.parameter import paramstore


logger = setup_logging('video_folder', 'chocolate')


class Video_folder:
    def __init__(self, json_data: Dict[str, Any]) -> None:
        self.mpd_url: Optional[str] = None
        self.json_data: Dict[str, Any] = json_data
        self.publicinfo: PublicInfo_Custom = PublicInfo_Custom(json_data)
        self.media_id: str = self.publicinfo.media_id
        self.title: str = self.publicinfo.media_title
        self.published_at: str = self.publicinfo.media_published_at
        self.time_str: str = self.publicinfo.formatted_published_at
        self.cmid: int = self.publicinfo.media_community_id
        self.artis_list: List[Dict[str, Optional[str]]] = self.publicinfo.artist_list
        self.folder_name = None
        self.base_dir = None
        self.output_dir: Optional[str] = None

    async def video_folder_handle(self) -> Path:
        """根據 community_name 和媒體資訊建立下載資料夾路徑"""
        community_name = (
            # 嘗試取得並處理社羣名稱這個表達式會先被執行
            # 1. 呼叫 get_community_name() 取得原始資料
            # 2. 呼叫 custom_dict() 處理原始資料
            #    如果 custom_dict() 的結果是「有值的」（即非 None, 非 False, 非 0, 非空容器），
            #    則整個 or 運算式結束，將結果賦值給 community_name
            #    如果 custom_dict() 的結果是「無值的」（例如 None 或空字串），
            #    則執行 or 後面的部分
            await custom_dict(await self.get_community_name(self.cmid)) 
        ) or (
            # 只有當 or 之前的表達式結果為「無值」時，這個部分才會被執行
            # 目的：作為一個備用方案 (Fallback)，重新執行一次 get_community_name()，
            #      並將這次的結果（未經 custom_dict 處理）賦值給 community_name
            await self.get_community_name(self.cmid)
        )
        base_dir: Path = Path(dl_folder_name) / community_name / "videos"
        temp_folder_name: str = f"{self.time_str} {self.media_id} [{str(random.randint(10**16, 10**17 - 1))}]"
        temp_name: str = self._sanitize_filename(temp_folder_name)
        temp_dir: Path = base_dir / temp_name / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir = base_dir
        self.output_dir = str(temp_dir.resolve())
        
        if get_artis_list(self.artis_list) == community_name:
            video_meta: Dict[str, str] = {
                "date": self.time_str,
                "title": self.title,
                "community_name": community_name,
                "source": "Berriz",
                "tag": CFG['output_template']['tag']
            }
        elif get_artis_list(self.artis_list) != community_name:
            video_meta: Dict[str, str] = {
                "date": self.time_str,
                "title": self.title,
                "artis": get_artis_list(self.artis_list),
                "community_name": community_name,
                "source": "Berriz",
                "tag": CFG['output_template']['tag']
            }
        folder_name: str = OutputFormatter(f"{CFG['Donwload_Dir_Name']['dir_name']}").format(video_meta)
        self.folder_name = folder_name
        return temp_dir

    def get_unique_folder_name(self, base_name: str, full_path: Path) -> Path:
        """確保資料夾名稱唯一性，避免衝突"""
        base_name = self._sanitize_filename(base_name)
        new_path: Path = Path(full_path).parent / base_name
        counter: int = 1
        while new_path.exists():
            new_path = Path(full_path).parent / f"{base_name} ({counter})"
            counter += 1
        return new_path
    
    def _sanitize_filename(self, name: str) -> str:
        """Strip invalid characters and handle Windows reserved names."""
        cleaned = re.sub(r'[\\/:*?"<>|]', "", name).rstrip(". ")
        reserved = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        return f"{cleaned}_" if cleaned.upper() in reserved else cleaned

    async def re_name_folder(self, video_file_name:str) -> None:
        """將下載完成後的暫存資料夾名稱重新命名為最終標題"""
        if self.output_dir is None:
             logger.warning("Output directory not set, skipping folder rename.")
             return
        
        new_path: Path = self.base_dir / self.folder_name
        full_path: Path = Path.cwd() / Path(self.output_dir)
        original_name: str = full_path.parent.name
        
        if self.media_id not in original_name:
            logger.warning(
                f"UUID '{self.media_id}' not found in folder name: {original_name}"
            )
            return
            
        await self.del_temp_folder(full_path)
        new_path: Path = self.get_unique_folder_name(self.folder_name, new_path)

        max_retries: int = 5
        delay_seconds: int = 1
        for attempt in range(1, max_retries + 1):
            try:
                await aios.rename(full_path.parent, new_path)
                logger.info(
                    f"{Color.fg('light_blue')}Renamed folder From: {Color.reset()}"
                    f"{Color.fg('light_gray')}{full_path.parent} "
                    f"{Color.fg('dark_green')}{new_path}{Color.reset()}"
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
        logger.info(
            f"{Color.fg('yellow')}Final output file: {Color.reset()}"
            f"{Color.fg('aquamarine')}{Path(new_path)}\n　➥ {video_file_name}{Color.reset()}"
            )

    async def del_temp_folder(self, temp_path: Path) -> None:
        """刪除下載完成後的 'temp' 暫存資料夾"""
        try:
            if temp_path.exists():
                if temp_path.exists() and (paramstore.get('skip_merge') is None and paramstore.get('skip_mux') is None):
                    await aios.rmdir(temp_path)
        except TypeError:
            logger.warning(f'Fail to del temp folder -> {temp_path}')
        except Exception as e:
            shutil.rmtree(temp_path, ignore_errors=True)
            sys.exit(1)
        
    async def save_json_to_folder(self, output_dir: str) -> None:
        """將 JSON 資料儲存到下載資料夾中"""
        output_path: Path = Path(output_dir).parent
        save_path: Path = output_path / f"{self.media_id}.json"
        try:
            serialized: bytes = orjson.dumps(
                self.json_data,
                option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS
            )
            serialized_str: str = serialized.decode('utf-8')

            async with aiofiles.open(save_path, mode='w', encoding='utf-8') as f:
                await f.write(serialized_str)
        except Exception as e:
            logger.error(f"Save JSON file error: {e}")
            sys.exit(1)

    async def get_community_name(self, community_id: int) -> str:
        """獲取媒體所屬的社群名稱"""
        # 假設 get_community 異步返回社群名稱字串
        n: Any = await get_community(community_id)
        return str(n)


async def start_download_queue(
    decryption_key: Optional[Union[bytes, str]], 
    json_data: Dict[str, Any], 
    mpd_content: Optional[Dict[str, Any]], 
    raw_mpd: Any, 
    hls_playback_url: str, 
    raw_hls: str
) -> None:
    """協調資料夾創建、資訊儲存、下載和後續處理的整個流程"""
    
    if mpd_content is None:
        logger.error("Failed to parse MPD content.")
        return
    
    publicinfo: PublicInfo_Custom = PublicInfo_Custom(json_data)
    video_folder_obj: Video_folder = Video_folder(json_data)
    
    media_id: str = publicinfo.media_id
    community_name = await video_folder_obj.get_community_name(publicinfo.media_community_id)
    output_dir: Path = await video_folder_obj.video_folder_handle()
    if output_dir is not None:
        s_obhect: save_json_data = save_json_data(output_dir)
        # 異步並行儲存 manifest 和 JSON 檔案
        await asyncio.gather(
            asyncio.create_task(s_obhect.mpd_to_folder(raw_mpd)),
            asyncio.create_task(s_obhect.hls_to_folder(raw_hls)),
            asyncio.create_task(video_folder_obj.save_json_to_folder(str(output_dir))),
            asyncio.create_task(s_obhect.play_list_to_folder(mpd_content))
        )
        
        # 延遲匯入 MediaDownloader
        from lib.download import MediaDownloader
        downloader: Any = MediaDownloader(media_id, output_dir)
        
        success: bool
        merge_type: str
        success, merge_type = await downloader.download_content(mpd_content)
        
        # 處理成功後的混流、重命名和清理
        s: SUCCESS = SUCCESS(downloader, json_data, community_name)
        video_file_name = await s.when_success(success, decryption_key, merge_type)
        await video_folder_obj.re_name_folder(video_file_name)
    else:
        logger.error("Failed to create output directory.")
        raise ValueError
