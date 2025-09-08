import asyncio
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Callable
import aiohttp
import aiofiles

from tqdm.asyncio import tqdm_asyncio

from lib.ffmpeg.parse_mpd import MPDContent, MPDParser, MediaTrack
from lib.video_folder import start_download_queue
from static.color import Color
from unit.handle_log import setup_logging
from unit.parameter import paramstore


USER_AGENT = "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36"


logger = setup_logging('download', 'peach')


class MediaDownloader:
    def __init__(self, media_id: str, outout_dir: str):
        self.media_id = media_id
        self.base_dir = outout_dir
        self.session = None

    def _get_file_extension(self, mime_type: str) -> str:
        """Determine file extension based on MIME type for DASH streaming"""
        mime_type = mime_type.lower()
        if "application/dash+xml" in mime_type:
            return ".m4v"
        if "video/mp4" in mime_type:
            return ".mp4"
        if "audio/mp4" in mime_type:
            return ".m4a"
        if "video/webm" in mime_type:
            return ".webm"
        if "audio/webm" in mime_type:
            return ".weba"
        if "text/vtt" in mime_type or "application/x-subrip" in mime_type:
            return ".vtt"
        if "application/octet-stream" in mime_type:
            return ".m4s"
        return ".ts"

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(limit_per_host=27)
            timeout = aiohttp.ClientTimeout(total=600)
            self.session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, headers={"User-Agent": USER_AGENT}
            )

    async def _download_file(self, url: str, save_path: Path, 
                            chunk_size: int = 128 * 1024, 
                            max_retries: int = 2,
                            progress_callback: Optional[Callable] = None) -> bool:
        retries = 0
        while retries <= max_retries:
            await self._ensure_session()
            try:
                async with self.session.get(url) as response:
                    if response.status not in (200, 206):
                        logger.warning(f"Request failed with status {response.status}, retrying...")
                        retries += 1
                        await asyncio.sleep(1 ** retries)
                        continue
                    
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    total_size = int(response.headers.get('content-length', 0))
                    
                    async with aiofiles.open(save_path, "wb") as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(chunk_size):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(len(chunk))
                    return True
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Download attempt {retries + 1} failed: {str(e)}")
                retries += 1
                if retries <= max_retries:
                    await asyncio.sleep(2 ** retries)
                else:
                    logger.error(f"Download failed after {max_retries} retries: {url}")
                    if save_path.exists():
                        save_path.unlink()
                    return False
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                if save_path.exists():
                    save_path.unlink()
                return False
        
        return False

    async def download_track(self, track: MediaTrack, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        track_dir.mkdir(exist_ok=True)

        logger.info(
            f"{Color.fg('light_gray')}Start downloading{Color.reset()} "
            f"{Color.bg('cyan')}{track_type}{Color.reset()} track: {Color.fg('cyan')}{track.id}{Color.reset()} "
            f"[Bitrate: {Color.fg('violet')}{track.bandwidth / 1000}k{Color.reset()}]"
            f"[Codec: {Color.fg('light_green')}{track.codecs}{Color.reset()}]"
            f"[Type: {Color.fg('light_yellow')}{track.mime_type}{Color.reset()}]"
            f"[Resolution: {Color.fg('light_magenta')}{track.height} x {track.width}{Color.reset()}]"
        )

        # Get appropriate extension for files
        file_ext = self._get_file_extension(track.mime_type)

        # Download initialization segment
        init_path = track_dir / f"init{file_ext}"
        if not await self._download_file(track.init_url, init_path):
            logger.error(f"{track_type} Initialization file download failed")
            return False

        # Download media segments with progress bar
        tasks = []
        for i, url in enumerate(track.segment_urls):
            seg_path = track_dir / f"seg_{i}{file_ext}"
            tasks.append(self._download_file(url, seg_path))
        
        # 使用 tqdm 包裝 gather
        results = await tqdm_asyncio.gather(
            *tasks,
            ascii="-#",
            desc=f"{track_type} process",
            unit="file",
            bar_format="{desc:6}: {percentage:1.0f} %  |{bar:150}| {n_fmt:>2}/{total_fmt:<2} files",
            ncols=150,
            colour='MAGENTA'
        )
        
        success_count = sum(results)
        
        logger.info(
            f"{Color.fg('plum')}{track_type} Split download complete: Success "
            f"{Color.fg('light_yellow')}{success_count}{Color.reset()}/{len(results)}{Color.reset()}"
        )
        return success_count == len(results)

    async def _merge_track(self, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        output_file = self.base_dir / f"{track_type}.ts"

        init_files = list(track_dir.glob("init.*"))
        if not init_files:
            logger.warning(f"Could not find {track_type} initialization file")
            return False

        segments = sorted(
            track_dir.glob("seg_*.*"), key=lambda x: int(x.stem.split("_")[1])
        )
        if not segments:
            logger.warning(f"No {track_type} fragment files found")
            return False

        logger.info(f"{Color.fg('light_gray')}Merge{Color.reset()} {Color.fg('light_gray')}{track_type} "
                    f"{Color.reset()}{Color.fg('light_gray')}tracks{Color.reset()}:{len(segments)} "
                    f"{Color.fg('yellow')}{Color.reset()}{Color.fg('light_gray')}segments{Color.reset()}"
                    )
        result = await MediaDownloader.binary_merge(output_file, init_files, segments, track_type)
        return result

    @staticmethod
    def _sync_process_chunk(segments: List[Path], temp_file: Path):
        """同步處理文件塊到臨時文件"""
        try:
            with open(temp_file, "wb") as outfile:
                for seg in segments:
                    with open(seg, "rb") as infile:
                        shutil.copyfileobj(infile, outfile)
            return True
        except Exception as e:
            logger.error(f"Failed to process chunk {temp_file}: {str(e)}")
            return e

    @staticmethod
    async def binary_merge(output_file: Path, init_files: List[Path], segments: List[Path], track_type: str) -> bool:
        try:
            # 創建臨時目錄
            temp_dir = output_file.parent / f"temp_{track_type}"
            temp_dir.mkdir(exist_ok=True)
            
            # 使用線程池執行阻塞的IO操作
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor() as pool:
                # 複製初始化文件
                await loop.run_in_executor(pool, shutil.copy2, init_files[0], output_file)
                
                # 分塊處理
                chunk_size = 50
                chunks = [segments[i:i + chunk_size] for i in range(0, len(segments), chunk_size)]
                
                # 並行處理每個塊到臨時文件
                tasks = []
                temp_files = []
                
                for i, chunk in enumerate(chunks):
                    temp_file = temp_dir / f"chunk_{i}.tmp"
                    temp_files.append(temp_file)
                    tasks.append(loop.run_in_executor(
                        pool, MediaDownloader._sync_process_chunk, chunk, temp_file
                    ))
                
                # 等待所有任務完成
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 檢查結果
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Chunk {i} processing failed: {str(result)}")
                        # 清理臨時文件
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return False
            
            # 合併所有臨時文件到最終輸出文件
            with open(output_file, "ab") as outfile:
                for temp_file in temp_files:
                    if temp_file.exists():
                        with open(temp_file, "rb") as infile:
                            shutil.copyfileobj(infile, outfile)
            
            # 清理臨時文件
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            logger.info(f"{Color.fg('light_gray')}{track_type} Merger completed: {output_file}{Color.reset()}")
            return True
            
        except Exception as e:
            logger.error(f"{track_type} Merger failed: {str(e)}")
            # 清理臨時文件
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    async def download_content(self, mpd_content: MPDContent):
        try:
            tasks = []

            if mpd_content.audio_track:
                tasks.append(self.download_track(mpd_content.audio_track, "audio"))
            if mpd_content.video_track and mpd_content.audio_track:
                tasks.append(self.download_track(mpd_content.video_track, "video"))

            download_results = await asyncio.gather(*tasks)
            
            if paramstore.get('skip_merge') is not True:
                merge_results = []
                if mpd_content.video_track and download_results[0]:
                    merge_results.append(await self._merge_track("video"))
                if mpd_content.audio_track and (
                    len(download_results) > 1 and download_results[1]
                ):
                    merge_results.append(await self._merge_track("audio"))

                return all(merge_results)
            else:
                logger.info(f"{Color.fg('light_gray')}Skip merge because --skip-merge is {Color.fg('cyan')}True{Color.reset()}")
        finally:
            if self.session:
                await self.session.close()


async def run_dl(mpd_uri, decryption_key, json_data, raw_mpd):
    parser = MPDParser(raw_mpd, mpd_uri)
    mpd_content = parser.get_highest_quality_content()

    if not mpd_content.video_track and not mpd_content.audio_track:
        logger.error("Error: No valid audio or video tracks found in MPD.")
        return

    if mpd_content.drm_info and mpd_content.drm_info.get("default_KID"):
        logger.info(
            f"\nEncrypted content detected (KID: {mpd_content.drm_info['default_KID']})"
        )

    await start_download_queue(decryption_key, json_data, mpd_content, raw_mpd)
