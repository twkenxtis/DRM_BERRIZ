import asyncio
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiofiles
import aiohttp
from contextlib import AsyncExitStack

from lib.__init__ import container
from lib.load_yaml_config import CFG
from lib.mux.parse_hls import HLS_Paser
from lib.mux.parse_mpd import MPDContent, MPDParser, MediaTrack
from lib.processbar import ProgressBar
from lib.merge import MERGE
from lib.video_folder import start_download_queue
from static.color import Color
from static.parameter import paramstore
from unit.__init__ import USERAGENT
from unit.handle.handle_log import setup_logging


logger = setup_logging('download', 'peach')


class MediaDownloader:
    def __init__(self, media_id: str, outout_dir: str):
        self.media_id: str = media_id
        self.base_dir: Path = Path(outout_dir)
        self.session: Optional[aiohttp.ClientSession] = None

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
        return ".bin"

    async def _ensure_session(self) -> None:
        if self.session is None or self.session.closed:
            connector: aiohttp.TCPConnector = aiohttp.TCPConnector(limit_per_host=50)
            timeout: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=600)
            self.session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, headers={f"User-Agent": USERAGENT}
            )

    async def _download_file(
        self,
        url: str,
        save_path: Path,
        chunk_size: int = 384 * 1024,
        max_retries: int = 2,
        progress_callback: Optional[Callable[[int], Any]] = None
    ) -> bool:
        retries: int = 0
        save_path.parent.mkdir(parents=True, exist_ok=True)
        while retries <= max_retries:
            await self._ensure_session()
            try:
                assert self.session is not None
                async with self.session.get(url) as response:
                    if response.status not in (200, 206):
                        logger.warning(f"Request failed with status {response.status}, retrying...")
                        retries += 1
                        await asyncio.sleep(1 ** retries)
                        continue
                    try:
                        async with AsyncExitStack() as stack:
                            f = await stack.enter_async_context(aiofiles.open(save_path, "wb"))
                            async for chunk in response.content.iter_chunked(chunk_size):
                                await f.write(chunk)
                                if progress_callback:
                                    progress_callback(len(chunk))
                    except asyncio.CancelledError:
                        await self.session.close()
                        await self.force_remove_with_retry(save_path.parents[2])
                        return False
                    return True

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Download attempt {retries + 1} failed: {str(e)}")
                retries += 1
                if retries <= max_retries:
                    await asyncio.sleep(1 ** retries)
                else:
                    logger.error(f"Download failed after {max_retries} retries: {url}")
                    if save_path.exists():
                        try:
                            shutil.rmtree(save_path, ignore_errors=True)
                        except Exception as e:
                            logger.error(f"Failed to remove failed download: {e}")
                    return False
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
        return False

    async def download_track(self, track: MediaTrack, track_type: str, merge_type: str) -> bool:
        track_dir: Path = self.base_dir / track_type
        track_dir.mkdir(exist_ok=True)
        if merge_type == 'hls':
            slice_parameters = track
            file_ext: str = '.bin'
            track_id: str = track[0].split('/')[-2]
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
            init_path: Path = track_dir / f"init{file_ext}"
            if not await self._download_file(track.init_url, init_path):
                logger.error(f"{track_type} Initialization file download failed")
                return False
            logger.info(
                f"{Color.fg('light_gray')}Start downloading{Color.reset()} "
                f"{Color.bg('cyan')}{track_type}{Color.reset()} track: {Color.fg('cyan')}{track_id}{Color.reset()} "
                f"[Bitrate: {Color.fg('violet')}{track.bandwidth / 1000}k{Color.reset()}]"
                f"[Codec: {Color.fg('light_green')}{track.codecs}{Color.reset()}]"
                f"[Type: {Color.fg('light_yellow')}{track.mime_type}{Color.reset()}]"
            )
        return await self.task_and_dl(slice_parameters, track_dir, file_ext, track_type)

    async def task_and_dl(self, slice_parameters: Any, track_dir: Path, file_ext: str, track_type: str) -> bool:
        total = len(slice_parameters)
        success_count = 0

        tasks = []
        for i, url in enumerate(slice_parameters):
            seg_path = track_dir / f"seg_{i}{file_ext}"
            logger.debug(url)
            tasks.append(self._download_file(url, seg_path))

        progress_bar = ProgressBar(total, prefix=track_type)
        try:
            for i, coro in enumerate(asyncio.as_completed(tasks), 1):
                result = await coro
                success_count += int(result)
                progress_bar.update(i)
        except asyncio.CancelledError:
            await self.session.close()
            return False
        
        progress_bar.finish()

        logger.info(
            f"{Color.fg('plum')}{track_type} Split download complete: Success "
            f"{Color.fg('light_yellow')}{success_count}{Color.reset()}/{Color.fg('gray')}{total}{Color.reset()}"
        )
        return success_count == total

    async def _merge_track(self, track_type: str, merge_type: str) -> bool:
        track_dir: Path = self.base_dir / track_type
        output_file: Path = self.base_dir / f"{track_type}.{container}"
        init_files: List[Path] = list(track_dir.glob("init.*"))

        if not init_files and merge_type == 'mpd':
            logger.warning(f"Could not find {track_type} initialization file")
            return False

        segments: List[Path] = sorted(
            track_dir.glob("seg_*.*"), key=lambda x: int(x.stem.split("_")[1])
        )
        if not segments:
            logger.warning(f"No {track_type} fragment files found")
            return False

        logger.info(f"{Color.fg('light_gray')}Merge{Color.reset()} {Color.fg('light_gray')}{track_type} "
                    f"{Color.reset()}{Color.fg('light_gray')}tracks{Color.reset()}: {len(segments)} "
                    f"{Color.fg('yellow')}{Color.reset()}{Color.fg('light_gray')}segments{Color.reset()}"
                    )
        result: bool = await MERGE.binary_merge(output_file, init_files, segments, track_type, merge_type)
        return result

    async def download_content(self, mpd_content: MPDContent) -> Tuple[bool, str]:
        if mpd_content.__class__.__name__ == 'MPDContent':
            logger.info(f"{Color.fg('light_gray')}Start downloading{Color.reset()} "
                        f"{Color.fg('light_gray')}content{Color.reset()} "
                        f"{Color.fg('tan')}by MPEG-DASH{Color.reset()}"
                        )
            merge_type: str = 'mpd'
        elif mpd_content.__class__.__name__ == 'HLSContent':
            logger.info(f"{Color.fg('light_gray')}Start downloading{Color.reset()} "
                        f"{Color.fg('light_gray')}content{Color.reset()} "
                        f"{Color.fg('orchid')}by HLS{Color.reset()}"
                        )
            merge_type = 'hls'
        else:
            merge_type = 'mpd'

        try:
            tasks: List["asyncio.Task[bool]"] = []
            if mpd_content.audio_track:
                tasks.append(self.download_track(mpd_content.audio_track, "audio", merge_type))
            if mpd_content.video_track:
                tasks.append(self.download_track(mpd_content.video_track, "video", merge_type))

            download_results: List[bool] = await asyncio.gather(*tasks)

            if paramstore.get('skip_merge') is not True:
                merge_results: List[bool] = []
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

    async def force_remove_with_retry(self, path: Path) -> bool:
        max_retries: int = 20
        delay: float = 0.05
        for attempt in range(1, max_retries + 1):
            try:
                if path.exists():
                    shutil.rmtree(path, ignore_errors=False)
                    logger.info(f"{Color.fg('yellow_ochre')}Successfully removed{Color.fg('denim')} {path}{Color.reset()}")
                return True
            except Exception:
                await asyncio.sleep(delay)
        logger.error(f"Failed to remove after {max_retries} attempts: {path}")
        return False

async def run_dl(mpd_uri: str, decryption_key: Optional[str], json_data: Dict[str, Any], raw_mpd: str, hls_playback_url: str, raw_hls: str) -> None:
    parser: MPDParser = MPDParser(raw_mpd, mpd_uri)
    mpd_content: MPDContent = parser.get_highest_mpd_content()
    hls_content: Any = await HLS_Paser()._parse_media_m3u8(raw_hls)

    if not mpd_content.video_track and not mpd_content.audio_track:
        logger.error("Error: No valid audio or video tracks found in MPD.")
        return
    if mpd_content.drm_info is not None and mpd_content.drm_info.get("default_KID"):
        logger.info(
            f"Encrypted content detected (KID: {Color.fg('azure')}{mpd_content.drm_info['default_KID']}){Color.reset()}"
        )
    try:
        hls_bool = CFG['HLS or MPEG-SASH']['HLS']
    except AttributeError:
        hls_bool = False
    if hls_bool is True:
        use_hls: Any = hls_content
    elif hls_content is False:
        use_hls: Any = mpd_content
    elif decryption_key:
        use_hls: Any = mpd_content
    elif decryption_key is None and paramstore.get('hls_only_dl') is False:
        use_hls: Any = mpd_content
    elif paramstore.get('hls_only_dl') is True:
        use_hls: Any = hls_content

    await start_download_queue(decryption_key, json_data, use_hls, raw_mpd, hls_playback_url, raw_hls)