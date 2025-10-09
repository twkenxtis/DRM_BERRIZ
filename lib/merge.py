import asyncio
import shutil
from typing import List

import aiofiles
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    DownloadColumn,
)

from static.color import Color
from lib.path import Path
from unit.handle.handle_log import setup_logging


logger = setup_logging('merge', 'blush')


class MERGE:
    @staticmethod
    async def binary_merge(
        output_file: Path,
        init_files: List[Path],
        segments: List[Path],
        track_type: str,
        merge_type: str
    ) -> bool:
        temp_dir: Path = output_file.parent / f"temp_merging_{track_type}"
        temp_dir.mkdirp()

        try:
            if merge_type == 'mpd' and init_files:
                async with aiofiles.open(init_files[0], 'rb') as src:
                    async with aiofiles.open(output_file, 'wb') as dst:
                        content = await src.read()
                        await dst.write(content)
                logger.info(f"{track_type} init file copied")

            total_bytes = sum(p.stat().st_size for p in segments)

            progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            )

            with progress:
                task_id = progress.add_task(
                    f"[cyan]{track_type}[/] merging",
                    total=total_bytes
                )
                chunk_size = 30
                chunks: List[List[Path]] = [
                    segments[i:i + chunk_size]
                    for i in range(0, len(segments), chunk_size)
                ]
                temp_files: List[Path] = [
                    temp_dir / f"chunk_{idx}.tmp"
                    for idx in range(len(chunks))
                ]
                tasks = [
                    MERGE.process_chunk_async(chunk, temp_file, progress, task_id)
                    for chunk, temp_file in zip(chunks, temp_files)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # 檢查是否有任務失敗
                for idx, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"{track_type} chunk {idx} failed: {result}")
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return False

            # 合併所有 chunk 到 output_file
            mode: str = "wb" if merge_type == 'hls' else "ab"
            async with aiofiles.open(output_file, mode=mode) as outfile:
                for temp_file in temp_files:
                    if not temp_file.exists():
                        continue
                    async with aiofiles.open(temp_file, mode="rb") as infile:
                        buffer_size: int = 32 * 1024 * 1024
                        while True:
                            data = await infile.read(buffer_size)
                            if not data:
                                break
                            await outfile.write(data)

            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(
                f"{Color.fg('light_gray')}{track_type} "
                f"{Color.fg('sienna')}Merger completed: "
                f"{Color.fg('light_gray')}{output_file}{Color.reset()}"
            )
            return True

        except Exception as e:
            logger.error(f"{track_type} Merger failed: {str(e)}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False

    @staticmethod
    async def process_chunk_async(
        segments: List[Path],
        temp_file: Path,
        progress: Progress,
        task_id # 傳遞 Progress 物件和 Task ID 以便更新
    ) -> bool:
        CHUNK_READ_SIZE = 2 * 1024 * 1024 
        try:
            async with aiofiles.open(temp_file, "wb") as outfile:
                for seg in segments:
                    async with aiofiles.open(seg, "rb") as infile:
                        while True:
                            content = await infile.read(CHUNK_READ_SIZE)
                            if not content:
                                break
                            await outfile.write(content)
                            progress.update(task_id, advance=len(content))
            return True
            
        except Exception as e:
            logger.error(f"Failed to process chunk {temp_file}: {e}")
            raise