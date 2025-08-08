import asyncio
from datetime import datetime
import logging
from pathlib import Path
import shutil

import aiohttp
from tqdm.asyncio import tqdm

from lib.ffmpeg.parse_mpd import MPDParser, MediaTrack, MPDContent
from lib.tools.reName import SUCCESS


USER_AGENT = "Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36"


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class MediaDownloader:
    def __init__(self, media_id: str):
        self.media_id = media_id
        self.base_dir = self._create_output_dir()
        self.session = None

    def _create_output_dir(self) -> Path:
        base_dir = Path("downloads")
        folder_name = f"{self.media_id} {datetime.now().strftime('%y%m%d_%H%M%S')}"
        output_dir = base_dir / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

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
            connector = aiohttp.TCPConnector(limit_per_host=25)
            timeout = aiohttp.ClientTimeout(total=1200)
            self.session = aiohttp.ClientSession(
                connector=connector, timeout=timeout, headers={"User-Agent": USER_AGENT}
            )

    async def _download_file(self, url: str, save_path: Path, desc: str = "Downloading") -> bool:
        await self._ensure_session()
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    total_size = int(response.headers.get("content-length", 0))
                    progress_bar = tqdm(
                        total=total_size,
                        unit="B",
                        unit_scale=True,
                        desc=desc,
                        leave=False
                    )
                    with open(save_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(10240 * 10240):
                            f.write(chunk)
                            progress_bar.update(len(chunk))
                    progress_bar.close()
                    return True
                return False
        except Exception as e:
            logging.error(f"Download failed {url}: {str(e)}")
            return False

    async def download_track(self, track: MediaTrack, track_type: str, progress_bar: tqdm) -> bool:
        track_dir = self.base_dir / track_type
        track_dir.mkdir(exist_ok=True)

        logging.info(
            f"Start downloading {track_type} track: {track.id} [Bitrate: {track.bandwidth}]"
        )

        # Get appropriate extension for files
        file_ext = self._get_file_extension(track.mime_type)

        # Download initialization segment
        init_path = track_dir / f"init{file_ext}"
        if not await self._download_file(track.init_url, init_path, desc=f"{track_type} init"):
            logging.error(f"{track_type} Initialization file download failed")
            return False

        # Download media segments
        tasks = []
        for i, url in enumerate(track.segment_urls):
            seg_path = track_dir / f"seg_{i:05d}{file_ext}"
            tasks.append(self._download_file(url, seg_path, desc=f"{track_type} seg {i:05d}"))

        results = await asyncio.gather(*tasks)
        for _ in results:
            progress_bar.update(1)  # Update the track-level progress bar

        success_count = sum(results)

        logging.info(
            f"{track_type} Split download complete: Success {success_count}/{len(results)}"
        )
        return success_count == len(results)

    def _merge_track(self, track_type: str) -> bool:
        track_dir = self.base_dir / track_type
        output_file = self.base_dir / f"{track_type}.ts"

        init_files = list(track_dir.glob("init.*"))
        if not init_files:
            logging.warning(f"Could not find {track_type} initialization file")
            return False

        segments = sorted(
            track_dir.glob("seg_*.*"), key=lambda x: int(x.stem.split("_")[1])
        )
        if not segments:
            logging.warning(f"No {track_type} fragment files found")
            return False

        logging.info(f"Merge {track_type} tracks: {len(segments)} segments")

        try:
            with open(output_file, "wb") as outfile:
                with open(init_files[0], "rb") as infile:
                    shutil.copyfileobj(infile, outfile)
                for seg in segments:
                    with open(seg, "rb") as infile:
                        shutil.copyfileobj(infile, outfile)

            logging.info(f"{track_type} Merger completed: {output_file}")
            return True
        except Exception as e:
            logging.error(f"{track_type} Merger failed: {str(e)}")
            return False

    async def download_content(self, mpd_content: MPDContent):
        try:
            tasks = []
            progress_bars = []
            
            # Create progress bars for each track
            if mpd_content.video_track:
                video_pbar = tqdm(
                    total=len(mpd_content.video_track.segment_urls) + 1,  # +1 for init file
                    desc="Video track",
                    unit="segment",
                    position=0
                )
                tasks.append(self.download_track(mpd_content.video_track, "video", video_pbar))
                progress_bars.append(video_pbar)
            
            if mpd_content.audio_track:
                audio_pbar = tqdm(
                    total=len(mpd_content.audio_track.segment_urls) + 1,  # +1 for init file
                    desc="Audio track",
                    unit="segment",
                    position=1
                )
                tasks.append(self.download_track(mpd_content.audio_track, "audio", audio_pbar))
                progress_bars.append(audio_pbar)

            # Run downloads concurrently
            download_results = await asyncio.gather(*tasks)

            # Close all progress bars
            for pbar in progress_bars:
                pbar.close()

            # Merge tracks if downloads were successful
            merge_results = []
            if mpd_content.video_track and download_results[0]:
                merge_results.append(self._merge_track("video"))
            if mpd_content.audio_track and (
                len(download_results) > 1 and download_results[1]
            ):
                merge_results.append(self._merge_track("audio"))

            return all(merge_results)
        finally:
            if self.session:
                await self.session.close()





async def run_dl(mpd_uri, decryption_key, json_data):
    parser = MPDParser(mpd_uri)
    mpd_content = parser.get_highest_quality_content()

    if not mpd_content.video_track and not mpd_content.audio_track:
        logging.error("Error: No valid audio or video tracks found in MPD.")
        return

    if mpd_content.drm_info and mpd_content.drm_info.get("default_KID"):
        logging.info(
            f"\nEncrypted content detected (KID: {mpd_content.drm_info['default_KID']})"
        )

    foldername = json_data.get("media", {}).get("id", "")
    downloader = MediaDownloader(f"{foldername}")
    success = await downloader.download_content(mpd_content)
    s = SUCCESS(downloader, json_data)
    s.when_success(success, decryption_key)
