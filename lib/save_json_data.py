import asyncio
from pathlib import Path
from typing import Any, Union, Dict, Optional

import aiofiles
import aiofiles.os as aios
import orjson

from unit.handle.handle_log import setup_logging


logger = setup_logging('save_json_data', 'peach')


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
