import asyncio
from pathlib import Path
from typing import Union

import aiofiles
import httpx
from fake_useragent import UserAgent

from static.color import Color
from unit.handle_log import setup_logging


logger = setup_logging('class_ImageDownloader', 'sienna')


class ImageDownloader:
    """Handles downloading images from URLs."""
    def get_header():
        return {
        "User-Agent": UserAgent().chrome,
        "Cache-Control": "no-cache",
        "Accept-Encoding": "identity",
        "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,image/svg+xml,*/*",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "image",
        'Connection': 'keep-alive'
    }

    _headers = get_header()
    _timeout = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=30.0)
    _limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        
    @staticmethod
    async def _write_to_file(resp: httpx.Response, file_path: Union[str, Path]) -> None:
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        write_queue = asyncio.Queue()
        async def writer_task():
            async with aiofiles.open(file_path, "wb") as f:
                while True:
                    data = await write_queue.get()
                    if data is None:
                        break
                    await f.write(data)
                    write_queue.task_done()
        writer = asyncio.create_task(writer_task())
        try:
            async for chunk in resp.aiter_bytes(25565):
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

                        write_task = asyncio.create_task(
                            ImageDownloader._write_to_file(resp, file_path)
                        )
                        await write_task

                logger.info(f"{Color.fg('periwinkle')}{file_path}{Color.reset()}")
                return

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
