import asyncio
import base64
import binascii
import os
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import aiofiles
import aiohttp
import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from static.color import Color
from unit.handle_log import setup_logging


logger = setup_logging('hls_download', 'fern')


class HLSDownloader:
    def __init__(
        self,
        m3u8_link: str,
        save_name: str,
        save_dir: str,
        max_retries: int = 4,
        request_delay: float = 0,
        info_tuple: Optional[Tuple[str, str, str, str, str, str, str, str]] = None,
    ):
        self.m3u8_link = m3u8_link
        self.save_name = save_name
        self.save_dir = save_dir
        self.video_dir = os.path.join(save_dir, "video_segments")
        self.audio_dir = os.path.join(save_dir, "audio_segments")
        self.session = requests.Session()
        self.session_headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148; iPhone18.3.2; iPhone14,8",
            "Referer": "https://berriz.in/",
            "Origin": "https://berriz.in",
        }
        self.session_headers = {}
        self.initial_media_sequence = 0
        self.current_media_sequence = 0
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.output_path = os.path.join(self.save_dir, self.save_name)
        self.downloaded_segments: set[str] = set()
        self.segment_counter = 0
        self.info_tuple = info_tuple
        self.video_is_encrypted = False
        self.video_encryption_key_uri: Optional[str] = None
        self.video_encryption_key: Optional[bytes] = None
        self.audio_is_encrypted = False
        self.audio_encryption_key_uri: Optional[str] = None
        self.audio_encryption_key: Optional[bytes] = None
        self._logged_key_iv = False
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(self.video_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)

    async def _get_async_response(
        self, url: str, session: aiohttp.ClientSession
    ) -> bytes:
        for attempt in range(self.max_retries):
            try:
                async with session.get(url, timeout=3) as response:
                    response.raise_for_status()
                    return await response.read()
            except aiohttp.ClientError as e:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"{Color.fg('yellow')}Async HTTP request failed after {Color.reset()}{self.max_retries} attempts: {Color.fg('light_gray')}{url}{Color.reset()} - {str(e)}"
                    )
                logger.warning(
                    f"{Color.fg('yellow')}Async HTTP request failed (attempt {Color.reset()}{attempt + 1}/{self.max_retries}): - {str(e)}"
                )
                await asyncio.sleep(0.3 * (1.5**attempt))
            except Exception as e:
                raise RuntimeError(f"Unexpected error: {url} - {str(e)}")

    def _get_http_response(self, url: str) -> bytes:
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=13)
                response.raise_for_status()
                return response.content
            except requests.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"{Color.fg('yellow')}Async HTTP request failed after {Color.reset()}{self.max_retries} attempts: {Color.fg('light_gray')}{url}{Color.reset()} - {str(e)}"
                    )
                logger.warning(
                    f"{Color.fg('yellow')}Async HTTP request failed (attempt {Color.reset()}{attempt + 1}/{self.max_retries}): - {str(e)}"
                )
                time.sleep(1 * (attempt + 1))
            except Exception as e:
                raise RuntimeError(f"Unexpected error: {url} - {str(e)}")
            finally:
                time.sleep(self.request_delay)

    def _get_m3u8_content(self, url: str) -> str:
        content = self._get_http_response(url)
        return content.decode("utf-8")

    async def _download_encryption_key_async(
        self, session: aiohttp.ClientSession, prefix: str
    ) -> bool:
        encryption_key_uri = getattr(self, f"{prefix}_encryption_key_uri", None)
        encryption_key_attr = f"{prefix}_encryption_key"

        if not encryption_key_uri:
            logger.error(
                f"{Color.fg('gold')}No key URI provided for {prefix}{Color.reset()}"
            )
            return False

        if getattr(self, encryption_key_attr, None):
            logger.debug(f"{prefix} key already downloaded")
            return True

        logger.info(
            f"{Color.fg('light_gray')}Downloading{Color.reset()} {Color.fg('ruby')}{prefix}{Color.reset()} "
            f"{Color.fg('light_gray')}encryption key:{Color.reset()} "
            f"{Color.fg('bright_cyan')}{encryption_key_uri}{Color.reset()}"
        )

        try:
            response_content = await self._get_async_response(
                encryption_key_uri, session
            )
            if len(response_content) == 16:
                setattr(self, encryption_key_attr, response_content)
                logger.info(
                    f"{Color.fg('tomato')}{prefix}{Color.reset()} {Color.fg('light_gray')}key downloaded successfully{Color.reset()}"
                )
                return True
            else:
                logger.error(
                    f"{prefix} key length incorrect ({len(response_content)} bytes), expected 16 bytes"
                )
                return False
        except RuntimeError as e:
            logger.error(f"Failed to download {prefix} key: {e}")
            return False

    async def _download_segment(
        self,
        ts_url: str,
        seq_num: int,
        save_path: str,
        session: aiohttp.ClientSession,
        prefix: str,
    ) -> bool:
        """Main method to orchestrate segment downloading."""
        if await self._check_segment_already_downloaded(ts_url):
            return True

        return await self._attempt_segment_download(
            ts_url, seq_num, save_path, session, prefix
        )

    async def _check_segment_already_downloaded(self, ts_url: str) -> bool:
        """Check if the segment has already been downloaded."""
        return ts_url in self.downloaded_segments

    async def _attempt_segment_download(
        self,
        ts_url: str,
        seq_num: int,
        save_path: str,
        session: aiohttp.ClientSession,
        prefix: str,
    ) -> bool:
        """Manage retry logic for downloading a segment."""
        with ThreadPoolExecutor(max_workers=4) as executor:
            for attempt in range(self.max_retries):
                if await self._try_download_segment(
                    ts_url, seq_num, save_path, session, prefix, executor
                ):
                    self.downloaded_segments.add(ts_url)
                    logger.info(
                        f"{Color.fg('light_gray')}Segment {seq_num} downloaded and saved to{Color.reset()} "
                        f"{Color.fg('gray')}{save_path}{Color.reset()}"
                    )
                    return True
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.3 * (1.5**attempt))
                else:
                    logger.error(
                        f"Download failed after {self.max_retries} attempts: {ts_url}"
                    )
                    return False
        return False

    async def _try_download_segment(
        self,
        ts_url: str,
        seq_num: int,
        save_path: str,
        session: aiohttp.ClientSession,
        prefix: str,
        executor: ThreadPoolExecutor,
    ) -> bool:
        """Attempt a single download of the segment."""
        try:
            data = await self._get_async_response(ts_url, session)
            data = await self._process_segment_data(data, seq_num, prefix, executor)
            await self._save_segment_data(data, save_path)
            return True
        except Exception as e:
            logger.error(f"Download attempt failed for {ts_url}: {str(e)}")
            return False

    async def _process_segment_data(
        self,
        data: bytes,
        seq_num: int,
        prefix: str,
        executor: ThreadPoolExecutor,
    ) -> bytes:
        """Process segment data, including decryption if needed."""
        if getattr(self, f"{prefix}_is_encrypted"):
            iv_bytes = self._calculate_iv(seq_num)
            encryption_key = getattr(self, f"{prefix}_encryption_key", None)
            if not encryption_key:
                raise RuntimeError(f"No encryption key for {prefix}")

            await self._log_key_iv(encryption_key, iv_bytes)

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor, lambda: self._decrypt_data(data, encryption_key, iv_bytes)
            )
        return data

    async def _log_key_iv(self, encryption_key: bytes, iv_bytes: bytes) -> None:
        """Log encryption key and IV in various formats."""
        if not self._logged_key_iv:
            logger.info(
                f"{Color.fg('light_gray')}Key (HEX): {Color.fg('orchid')}{binascii.hexlify(encryption_key).decode('utf-8')}{Color.reset()}"
            )
            logger.info(
                f"{Color.fg('light_gray')}IV (HEX): {Color.fg('lavender')}{binascii.hexlify(iv_bytes).decode('utf-8')}{Color.reset()}"
            )
            logger.info(
                f"{Color.fg('light_gray')}Key (HEX): {Color.fg('orchid')}{base64.b64encode(encryption_key).decode('utf-8')}{Color.reset()}"
            )
            logger.info(
                f"{Color.fg('light_gray')}IV (HEX): {Color.fg('lavender')}{base64.b64encode(iv_bytes).decode('utf-8')}{Color.reset()}"
            )
            self._logged_key_iv = True

    async def _save_segment_data(self, data: bytes, save_path: str) -> None:
        """Save segment data to file."""
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(data)

    async def _get_async_response(
        self, ts_url: str, session: aiohttp.ClientSession
    ) -> bytes:
        """Fetch data from the given URL using the session."""
        async with session.get(ts_url) as response:
            response.raise_for_status()
            return await response.read()

    def _calculate_iv(self, media_sequence: int) -> bytes:
        hex_msn = format(media_sequence, "x")
        iv_hex_string = hex_msn.zfill(32)
        return binascii.unhexlify(iv_hex_string)

    def _decrypt_data(self, encrypted_data: bytes, iv_bytes: bytes) -> bytes:
        if not self.encryption_key:
            raise RuntimeError("Decryption key not provided or downloaded")
        if len(self.encryption_key) != 16:
            raise ValueError(
                f"Key length incorrect ({len(self.encryption_key)} bytes), expected 16 bytes"
            )
        if len(iv_bytes) != 16:
            raise ValueError(
                f"IV length incorrect ({len(iv_bytes)} bytes), expected 16 bytes"
            )

        try:
            cipher = Cipher(
                algorithms.AES(self.encryption_key),
                modes.CBC(iv_bytes),
                backend=default_backend(),
            )
            decryptor = cipher.decryptor()
            decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()
            return decrypted_data
        except Exception as e:
            raise RuntimeError(f"Decryption failed: {str(e)}")

    async def download_and_process_segments(
        self, m3u8_url: str, segment_dir: str, prefix: str
    ) -> Tuple[int, int, float]:
        """Main method to orchestrate segment downloading and processing."""
        os.makedirs(segment_dir, exist_ok=True)
        async with aiohttp.ClientSession(headers=self.session_headers) as session:
            try:
                if not await self._handle_encryption_key(session, prefix):
                    return 0, 0, 0.0

                ts_segments, audio_url, = (
                    await self._parse_m3u8(m3u8_url, prefix)
                )
                if not ts_segments:
                    return 0, 0

                return await self._process_segment_batch(
                    ts_segments, segment_dir, prefix, session
                )
            except asyncio.CancelledError:
                logger.info(f"Download cancelled for {prefix}")
                return 0, 0, 0.0
            finally:
                await session.close()

    async def _handle_encryption_key(
        self, session: aiohttp.ClientSession, prefix: str
    ) -> bool:
        """Handle downloading of encryption key if needed."""
        if getattr(self, f"{prefix}_is_encrypted", False):
            if not await self._download_encryption_key_async(session, prefix):
                logger.error(f"Failed to download {prefix} encryption key")
                return False
        return True

    async def _process_segment_batch(
        self,
        ts_segments: List,
        segment_dir: str,
        prefix: str,
        session: aiohttp.ClientSession,
    ) -> Tuple[int, int, float]:
        """Process a batch of segments by creating and executing download tasks."""
        tasks, save_paths = await self._create_download_tasks(
            ts_segments, segment_dir, prefix, session
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return self._evaluate_download_results(ts_segments, results, save_paths, prefix)

    async def _create_download_tasks(
        self,
        ts_segments: List,
        segment_dir: str,
        prefix: str,
        session: aiohttp.ClientSession,
    ) -> Tuple[List, List[str]]:
        """Create download tasks for segments that haven't been downloaded."""
        tasks = []
        save_paths = []
        for ts_url, seq_num, _ in ts_segments:
            if ts_url in self.downloaded_segments:
                logger.debug(f"Skipping already downloaded {prefix} segment: {ts_url}")
                continue
            save_path = os.path.join(
                segment_dir, f"{prefix}_{self.segment_counter}.bin"
            )
            self.segment_counter += 1
            save_paths.append(save_path)
            tasks.append(
                self._download_segment(ts_url, seq_num, save_path, session, prefix)
            )
        return tasks, save_paths

    def _evaluate_download_results(
        self, ts_segments: List, results: List, save_paths: List[str], prefix: str
    ) -> Tuple[int, int, float]:
        """Evaluate download results and update success/failure counts."""
        success_count = 0
        fail_count = 0
        for idx, (ts_url, _, _), result, save_path in zip(
            range(len(results)), ts_segments, results, save_paths
        ):
            if isinstance(result, Exception):
                logger.error(f"Segment {ts_url} failed: {str(result)}")
                fail_count += 1
            elif result:
                success_count += 1
                self.downloaded_segments.add(ts_url)
            else:
                fail_count += 1

        logger.info(
            f"{Color.fg('tomato')}{prefix} download completed:{Color.reset()} "
            f"{Color.fg('lemon')}{success_count}{Color.reset()}"
            f"{Color.fg('light_gray')} successful | {Color.reset()} "
            f"{Color.fg('ivory')}{fail_count}{Color.reset()} {Color.fg('light_gray')}failed{Color.reset()}"
        )
        return success_count, fail_count, ts_segments[0][2] if ts_segments else 0.0

    async def _parse_media_m3u8(
        self, m3u8_url: str, prefix: str = "video"
    ) -> Tuple[List[Tuple[str, int, float]], Optional[str], bool, float]:
        """Main method to parse M3U8 playlist and orchestrate processing."""
        content = self._get_m3u8_content(m3u8_url)
        lines = self._preprocess_content(content)
        self._set_default_encryption_attributes(prefix)

        if self._check_master_playlist(lines):
            return await self._process_master_playlist(lines, m3u8_url, prefix)
        return await self._process_media_playlist(lines, m3u8_url, prefix)

    def _preprocess_content(self, content: str) -> List[str]:
        """Split and clean M3U8 content into a list of non-empty lines."""
        return [line.strip() for line in content.splitlines() if line.strip()]

    def _set_default_encryption_attributes(self, prefix: str) -> None:
        """Set default encryption attributes for the given prefix."""
        setattr(self, f"{prefix}_is_encrypted", False)
        setattr(self, f"{prefix}_encryption_key_uri", None)
        setattr(self, f"{prefix}_encryption_key", None)

    def _check_master_playlist(self, lines: List[str]) -> bool:
        """Determine if the playlist is a master playlist."""
        return any(line.startswith("#EXT-X-STREAM-INF:") for line in lines)

    async def _process_master_playlist(
        self, lines: List[str], m3u8_url: str, prefix: str
    ) -> Tuple[List[Tuple[str, int, float]], Optional[str], bool, float]:
        """Select and parse the best resolution sub-playlist from a master playlist."""
        best_height, best_link, best_info = -1, None, ""
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF:"):
                height = self._extract_resolution_height(line)
                if (
                    height > best_height
                    and i + 1 < len(lines)
                    and not lines[i + 1].startswith("#")
                ):
                    best_height = height
                    best_link = urljoin(m3u8_url, lines[i + 1])
                    best_info = line

        if best_link:
            logger.info(
                f"{Color.fg('light_gray')}{prefix}:{Color.reset()} "
                f"{Color.fg('beige')}{best_info}{Color.reset()}\n"
                f"{'-' * 170}\n"
                f"{Color.fg('dark_gray')}{best_link}{Color.reset()}\n"
                f"{'-' * 170}"
            )
            if prefix == "video":
                self.m3u8_link = best_link
            return await self._parse_media_m3u8(best_link, prefix)

        logger.error(f"No valid sub-playlist links found for {prefix}")
        return [], None, False, 0.0

    def _extract_resolution_height(self, line: str) -> int:
        """Extract the resolution height from a STREAM-INF line."""
        resolution_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
        return int(resolution_match.group(2)) if resolution_match else -1

    def _extract_audio_url(self, line: str, m3u8_url: str) -> Optional[str]:
        """Extract audio track URL from an EXT-X-MEDIA line."""
        uri_match = re.search(r'URI="([^"]+)"', line)
        if uri_match:
            audio_url = urljoin(m3u8_url, uri_match.group(1))
            logger.info(f"Found audio track: {audio_url}")
            return audio_url
        return None

    def _handle_encryption(self, line: str, m3u8_url: str, prefix: str) -> None:
        """Process encryption key information from an EXT-X-KEY line."""
        if "METHOD=AES-128" in line:
            setattr(self, f"{prefix}_is_encrypted", True)
            uri_match = re.search(r'URI="([^"]+)"', line)
            if uri_match:
                key_uri = urljoin(m3u8_url, uri_match.group(1))
                setattr(self, f"{prefix}_encryption_key_uri", key_uri)
                logger.info(
                    f"{Color.fg('ruby')}{prefix}{Color.reset()} {Color.fg('light_gray')}encryption key URI: {Color.reset()} "
                    f"{Color.fg('bright_cyan')}{key_uri}{Color.reset()}"
                )
        else:
            logger.warning(f"Unsupported {prefix} encryption method: {line}")

    def _update_media_sequence(self, line: str) -> None:
        """Update media sequence numbers from an EXT-X-MEDIA-SEQUENCE line."""
        self.initial_media_sequence = int(line.split(":")[1])
        if self.current_media_sequence == 0:
            self.current_media_sequence = self.initial_media_sequence
        logger.debug(f"Media Sequence Number: {self.initial_media_sequence}")

    def _extract_segment_duration(self, line: str) -> float:
        """Extract segment duration from an EXTINF line."""
        duration_match = re.search(r"^#EXTINF:([\d.]+)", line)
        return float(duration_match.group(1)) if duration_match else 0.0

    def _process_segment(self, line: str, m3u8_url: str) -> Tuple[str, int]:
        """Process a segment line to extract URL and sequence number."""
        segment_url = urljoin(m3u8_url, line)
        match = re.search(r"-seq=(\d+)\.(ts|aac|mp4|m4a|m4v)", segment_url)
        seq_num = int(match.group(1)) if match else self.current_media_sequence
        return segment_url, seq_num

    async def _download_loop(self) -> Tuple[int, int, Optional[str], float]:
        """Main download loop to process video and audio segments."""
        video_success_total = 0
        audio_success_total = 0
        audio_m3u8 = None

        for i in segments:
            try:
                segments, audio_m3u8= (
                    await self._parse_playlist(self.m3u8_link)
                )
                video_success, audio_success = await self._process_downloads(
                    segments, audio_m3u8
                )
                
                video_success_total += video_success
                audio_success_total += audio_success

            except asyncio.CancelledError:
                logger.info("Download loop cancelled")
                return (
                    video_success_total,
                    audio_success_total,
                    audio_m3u8,
                )

        return (
            video_success_total,
            audio_success_total,
            audio_m3u8,
        )

    async def _parse_playlist(
        self, m3u8_url: str
    ) -> Tuple[List, Optional[str], bool, float]:
        """Parse the M3U8 playlist to extract segments and metadata."""
        return await self._parse_media_m3u8(m3u8_url, "video")

    def _check_stream_end(self, is_ended: bool) -> bool:
        """Check if the stream has ended based on playlist metadata."""
        return is_ended

    async def _process_downloads(
        self, segments: List, audio_m3u8: Optional[str]
    ) -> Tuple[int, int]:
        """Process video and audio segment downloads."""
        video_success, video_fail, _ = await self.download_and_process_segments(
            self.m3u8_link, self.video_dir, "video"
        )

        audio_success, audio_fail = 0, 0
        if audio_m3u8:
            audio_success, audio_fail, _ = await self.download_and_process_segments(
                audio_m3u8, self.audio_dir, "audio"
            )
        return video_success, audio_success

    def _merge_av_streams(self, video_files: List[str], audio_files: List[str]) -> bool:
        temp_video = os.path.join(self.video_dir, "temp_video.bin")
        temp_audio = os.path.join(self.audio_dir, "temp_audio.bin")

        if not self._merge_single_stream(video_files, self.video_dir, temp_video):
            return False

        if audio_files and not self._merge_single_stream(
            audio_files, self.audio_dir, temp_audio
        ):
            if os.path.exists(temp_video):
                os.remove(temp_video)
            return False

        try:
            cmd = ["ffmpeg", "-y", "-i", temp_video]
            if audio_files:
                cmd += ["-i", temp_audio]
            cmd += [
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-movflags",
                "faststart",
                self.output_path,
            ]
            subprocess.run(cmd, check=True, stderr=subprocess.PIPE, shell=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Audio-video merge failed: {e.stderr.decode('utf-8')}")
            return False
        finally:
            for f in [temp_video, temp_audio]:
                if os.path.exists(f):
                    os.remove(f)

    def _merge_single_stream(
        self, file_list: List[str], dir_path: str, output_path: str
    ) -> bool:
        if not file_list:
            logger.error(f"No segments available for merging: {dir_path}")
            return False

        list_path = self._create_concat_list(dir_path, file_list)

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    list_path,
                    "-c",
                    "copy",
                    "-bsf:a",
                    "aac_adtstoasc",
                    output_path,
                ],
                check=True,
                stderr=subprocess.PIPE,
                shell=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg merge failed: {e.stderr.decode('utf-8')}")
            return False
        finally:
            if os.path.exists(list_path):
                os.remove(list_path)

    def _cleanup_segments(self):
        for dir_path in [self.video_dir, self.audio_dir]:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path, ignore_errors=True)

    def _validate_video_segments(self, video_success_total: int) -> None:
        """驗證至少有一個視訊片段下載成功"""
        if video_success_total == 0:
            raise RuntimeError("No video segments downloaded successfully")
        logger.info(f"{Color.fg('fern')}Merging files...{Color.reset()}")

    def _get_stream_files(
        self, audio_m3u8: Optional[str]
    ) -> Tuple[List[str], List[str]]:
        """獲取視訊和音訊文件列表"""
        video_files = sorted(
            f for f in os.listdir(self.video_dir) if f.endswith(".bin")
        )

        audio_files = []
        if audio_m3u8:
            audio_files = sorted(
                f for f in os.listdir(self.audio_dir) if f.endswith(".bin")
            )

        return video_files, audio_files

    def _process_stream_merging(
        self,
        video_files: List[str],
        audio_files: List[str],
        audio_success_total: int,
    ) -> bool:
        """根據條件處理不同合併情境"""
        if audio_files and audio_success_total > 0:
            return self._merge_av_streams(video_files, audio_files)
        else:
            return self._merge_single_stream(
                video_files, self.video_dir, self.output_path
            )

    def _verify_output_file(self) -> None:
        """驗證最終輸出文件是否生成"""
        if not os.path.exists(self.output_path):
            raise RuntimeError("Final output file not generated")

    def merge_streams(
        self,
        video_success_total: int,
        audio_success_total: int,
        audio_m3u8: Optional[str],
    ) -> bool:
        """合併視訊和音訊流的主要入口函數"""
        self._validate_video_segments(video_success_total)

        video_files, audio_files = self._get_stream_files(audio_m3u8)
        success = self._process_stream_merging(
            video_files, audio_files, audio_success_total
        )

        self._verify_output_file()
        return success

    async def rename_process(self) -> bool:
        self._cleanup_segments()
        logger.info(f"{Color.fg('sea_green')}Cleanup segments completed{Color.reset()}")
        try:
            #new_path = re_name_file(self.output_path)
            new_path = self.output_path
            logger.info(
                f"{Color.fg('light_gray')}Processing completed! File saved to: {Color.reset()}"
                f"{Color.fg('indigo')}{new_path}{Color.reset()}"
            )

            (
                thumbnailUrl,
                Live_link_url,
                discord_time,
                capital_community_name,
                title,
                author_icon_url,
                source_artist,
                tpeTime,
                mediaId,
            ) = self.info_tuple
            return True
        except AttributeError as e:
            logger.error(f"External method not implemented: {e}")
            return False

    def _handle_interrupt(self) -> bool:
        logger.info("Download interrupted by user, merging downloaded segments...")
        video_files = sorted(
            [f for f in os.listdir(self.video_dir) if f.endswith(".bin")]
        )
        audio_files = (
            sorted([f for f in os.listdir(self.audio_dir) if f.endswith(".bin")])
            if os.path.exists(self.audio_dir)
            else []
        )

        success = False
        if video_files:
            if audio_files:
                success = self._merge_av_streams(video_files, audio_files)
            else:
                success = self._merge_single_stream(
                    video_files, self.video_dir, self.output_path
                )

        if success and os.path.exists(self.output_path):
            logger.info(f"Partial stream content saved: {self.output_path}")
            self._cleanup_segments()

        return success
    
    def _create_concat_list(self, dir_path: str, file_list: List[str]) -> str:
        list_path = os.path.join(dir_path, "file_list.txt")

        def natural_keys(text):
            return [int(c) if c.isdigit() else c for c in re.split(r"(\d+)", text)]

        file_list.sort(key=natural_keys)

        with open(list_path, "w", encoding="utf-8") as f:
            for filename in file_list:
                full_path = os.path.abspath(os.path.join(dir_path, filename))
                ffmpeg_path = full_path.replace("\\", "/")
                f.write(f"file '{ffmpeg_path}'\n")

        return list_path
    
    def run(self) -> bool:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            (
                video_success_total,
                audio_success_total,
                audio_m3u8,
                avg_segment_duration,
            ) = loop.run_until_complete(self._download_loop())
            success = self.merge_streams(
                video_success_total, audio_success_total, audio_m3u8
            )
            if success and os.path.exists(self.output_path):
                return asyncio.create_task(self.rename_process())
            return False
        except KeyboardInterrupt:
            logger.info("Download interrupted by KeyboardInterrupt")
            return self._handle_interrupt()
        finally:
            loop.close()