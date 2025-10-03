import asyncio
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Union, List

import aiofiles
import aiofiles.os as aios
import orjson

from lib.__init__ import dl_folder_name, OutputFormatter
from lib.load_yaml_config import CFG
from lib.tools.reName import SUCCESS
from static.color import Color
from static.PublicInfo import PublicInfo_Custom
from unit.community import custom_dict, get_community
from unit.handle_log import setup_logging
from unit.parameter import paramstore


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
        temp_folder_name: str = f"{self.time_str} {self.media_id} [{str(uuid.uuid1())[:17]}]"
        temp_name: str = self._sanitize_filename(temp_folder_name)
        temp_dir: Path = base_dir / temp_name / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir = base_dir
        self.output_dir = str(temp_dir.resolve())
        
        if self.get_artis_list() == community_name:
            video_meta: Dict[str, str] = {
                "date": self.time_str,
                "title": self.title,
                "community_name": community_name,
                "source": "Berriz",
                "tag": CFG['output_template']['tag']
            }
        elif self.get_artis_list() != community_name:
            video_meta: Dict[str, str] = {
                "date": self.time_str,
                "title": self.title,
                "artis": self.get_artis_list(),
                "community_name": community_name,
                "source": "Berriz",
                "tag": CFG['output_template']['tag']
            }
        folder_name: str = OutputFormatter(f"{CFG['Donwload_Dir_Name']['dir_name']}").format(video_meta)
        self.folder_name = folder_name
        return temp_dir
    
    def get_artis_list(self):
        self.artis_list: List[Dict[str, Optional[str]]]
        all_artos_list = set()
        for i in self.artis_list:
            if i.get('name'):
                all_artos_list.add(i['name'])
        all_artis_str: str  = " ".join(sorted(all_artos_list))
        return all_artis_str

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
            logger.error(f"Failed to delete folder: {e}")
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


class save_hls_mpd:
    def __init__(self, output_dir: Union[str, Path]) -> None:
        # 將 output_dir 設定為其父目錄，因為它指向 'temp' 資料夾
        self.output_dir: Path = Path(output_dir).parent
        self.max_retries: int = 3
        self.retry_delay: int = 2
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure the output directory exists."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def _write_file(self, file_path: Path, content: Union[str, bytes], mode: str = "wb") -> None:
        """Write content to a file with retry logic and atomic replacement."""
        tmp_path: Path = file_path.with_suffix(file_path.suffix + ".part")
        is_text_mode: bool = 'b' not in mode
        encoding: Optional[str] = 'utf-8' if is_text_mode else None
        for attempt in range(self.max_retries):
            try:
                async with aiofiles.open(tmp_path, mode, encoding=encoding) as f:
                    # 根據 content 類型，確保在正確模式下寫入
                    if is_text_mode and isinstance(content, bytes):
                        pass
                    elif not is_text_mode and isinstance(content, str):
                        # 如果是二進製模式但 content 是 str，可能需要編碼
                        content = content.encode('utf-8')
                    
                    await f.write(content)
                await aios.replace(tmp_path, file_path)
                return
            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue
                if await aios.path.exists(tmp_path):
                    await aios.remove(tmp_path)
                raise RuntimeError(f"Failed to write to {file_path} after {self.max_retries} attempts: {e}")
    
    async def mpd_to_folder(self, raw_mpd: Any) -> None:
        """Save MPD content (expecting an object with a .text attribute) to manifest.mpd."""
        if raw_mpd is None:
            return
        try:
            content: str = raw_mpd.text
            await self._write_file(self.output_dir / "manifest.mpd", content, mode="w")
        except AttributeError as e:
            raise ValueError("Invalid MPD object: missing 'text' attribute") from e

    async def hls_to_folder(self, raw_hls: str) -> None:
        """Save HLS content to manifest.m3u8."""
        if raw_hls is None:
            return
        await self._write_file(self.output_dir / "manifest.m3u8", raw_hls, mode="w")

    async def play_list_to_folder(self, raw_play_list: Optional[Dict[str, Any]]) -> None:
        """Save playlist JSON to meta.json."""
        if raw_play_list is None:
            return
        try:
            json_bytes: bytes = orjson.dumps(
                raw_play_list,
                option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS
            )
            await self._write_file(self.output_dir / "meta.json", json_bytes)
        except orjson.JSONEncodeError as e:
            raise ValueError("Failed to serialize playlist to JSON") from e


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
        s_obhect: save_hls_mpd = save_hls_mpd(output_dir)
        
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
