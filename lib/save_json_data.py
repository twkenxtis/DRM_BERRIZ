import asyncio
from typing import Union, Optional

import aiofiles
import aiofiles.os as aios
import orjson
import httpx

from lib.path import Path
from static.parameter import paramstore
from unit.handle.handle_log import setup_logging


logger = setup_logging('save_json_data', 'peach')


class save_json_data:
    def __init__(self, output_dir: Union[str, Path]) -> None:
        self.output_dir: Path = Path(output_dir).parent
        self.max_retries: int = 3
        self.retry_delay: int = 2
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure the output directory exists."""
        self.output_dir.mkdirp()

    async def _write_file(self, file_path: Path, content: Union[str, bytes], mode: str = "wb") -> None:
        """Write content to a file with retry logic and atomic replacement."""
        tmp_path: Path = file_path.with_suffix(file_path.suffix + ".part")
        is_text_mode: bool = 'b' not in mode
        encoding: Optional[str] = 'utf-8' if is_text_mode else None
        for attempt in range(self.max_retries):
            try:
                async with aiofiles.open(tmp_path, mode, encoding=encoding) as f:
                    if is_text_mode and isinstance(content, bytes):
                        content = content.decode('utf-8')
                    elif not is_text_mode and isinstance(content, str):
                        content = content.encode('utf-8')
                    logger.info(f"Writing {file_path})")
                    await f.write(content)
                await aios.replace(tmp_path, file_path)
                return
            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    logger.warning(f"Failed to write to {file_path} (attempt {attempt+1}/{self.max_retries}): {e}")
                    continue
                if await aios.path.exists(tmp_path):
                    await aios.remove(tmp_path)
                raise RuntimeError(f"Failed to write to {file_path} after {self.max_retries} attempts: {e}")
    
    async def mpd_to_folder(self, raw_mpd: httpx.Response) -> None:
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
        content: str = raw_hls
        await self._write_file(self.output_dir / "manifest.m3u8", content, mode="w")

    async def play_list_to_folder(self, raw_play_list: object) -> None:
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
            if paramstore.get("mpd_video") is True:
                raise ValueError("Failed to serialize playlist to JSON") from e