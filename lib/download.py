import asyncio
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import aiofiles
import aiohttp
from tqdm.asyncio import tqdm_asyncio

from lib.ffmpeg.parse_hls import HLS_Paser
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
            connector = aiohttp.TCPConnector(limit_per_host=50)
            timeout = aiohttp.ClientTimeout(total=600)
            self.session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, headers={"User-Agent": USER_AGENT}
            )

    async def _download_file(self, url: str, save_path: Path, 
                            chunk_size: int = 384 * 1024, 
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
                    await asyncio.sleep(1 ** retries)
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

    async def download_track(self, track: MediaTrack, track_type: str, merge_type:str) -> bool:
        track_dir = self.base_dir / track_type
        track_dir.mkdir(exist_ok=True)

        if merge_type == 'hls':
            slice_parameters = track
            file_ext = '.ts'
            track_id = track[0].split('/')[-2]
            logger.info(
                f"{Color.fg('light_gray')}Start downloading{Color.reset()} "
                f"{Color.bg('cyan')}{track_type}{Color.reset()} track: {Color.fg('cyan')}{track_id}{Color.reset()} "
            )
        else:
            slice_parameters = track.segment_urls
            # Get appropriate extension for files
            file_ext = self._get_file_extension(track.mime_type)
            track_id = track.id

            # Download initialization segment
            init_path = track_dir / f"init{file_ext}"
            if not await self._download_file(track.init_url, init_path):
                logger.error(f"{track_type} Initialization file download failed")
                return False
            logger.info(
                f"{Color.fg('light_gray')}Start downloading{Color.reset()} "
                f"{Color.bg('cyan')}{track_type}{Color.reset()} track: {Color.fg('cyan')}{track_id}{Color.reset()} "
                f"[Bitrate: {Color.fg('violet')}{track.bandwidth / 1000}k{Color.reset()}]"
                f"[Codec: {Color.fg('light_green')}{track.codecs}{Color.reset()}]"
                f"[Type: {Color.fg('light_yellow')}{track.mime_type}{Color.reset()}]"
                f"[Resolution: {Color.fg('light_magenta')}{track.height} x {track.width}{Color.reset()}]"
            )
        return await self.task_and_dl(slice_parameters, track_dir, file_ext, track_type)

    async def task_and_dl(self ,slice_parameters, track_dir, file_ext, track_type):
        # Download media segments with progress bar
        tasks = []
        for i, url in enumerate(slice_parameters):
            seg_path = track_dir / f"seg_{i}{file_ext}"
            tasks.append(self._download_file(url, seg_path))
        
        # 使用 tqdm 包裝 gather
        results = await tqdm_asyncio.gather(
            *tasks,
            ascii="-#",
            desc=f"{track_type} process",
            unit="file",
            bar_format="{desc:6}: {percentage:1.0f} % {n_fmt:>2}/{total_fmt:<2} files",
            ncols=150,
            colour='MAGENTA',
            leave=True
        )
        
        success_count = sum(results)
        
        logger.info(
            f"{Color.fg('plum')}{track_type} Split download complete: Success "
            f"{Color.fg('light_yellow')}{success_count}{Color.reset()}/{len(results)}{Color.reset()}"
        )
        return success_count == len(results)

    async def _merge_track(self, track_type: str, merge_type: str) -> bool:
        track_dir = self.base_dir / track_type
        output_file = self.base_dir / f"{track_type}.ts"
        init_files = list(track_dir.glob("init.*"))

        if not init_files and merge_type == 'mpd':
            logger.warning(f"Could not find {track_type} initialization file")
            return False

        segments = sorted(
            track_dir.glob("seg_*.*"), key=lambda x: int(x.stem.split("_")[1])
        )
        if not segments:
            logger.warning(f"No {track_type} fragment files found")
            return False

        logger.info(f"{Color.fg('light_gray')}Merge{Color.reset()} {Color.fg('light_gray')}{track_type} "
                    f"{Color.reset()}{Color.fg('light_gray')}tracks{Color.reset()}: {len(segments)} "
                    f"{Color.fg('yellow')}{Color.reset()}{Color.fg('light_gray')}segments{Color.reset()}"
                    )
        result = await MediaDownloader.binary_merge(output_file, init_files, segments, track_type, merge_type)
        return result

    @staticmethod
    def process_chunk(segments: List[Path], temp_file: Path) -> bool:
        try:
            # 以 二進位 寫入模式 開啟臨時文件（覆寫）
            with open(temp_file, "wb") as outfile:
                for seg in segments:
                    # 以 二進位 讀取模式 開啟每個 segment
                    with open(seg, "rb") as infile:
                        # 使用 copyfileobj 直接複製整個文件
                        shutil.copyfileobj(infile, outfile)
            return True

        except Exception as e:
            logger.error(f"Failed to process chunk {temp_file}: {e}")
            return False

    @staticmethod
    async def binary_merge(output_file: Path,
                        init_files: List[Path],
                        segments: List[Path],
                        track_type: str,
                        merge_type: str
                        ) -> bool:
        temp_dir = output_file.parent / f"temp_{track_type}"
        temp_dir.mkdir(exist_ok=True)
        
        loop = asyncio.get_event_loop()
        max_workers = min(64, os.cpu_count() * 4)
        chunk_size = 50
        chunks = [segments[i:i + chunk_size] for i in range(0, len(segments), chunk_size)]
        temp_files = []
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {}
                
                # 1. For MPD, submit the initialization file copy task
                if merge_type == 'mpd' and init_files:
                    copy_future = pool.submit(shutil.copy2, init_files[0], output_file)
                    futures[copy_future] = "init"
                # For HLS, no init file copy is needed; output_file will be created during merge
                
                # 2. Submit all segment chunk processing tasks
                for idx, chunk in enumerate(chunks):
                    temp_file = temp_dir / f"chunk_{idx}.tmp"
                    temp_files.append(temp_file)
                    fut = pool.submit(MediaDownloader.process_chunk, chunk, temp_file)
                    futures[fut] = idx
                
                # 3. Process completed or failed tasks
                for fut in as_completed(futures):
                    tag = futures[fut]
                    try:
                        fut.result()
                        if tag == "init":
                            logger.info(f"{track_type} init file copied")
                        else:
                            logger.debug(f"{track_type} chunk {tag} done")
                    except Exception as e:
                        logger.error(f"{track_type} task {tag} failed: {e}")
                        # Cancel remaining tasks and clean up
                        pool.shutdown(cancel_futures=True)
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return False
                
                # 4. Merge all temporary files into the final output file
                async def merge_with_aiofiles(temp_files: List[Path], output_file: Path):
                    # Open output file in write mode for HLS (since no init file) or append mode for MPD
                    mode = "wb" if merge_type == 'hls' else "ab"
                    async with aiofiles.open(output_file, mode=mode) as outfile:
                        # Iterate through each temporary file
                        for temp_file in temp_files:
                            if not temp_file.exists():
                                continue
                            # Read and write in chunks
                            async with aiofiles.open(temp_file, mode="rb") as infile:
                                chunk_size = 512 * 1024  # 512KB
                                while True:
                                    chunk = await infile.read(chunk_size)
                                    if not chunk:
                                        break
                                    await outfile.write(chunk)
                
                await merge_with_aiofiles(temp_files, output_file)
                
                # 5. Clean up temporary files
                shutil.rmtree(temp_dir, ignore_errors=True)
                
                logger.info(f"{Color.fg('light_gray')}{track_type} "
                            f"{Color.fg('sienna')}Merger completed: {Color.fg('light_gray')}{output_file}{Color.reset()}")
                return True
            
        except Exception as e:
            logger.error(f"{track_type} Merger failed: {str(e)}")
            # Clean up temporary files
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
    
    async def download_content(self, mpd_content: MPDContent):
        if mpd_content.__class__.__name__ == 'MPDContent':
            logger.info(f"{Color.fg('light_gray')}Start downloading{Color.reset()} "
                        f"{Color.fg('tan')}MPD{Color.reset()} "
                        f"{Color.fg('light_gray')}content{Color.reset()}"
                        )
            merge_type = 'mpd'
        elif mpd_content.__class__.__name__ == 'HLSContent':
            logger.info(f"{Color.fg('light_gray')}Start downloading{Color.reset()} "
                        f"{Color.fg('orchid')}HLS{Color.reset()} "
                        f"{Color.fg('light_gray')}content{Color.reset()}"
                        )
            merge_type = 'hls'

        try:
            tasks = []
            if mpd_content.audio_track:
                tasks.append(self.download_track(mpd_content.audio_track, "audio", merge_type))
            if mpd_content.video_track:
                tasks.append(self.download_track(mpd_content.video_track, "video", merge_type))

            download_results = await asyncio.gather(*tasks)
            
            if paramstore.get('skip_merge') is not True: 
                merge_results = []
                if mpd_content.video_track and download_results[0]:
                    merge_results.append(await self._merge_track("video", merge_type))
                if mpd_content.audio_track and (
                    len(download_results) > 1 and download_results[1]
                ):
                    merge_results.append(await self._merge_track("audio", merge_type))
                return all(merge_results), merge_type
            else:
                logger.info(f"{Color.fg('light_gray')}Skip merge because --skip-merge is {Color.fg('cyan')}True{Color.reset()}")
                return False, merge_type
        finally:
            if self.session:
                await self.session.close()


async def run_dl(mpd_uri, decryption_key, json_data, raw_mpd, hls_playback_url, raw_hls):
    parser = MPDParser(raw_mpd, mpd_uri)
    mpd_content = parser.get_highest_mpd_content()
    hls_content = await HLS_Paser()._parse_media_m3u8(raw_hls)

    if not mpd_content.video_track and not mpd_content.audio_track:
        logger.error("Error: No valid audio or video tracks found in MPD.")
        return
    if mpd_content.drm_info is not None and mpd_content.drm_info.get("default_KID"):
        logger.info(
            f"Encrypted content detected (KID: {Color.fg('platinum')}{mpd_content.drm_info['default_KID']}){Color.reset()}"
        )
    if decryption_key:
        use_hls = mpd_content
    elif decryption_key is None:
        use_hls = hls_content

    await start_download_queue(decryption_key, json_data, use_hls, raw_mpd, hls_playback_url, raw_hls)
