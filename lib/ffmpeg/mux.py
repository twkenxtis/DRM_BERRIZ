import subprocess
from pathlib import Path

from typing import Optional, List

from static.color import Color
from unit.handle_log import setup_logging
from unit.parameter import paramstore
import asyncio


logger = setup_logging('mux', 'lavender')


class FFmpegMuxer:
    def __init__(self, base_dir: Path, decryption_key: Optional[List] = None):
        self.base_dir = base_dir
        self.decryption_key = decryption_key

    async def _prepare_track(self, track_type: str) -> Optional[Path]:
        """Handle decryption if needed and return final file path"""
        input_file = self.base_dir / f"{track_type}.ts"

        if not input_file.exists():
            return None

        if self.decryption_key:
            logger.info(
                f"{Color.fg('blue')}Detected{Color.reset()} {Color.fg('cyan')}{track_type} {Color.reset()}{Color.fg('blue')}"
                f"{Color.reset()}{Color.fg('blue')}decrypting...{Color.reset()}"
            )
            decryption_key = await self.process_decryption_key()
            decrypted_file = self.base_dir / f"{track_type}_decrypted.ts"
            if await self._decrypt_file(input_file, decrypted_file, decryption_key):
                return decrypted_file
            return None
        # No encryption, use original file
        return input_file

    async def process_decryption_key(self):
        if type(self.decryption_key) is list:
            key = ' '.join([str(sublist).replace('[', '').replace(']', '') for sublist in self.decryption_key])
            return key
        elif type(self.decryption_key) is str:
            return self.decryption_key

    async def _decrypt_file(
            self,
            input_path: Path,
            output_path: Path,
            key: str,
        ) -> bool:
            current_dir = Path(__file__).parent
            parent_tools_dir = current_dir.parent / "tools"
            mp4decrypt_path = parent_tools_dir / "mp4decrypt.exe"
            
            if not mp4decrypt_path.exists():
                logger.error(f"mp4decrypt.exe not found at: {mp4decrypt_path}")
                return False
            
            try:
                # 分割 key 字串並為每個 key 添加 --key 參數
                key_parts = key.split()
                key_args = []
                for k in key_parts:
                    key_args.extend(["--key", k])
                
                # 建立完整的命令
                command = [str(mp4decrypt_path)] + key_args + [str(input_path), str(output_path)]
                
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return True
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Decryption failed for {input_path}: {e.stderr or e.stdout}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error decrypting {input_path}: {str(e)}")
                return False

    async def mux_to_mp4(self, merge_type: str, tempfile_name) -> bool:
        # Prepare video and audio tracks
        async with asyncio.TaskGroup() as tg:
            video_task = tg.create_task(self._prepare_track("video"))
            audio_task = tg.create_task(self._prepare_track("audio"))

        video_file = video_task.result()
        audio_file = audio_task.result()
        if merge_type == 'mpd' and (not video_file or not audio_file) and paramstore.get('skip_merge') is not True:
            logger.error(
                "Error: Valid video and audio must exist simultaneously for multiplexing."
            )
            return False
        elif merge_type == 'hls' and not video_file and paramstore.get('skip_merge') is not True:
            logger.error(
                "Error: Valid video and audio must exist simultaneously for multiplexing."
            )
            return False
        elif paramstore.get('skip_merge') is True:
            return False
        logger.info(F"{Color.fg('light_gray')}Start using FFmpeg to mux video and audio...{Color.reset()}")

        # Standard FFmpeg command without modification
        temp_file_path = Path(self.base_dir / tempfile_name)
        cmd = await self.build_ffmpeg_command(video_file, audio_file, temp_file_path)
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg multiplexing failed:\n{result.stderr}")
                return False
            logger.info(f"{Color.fg('gray')}Mixed flow completed: {temp_file_path}{Color.reset()}")
            return True
        except Exception as e:
            logger.error(f"FFmpeg mixing error: {str(e)}")
            return False
    
    async def build_ffmpeg_command(
        self, video_file: str, audio_file: str, temp_file_path: Path
                                   ) -> List[str]:
        if audio_file is not None:
            return [
                "ffmpeg",
                "-i", str(video_file),
                "-i", str(audio_file),
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                "-movflags", "+faststart+frag_keyframe+empty_moov+default_base_moof",
                "-fflags", "+genpts",
                "-map_metadata", "-1",
                "-map_chapters", "-1",
                "-metadata", "title=",
                "-metadata", "comment=",
                "-f", "mp4",
                "-y",
                str(temp_file_path),
            ]
        if audio_file is None:
            return [
                "ffmpeg",
                "-i", str(video_file),
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                "-movflags", "+faststart+frag_keyframe+empty_moov+default_base_moof",
                "-fflags", "+genpts",
                "-map_metadata", "-1",
                "-map_chapters", "-1",
                "-metadata", "title=",
                "-metadata", "comment=",
                "-f", "mp4",
                "-y",
                str(temp_file_path),
            ]
            
            
        
