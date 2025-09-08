import subprocess
from pathlib import Path

from typing import Optional, List

from static.color import Color
from unit.handle_log import setup_logging
from unit.parameter import paramstore


logger = setup_logging('mux', 'lavender')


class FFmpegMuxer:
    def __init__(self, base_dir: Path, decryption_key: Optional[List] = None):
        self.base_dir = base_dir
        self.decryption_key = decryption_key

    def _prepare_track(self, track_type: str) -> Optional[Path]:
        """Handle decryption if needed and return final file path"""
        input_file = self.base_dir / f"{track_type}.ts"

        if not input_file.exists():
            return None

        # Check for encryption
        kid = self._check_encryption(input_file)

        if kid and self.decryption_key:
            logger.info(
                f"{Color.fg('blue')}Detected{Color.reset()} {Color.fg('cyan')}{track_type} {Color.reset()}{Color.fg('blue')}"
                f"{Color.reset()}{Color.fg('blue')}decrypting...{Color.reset()}"
            )
            decryption_key = self.process_decryption_key()
            decrypted_file = self.base_dir / f"{track_type}_decrypted.ts"
            if self._decrypt_file(input_file, decrypted_file, decryption_key):
                return decrypted_file
            return None
        elif kid:
            logger.warning(
                f"Warning: {track_type} track is encrypted but no decryption key is provided."
            )
            return None

        # No encryption, use original file
        return input_file

    def process_decryption_key(self):
        if type(self.decryption_key) is list:
            key = ' '.join([str(sublist).replace('[', '').replace(']', '') for sublist in self.decryption_key])
            return key
        elif type(self.decryption_key) is str:
            return self.decryption_key

    def _check_encryption(self, file_path: Path) -> Optional[str]:
        """Check if file is encrypted using mp4info and return KID if found"""
        try:
            result = subprocess.run(
                ["mp4info", str(file_path)], capture_output=True, text=True
            )

            if "encrypted" in result.stdout.lower():
                return "encrypted"
            return None
        except Exception as e:
            logger.error(f"Encryption check failed {file_path}: {str(e)}")
            return None

    def _decrypt_file(
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
            subprocess.run(
                [
                    str(mp4decrypt_path),
                    "--key",
                    key,
                    str(input_path),
                    str(output_path),
                ],
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

    def mux_to_mp4(self, output_name: str = "output.mp4") -> bool:
        # Prepare video and audio tracks
        video_file = self._prepare_track("video")
        audio_file = self._prepare_track("audio")

        if (not video_file or not audio_file) and paramstore.get('skip_merge') is not True:
            logger.warning(
                "Error: Valid video and audio must exist simultaneously for multiplexing."
            )
            return False
        elif paramstore.get('skip_merge') is True:
            return False

        output_file = self.base_dir / output_name

        logger.info(F"{Color.fg('light_gray')}Start using FFmpeg to mux video and audio...{Color.reset()}")

        # Standard FFmpeg command without modification
        cmd = [
            "ffmpeg",
            "-i",
            str(video_file),
            "-i",
            str(audio_file),
            "-c",
            "copy",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-metadata",
            "title=",
            "-metadata",
            "comment=",
            "-f",
            "mp4",
            "-movflags",
            "+faststart+frag_keyframe+empty_moov+default_base_moof",
            "-fflags",
            "+genpts",
            "-y",
            str(output_file),
        ]

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

            logger.info(f"{Color.fg('gray')}Mixed flow completed: {output_file}{Color.reset()}")
            return True
        except Exception as e:
            logger.error(f"FFmpeg mixing error: {str(e)}")
            return False
