import asyncio
from pathlib import Path
from typing import Union, Dict

import aiofiles
import httpx

from static.color import Color
from unit.handle_log import setup_logging
from lib.load_yaml_config import CFG


logger = setup_logging('class_ImageDownloader', 'sienna')


class ImageDownloader:
    """Handles downloading images from URLs."""

    @staticmethod
    def get_header() -> Dict[str, str]:
        return {
            "User-Agent": f"{CFG['headers']['User-Agent']}",
            "Cache-Control": "no-cache",
            "Accept-Encoding": "identity",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,image/svg+xml,*/*",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "image",
        }

    _headers: Dict[str, str] = get_header.__func__()  # type: ignore
    _timeout: httpx.Timeout = httpx.Timeout(connect=13.0, read=7.0, write=2.0, pool=10.0)
    _limits: httpx.Limits = httpx.Limits(max_keepalive_connections=10, max_connections=10)
        
    @staticmethod
    async def _write_to_file(resp: httpx.Response, file_path: Union[str, Path]) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_queue: asyncio.Queue[bytes] = asyncio.Queue()

        async def writer_task() -> None:
            async with aiofiles.open(path, "wb") as f:
                while True:
                    data = await write_queue.get()
                    if data is None:
                        break
                    await f.write(data)
                    write_queue.task_done()

        writer = asyncio.create_task(writer_task())
        try:
            async for chunk in resp.aiter_bytes(10240):
                await write_queue.put(chunk)
            await write_queue.join()
        finally:
            await write_queue.put(None)
            await writer

    @staticmethod
    async def download_image(url: str, file_path: Union[str, Path]) -> None:
        for attempt in range(1, 11):
            try:
                async with httpx.AsyncClient(
                    headers=ImageDownloader._headers,
                    timeout=ImageDownloader._timeout,
                    limits=ImageDownloader._limits,
                    http2=True,
                ) as client:
                    async with client.stream("GET", url) as resp:
                        resp.raise_for_status()

                        logger.info(f"{Color.fg('periwinkle')}{file_path}{Color.reset()}")
                        await ImageDownloader._write_to_file(resp, file_path)
                return True
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning(f"[Attempt {attempt}/10] Failed to download {url}: {e}")
                if attempt == 10:
                    logger.error(f"{url} download failed after 10 attempts")
                    raise
            except asyncio.CancelledError:
                logger.warning(f"File write cancelled for {Color.fg('light_gray')}{url}{Color.reset()}")
                try:
                    if await aiofiles.os.path.exists(file_path):
                        await aiofiles.os.remove(file_path)
                        logger.info(f"Removed partial file: {file_path}")
                except OSError as e:
                    logger.warning(f"Failed to remove file {file_path}: {e}")
                raise