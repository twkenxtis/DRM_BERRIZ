import subprocess
import logging
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class FFmpegMuxer:
    def __init__(self, base_dir: Path, decryption_key: Optional[str] = None):
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
            logging.info(
                f"Detected {track_type} track encryption (KID: {kid}), decrypting..."
            )
            decrypted_file = self.base_dir / f"{track_type}_decrypted.ts"
            if self._decrypt_file(input_file, decrypted_file, self.decryption_key, kid):
                return decrypted_file
            return None
        elif kid:
            logging.warning(
                f"Warning: {track_type} track is encrypted but no decryption key is provided."
            )
            return None

        # No encryption, use original file
        return input_file

    def _check_encryption(self, file_path: Path) -> Optional[str]:
        """Check if file is encrypted using mp4info and return KID if found"""
        try:
            result = subprocess.run(
                ["mp4info", str(file_path)], capture_output=True, text=True
            )

            if "encrypted" in result.stdout.lower():
                # Extract KID from output
                for line in result.stdout.splitlines():
                    if "default_KID" in line:
                        return line.split("=")[1].strip().strip("{}")
                return "encrypted_unknown_kid"
            return None
        except Exception as e:
            logging.error(f"Encryption check failed {file_path}: {str(e)}")
            return None

    def _decrypt_file(
        self,
        input_path: Path,
        output_path: Path,
        key: str,
        kid: str,
    ) -> bool:
        current_dir = Path(__file__).parent
        parent_tools_dir = current_dir.parent / "tools"
        mp4decrypt_path = parent_tools_dir / "mp4decrypt.exe"

        if not mp4decrypt_path.exists():
            logging.error(f"mp4decrypt.exe not found at: {mp4decrypt_path}")
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
            logging.error(f"Decryption failed for {input_path}: {e.stderr or e.stdout}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error decrypting {input_path}: {str(e)}")
            return False

    def mux_to_mp4(self, output_name: str = "output.mp4") -> bool:
        # Prepare video and audio tracks
        video_file = self._prepare_track("video")
        audio_file = self._prepare_track("audio")

        if not video_file or not audio_file:
            logging.warning(
                "Error: Valid video and audio must exist simultaneously for multiplexing."
            )
            return False

        output_file = self.base_dir / output_name

        logging.info("Start using FFmpeg to mux video and audio...")

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
                logging.error(f"FFmpeg multiplexing failed:\n{result.stderr}")
                return False

            logging.info(f"Mixed flow completed: {output_file}")
            return True
        except Exception as e:
            logging.error(f"FFmpeg mixing error: {str(e)}")
            return False
