import asyncio
import os
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Union

import aiofiles

from static.color import Color
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
        temp_dir: Path = output_file.parent / f"temp_{track_type}"
        temp_dir.mkdir(exist_ok=True)
        
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
        max_workers: int = min(64, (os.cpu_count() or 1) * 4)
        chunk_size: int = 50
        chunks: List[List[Path]] = [segments[i:i + chunk_size] for i in range(0, len(segments), chunk_size)]
        temp_files: List[Path] = []
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures: Dict[Any, Union[int, str]] = {}
                
                # 1. For MPD, submit the initialization file copy task
                if merge_type == 'mpd' and init_files:
                    copy_future = pool.submit(shutil.copy2, init_files[0], output_file)
                    futures[copy_future] = "init"
                # For HLS, no init file copy is needed; output_file will be created during merge
                
                # 2. Submit all segment chunk processing tasks
                for idx, chunk in enumerate(chunks):
                    temp_file: Path = temp_dir / f"chunk_{idx}.tmp"
                    temp_files.append(temp_file)
                    fut = pool.submit(MERGE.process_chunk, chunk, temp_file)
                    futures[fut] = idx
                
                # 3. Process completed or failed tasks
                for fut in as_completed(futures):
                    tag: Union[int, str] = futures[fut]
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
                async def merge_with_aiofiles(temp_files: List[Path], output_file: Path) -> None:
                    # Open output file in write mode for HLS (since no init file) or append mode for MPD
                    mode: str = "wb" if merge_type == 'hls' else "ab"
                    async with aiofiles.open(output_file, mode=mode) as outfile:
                        # Iterate through each temporary file
                        for temp_file in temp_files:
                            if not temp_file.exists():
                                continue
                            # Read and write in chunks
                            async with aiofiles.open(temp_file, mode="rb") as infile:
                                chunk_size_local: int = 512 * 1024  # 512KB
                                while True:
                                    chunk = await infile.read(chunk_size_local)
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