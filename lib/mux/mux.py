import asyncio
import subprocess
from pathlib import Path
from typing import List, Optional, Any, Union

from lib.__init__ import container
from lib.load_yaml_config import CFG, ConfigLoader
from lib.mux.tools_path import ToolsPath
from static.color import Color
from unit.handle.handle_log import setup_logging
from static.parameter import paramstore


logger = setup_logging('mux', 'lavender')


class FFmpegMuxer:
    base_dir: Path
    decryption_key: Optional[List[Any]]
    
    def __init__(self, base_dir: Path, decryption_key: Optional[Union[List, str]] = None):
        self.base_dir = base_dir
        self.decryption_key = decryption_key
        self.key = None
        self.input_path = None
        self.output_path = None        

    async def _prepare_track(self, track_type: str) -> Optional[Path]:
        """Handle decryption if needed and return final file path"""
        input_file: Path = self.base_dir / f"{track_type}.{container}"
        self.input_path: Path = input_file
        if not input_file.exists():
            return None

        if self.decryption_key:
            logger.info(
                 f"{Color.fg('blue')}Detected{Color.reset()} {Color.fg('cyan')}{track_type} {Color.reset()}{Color.fg('blue')}"
                 f"{Color.reset()}{Color.fg('blue')}decrypting...{Color.reset()}"
            )
            decryption_key: str = await self.process_decryption_key()
            decrypted_file: Path = self.base_dir / f"{track_type}_decrypted.{container}"
            
            self.key = decryption_key
            self.output_path: Path = decrypted_file
            
            if await self.decrypt():
                return decrypted_file
            return None
        # No encryption, use original file
        return input_file

    async def process_decryption_key(self) -> str:
        if type(self.decryption_key) is list:
            # 假設子列表中的內容是可轉換為 str 的
            key: str = ' '.join([str(sublist).replace('[', '').replace(']', '') for sublist in self.decryption_key])
            return key
        elif type(self.decryption_key) is str:
            return self.decryption_key
        
        return ""
    
    async def decrypt(self,) -> bool:
        try:
            decryptionengine = CFG['Container']['decryption-engine']
            decryptionengine = decryptionengine.upper()
        except AttributeError:
            ConfigLoader.print_warning('decryptionengine', decryptionengine, 'shaka-packager')
            decryptionengine = 'SHAKA_PACKAGER'

        match decryptionengine:
            case 'MP4DECRYPT':
                logger.info("decrypt by mp4decrypt")
                return await self._decrypt_file_mp4decrypt()
            case 'SHAKA_PACKAGER':
                logger.info("decrypt by shaka-packager")
                return await self._decrypt_file_packager()
            case _:
                ConfigLoader.print_warning('decryptionengine', decryptionengine, 'shaka-packager')
                return await self._decrypt_file_packager()

    async def _decrypt_file_mp4decrypt(self) -> bool:
        mp4decrypt_path = ToolsPath().mp4decrypt_path

        if not mp4decrypt_path.exists():
            logger.error(f"mp4decrypt.exe not found at: {mp4decrypt_path}")
            return False
            
        try:
            # 分割 key 字串並為每個 key 添加 --key 參數
            key_parts: List[str] = self.key.split()
            key_args: List[str] = []
            for k in key_parts:
                key_args.extend(["--key", k])
            
            # 建立完整的命令
            command: List[str] = [str(mp4decrypt_path)] + key_args + [str(self.input_path), str(self.output_path)]
            
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Decryption failed for {self.input_path}: {e.stderr or e.stdout}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error decrypting {self.input_path}: {str(e)}")
            return False
    
    async def _decrypt_file_packager(self) -> bool:
        packager_path = ToolsPath().packager_path
        packager_output_path = Path(self.output_path).with_suffix(".m4v")

        if not packager_path.exists():
            logger.error(f"shaka-packager.exe not found at: {packager_path}")
            return False

        # 分割 key 字串並為每個 key 添加 --keys 參數
        key_lines: List[str] = self.key.strip().splitlines()
        key_args: List[str] = []

        for k in key_lines:
            try:
                kid, value = k.strip().split(":")
                key_args.extend(["--keys", f"key_id={kid}:key={value}"])
            except ValueError:
                logger.error(f"Invalid key format: {k}")
                return False

        # 建立完整的命令
        command: List[str] = [
            str(packager_path),
            f"input={self.input_path},stream_selector=0,output={packager_output_path}",
            "--enable_raw_key_decryption"
        ] + key_args

        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            logger.debug(f"Packager output: {result.stdout}")

            # 成功後改回指定副檔名
            final_output_path = packager_output_path.with_suffix(f".{container}")
            packager_output_path.rename(final_output_path)
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Packager failed: {e.stderr}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error running packager: {e}")
            return False
    
    async def mux_main(self, merge_type: str, tempfile_name: str) -> bool:
        # Prepare video and audio tracks
        async with asyncio.TaskGroup() as tg:
            video_task: asyncio.Task[Optional[Path]] = tg.create_task(self._prepare_track("video"))
            audio_task: asyncio.Task[Optional[Path]] = tg.create_task(self._prepare_track("audio"))

        # task.result() 實際上會回傳 Path 或 None
        video_file: Optional[Path] = video_task.result()
        audio_file: Optional[Path] = audio_task.result()
        
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

        # Standard FFmpeg command without modification
        temp_file_path: Path = self.base_dir / tempfile_name
        
        video_file_str: str = str(video_file) if video_file else ""
        audio_file_str: Optional[str] = str(audio_file) if audio_file else None
        
        if paramstore.get('skip_mux') is True:
            return True
        else:
            return await self.choese_mux_tool(video_file_str, audio_file_str, temp_file_path)
        
    async def choese_mux_tool(self, video_file_str: str, audio_file_str: str, temp_file_path: Path):
        try:
            mux_tool = CFG['Container']['mux']
            mux_tool = mux_tool.upper()
        except AttributeError:
            ConfigLoader.print_warning('MUX', mux_tool, 'ffmpeg')
            mux_tool = 'FFMPEG'
        MKVTOOLNIX_path: Path = ToolsPath().mkvmerge_path
        if not MKVTOOLNIX_path.exists():
            logger.error(f"shaka-packager.exe not found at: {MKVTOOLNIX_path}")
            return False
        match mux_tool:
            case 'FFMPEG':
                cmd: List[str] = await self.build_ffmpeg_command(video_file_str, audio_file_str, temp_file_path)
                
                try:
                    logger.info(F"{Color.fg('light_gray')}Start using FFmpeg to mux video and audio...{Color.reset()}")
                    result: subprocess.CompletedProcess = subprocess.run(
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
            case 'MKVTOOLNIX':
                cmd = [
                    MKVTOOLNIX_path,
                    "-o", str(temp_file_path),
                    str(Path(video_file_str)),
                    str(Path(audio_file_str)),
                ]
                try:
                    logger.info(f"{Color.fg('light_gray')}Start using mkvmerge to mux video and audio...{Color.reset()}")
                    result: subprocess.CompletedProcess = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                    )
                    if result.returncode != 0:
                        logger.error(f"mkvmerge multiplexing failed:\n{result.stderr}")
                        return False
                    logger.info(f"{Color.fg('gray')}Mixed flow completed: {temp_file_path}{Color.reset()}")
                    return True
                except Exception as e:
                    logger.error(f"mkvmerge mixing error: {str(e)}")
                    return False
            case _:
                logger.error(f"Unsupported mux tool: {mux_tool}")
                return False
        
    async def build_ffmpeg_command(
        self,
        video_file: str,
        audio_file: Optional[str],
        temp_file_path: Path
    ) -> List[str]:
        """
        建立 FFmpeg 命令，用於混流 video + audio 或僅封裝 video
        所有輸出皆為 copy 模式，無轉碼
        """

        command: List[str] = [
            "ffmpeg",
            "-i", video_file,
        ]

        if audio_file is not None:
            command += ["-i", audio_file]

        command += [
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            "-movflags", "+faststart+frag_keyframe+empty_moov+default_base_moof",
            "-fflags", "+genpts",
            "-map_metadata", "-1",
            "-map_chapters", "-1",
            "-metadata", "title=",
            "-metadata", "comment=",
            "-y",
            str(temp_file_path),
        ]

        return command
        
    async def build_mkvmerge_command(
            self, video_file: str, audio_file: Optional[str], temp_file_path: Path
        ) -> List[str]:
        command = [
            "mkvmerge",
            "--output", str(temp_file_path),
            "--no-chapters",              # 對應 -map_chapters -1
            "--no-global-tags",           # 對應 -map_metadata -1 (全局)
            "--no-track-tags",            # 對應 -map_metadata -1 (軌道)
            "--title", "",                # 對應 -metadata title=
            "--disable-language-ietf",    # 使用傳統語言代碼
        ]
        
        # 添加視訊檔案
        command.append(video_file)
        
        # 添加音訊檔案（如果存在）
        if audio_file is not None:
            command.append(audio_file)
        
        return command