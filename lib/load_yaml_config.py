import asyncio
import re
import sys
import os
import yaml

from pathlib import Path
from functools import lru_cache

import aiofiles
import rich.traceback
from email_validator import validate_email, EmailNotValidError

from static.color import Color
from static.route import Route
from key.drm.cdm_path import CDM_PATH
from static.route import Route
from unit.handle.handle_log import setup_logging

rich.traceback.install()
logger = setup_logging('load_yaml_config', 'fresh_chartreuse')


YAML_PATH: Path = Route().YAML_path


DEFAULT_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6_1 like Mac OS X) '
    'AppleWebKit/605.1.16 (KHTML, like Gecko) Mobile/15E148; '
    'iPhone18.6.1; iPhone17,2'
)


def check_email(email_str: str) -> bool:
    try:
        validate_email(email_str)
        return True
    except EmailNotValidError as e:
        logger.error(f"Mail invaild:  '{email_str}' | {e}")
        return False


def tools_check() -> None:
    R = Route()
    tools = {
        "mp4decrypt": R.mp4decrypt_path,
        "packager": R.packager_path,
        "mkvmerge": R.mkvmerge_path,
    }

    missing = {name: path for name, path in tools.items() if not os.path.exists(path)}

    if missing:
        msg = (
            f"Missing tools:{Color.fg('gold')} "
            + ", ".join(f"{name} ({path})" for name, path in missing.items())
        )
        logger.error(msg)
        raise FileNotFoundError(f"{', '.join(missing)} not found exit.")
tools_check()

class ConfigLoader:
    @classmethod
    @lru_cache(maxsize=1)
    def load(cls, path: Path = YAML_PATH) -> dict:
        """同步介面，快取並返回完整、驗證過的 config 字典。"""
        config = asyncio.run(cls._load_async(path))
        try:
            cls.check_cfg(config)
        except Exception as e:
            logger.error(f"{Color.fg('ruby')}Failed to load config: {e}{Color.reset()}")
            sys.exit(1)
        return config

    @staticmethod
    async def _load_async(path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()

        try:
            return yaml.safe_load(raw)
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse YAML: {e}")

    @staticmethod
    def check_cfg(config: dict) -> None:
        """驗證並填充 config 各區段的預設值。"""
        if not isinstance(config, dict):
            raise TypeError("Config must be a dictionary")

        # 1. duplicate 區段
        dup = config.get("duplicate")
        if not isinstance(dup, dict):
            raise TypeError("duplicate must be a dict")
        if not isinstance(dup.get("default"), bool):
            raise TypeError("duplicate.default must be boolean")
        overrides = dup.get("overrides", {})
        if not isinstance(overrides, dict):
            raise TypeError("duplicate.overrides must be a dict")
        for key in ("image", "video", "post", "notice"):
            val = overrides.get(key)
            if val is None:
                ConfigLoader.print_warning(key, val, 'False')
                overrides[key] = False
            elif not isinstance(val, bool):
                raise TypeError(f"duplicate.overrides.{key} must be boolean")
        dup["overrides"] = overrides
        config["duplicate"] = dup

        # 2. headers.User-Agent
        headers = config.get("headers", {})
        if not isinstance(headers, dict):
            raise TypeError("headers must be a dict")
        ua = headers.get("User-Agent")
        if not ua or not isinstance(ua, str):
            ConfigLoader.print_warning('User-Agent', ua, DEFAULT_UA)
            headers["User-Agent"] = DEFAULT_UA
        config["headers"] = headers

        # 3. output_template 區段
        ot = config.get("output_template", {})
        if not isinstance(ot, dict):
            raise TypeError("output_template must be a dict")
        if not ot.get("video") or not isinstance(ot["video"], str):
            raise ValueError("output_template.video must be a non-empty <string> !!")
        if isinstance(ot.get("video"), str) and not "{title}" in ot.get("video"):
            raise ValueError("output_template.video require at least one {title} in name as arg")
        if not isinstance(ot["tag"], str):
            ConfigLoader.print_warning('output_template.tag, must be a string', ot["tag"], 'Empty-Tag')
            ot["tag"] = ""
        if not ot.get("date_formact") or not isinstance(ot["date_formact"], str):
            ConfigLoader.print_warning('output_template.date_formact', ot["date_formact"], '%Y%m%d_%H%M%S')
            ot["date_formact"] = "%Y%m%d.%H%M%S"
        config["output_template"] = ot

        # 4. Donwload_Dir_Name 區段
        dld = config.get("Donwload_Dir_Name", {})
        if not isinstance(dld, dict):
            raise TypeError("Donwload_Dir_Name must be a dict")
        if not dld.get("download_dir") or not isinstance(dld["download_dir"], str):
            ConfigLoader.print_warning("Donwload_Dir_Name.download_dir", dld["download_dir"], "Berriz.Downloads")
            dld["download_dir"] = "Berriz.Downloads"
        if not dld.get("dir_name") or not isinstance(dld["dir_name"], str):
            ConfigLoader.print_warning('Donwload_Dir_Name.dir_name', dld["dir_name"], "{date} {community_name} {artist} {title}")
            dld["dir_name"] = "{date} {community_name} {artist} {title}"
        if not dld.get("date_formact") or not isinstance(dld["date_formact"], str):
            ConfigLoader.print_warning('Donwload_Dir_Name.date_formact', dld["date_formact"], "%y%m%d_%H-%M_%S")
            dld["date_formact"] = "%y%m%d_%H-%M_%S"
        config["Donwload_Dir_Name"] = dld

        # 5. Container 區段
        cont = config.get("Container", {})
        if not isinstance(cont, dict):
            raise TypeError("Container must be a dict")
        if not isinstance(cont.get("mux"), str):
            ConfigLoader.print_warning('Container.mux', cont.get("mux"), 'ffmpeg')
            cont["mux"] = "ffmpeg"
        if cont.get("mux").lower() not in ("ffmpeg", "mkvtoolnix"):
            raise ValueError("Container.mux must be 'ffmpeg' or 'mkvtoolnix'")
        if cont.get("video") not in ("ts", "mp4", "mov", "m4v", "mkv", "avi"):
            raise ValueError("Container.video must be one of ts, mp4, mov, m4v, mkv, avi")
        if not isinstance(cont.get("decryption-engine"), str):
            ConfigLoader.print_warning('Container.decryption-engine', cont.get("decryption-engine"), 'shaka-packager')
            cont["decryption-engine"] = "SHAKA_PACKAGER"
        if isinstance(cont.get("decryption-engine"), str):
            decryption_engine = cont.get("decryption-engine").lower()
            all_chars = list(decryption_engine)
            target_chars = list("shakapackager")
            
            # 條件1: 包含所有必要字符
            has_all_chars = all(char in all_chars for char in target_chars)
            # 條件2: 在有序情況下能拼出 "shaka" 或 "packa"
            can_form_shaka = "shaka" in decryption_engine
            can_form_packa = "packager" in decryption_engine
            if has_all_chars and (can_form_shaka or can_form_packa):
                cont["decryption-engine"] = "SHAKA_PACKAGER"

        # 6. HLS or MPEG-SASH 區段
        hls_sec = config.get("HLS or MPEG-SASH", {})
        if not isinstance(hls_sec, dict):
            raise TypeError("HLS or MPEG-SASH must be a dict")
        if not isinstance(hls_sec.get("HLS"), bool):
            ConfigLoader.print_warning('HLS or MPEG-SASH.HLS', hls_sec.get("HLS"), 'Set to not use HLS for dl')
            hls_sec["HLS"] = False
        config["HLS or MPEG-SASH"] = hls_sec

        # 7. TimeZone 區段
        tz = config.get("TimeZone", {})
        if not isinstance(tz, dict):
            raise TypeError("TimeZone must be a dict")
        time_str = tz.get("time")
        if not isinstance(time_str, (int, str)):
            raise ValueError("TimeZone.time must be a string or int")
        if isinstance(time_str, str):
            int_brisbane_offset = int(re.sub(r'(?i)|utc', '', time_str).strip().lower())
            if not (-12 <= int_brisbane_offset <= 14):
                ConfigLoader.print_warning('TimeZone invaild should be -12 ~ +14', int_brisbane_offset, "UTC +9")
                tz["TimeZone"] = 9

        # 8. KeyService 區段
        ks = config.get("KeyService", {})
        valid_sources = {"mspr", "wv", "watora_wv", "cdrm_wv", "cdrm_mspr"}
        if not isinstance(ks, dict):
            raise TypeError("KeyService must be a dict")
        elif not isinstance(ks.get("source"), str):
            raise ValueError("KeyService.source must be a string")
        if ks.get("source") not in valid_sources:
            match ks.get("source").lower():
                case "widevine":
                    ks["KeyService"] = 'wv'
                case "playready":
                    ConfigLoader.print_warning('DRM-Key Service', ks.get("source"), "CDRM Widevine")
                    ks["KeyService"] = 'mspr'
                case _:
                    ConfigLoader.print_warning('DRM-Key Service', ks.get("source"), "CDRM Widevine")
                    ks["KeyService"] = 'cdrm_wv'
                    
        # 9. CDM
        cdm = config.get("CDM", {})
        if not isinstance(cdm, dict):
            raise TypeError("CDM must be a dict")
        if not isinstance(cdm.get("widevine"), str):
            raise ValueError("CDM.widevine must be a string")
        elif isinstance(cdm.get("widevine"), str):
            if not cdm.get("widevine").strip().lower().endswith(".wvd"):
                raise ValueError("CDM.widevine must be a wvd file")
            cdm_path = CDM_PATH({"CDM":{"widevine": cdm.get("widevine"), "playready": cdm.get("playready")}})
            if not os.path.exists(cdm_path.wv_device_path):
                raise ValueError(f"CDM.widevine not found {cdm_path.wv_device_path}")
        if not isinstance(cdm.get("playready"), str):
            raise ValueError("CDM.playready must be a string")
        elif isinstance(cdm.get("playready"), str):
            if not cdm.get("playready").strip().lower().endswith(".prd"):
                raise ValueError("CDM.widevine must be a prd file")
            if not os.path.exists(cdm_path.prd_device_path):
                raise ValueError(f"CDM.playready not found {cdm_path.prd_device_path}")

        # 10. berriz 區段
        user = config.get("berriz", {})
        if not isinstance(user, dict):
            raise TypeError("berriz must be a dict")
        if not isinstance(user.get("account"), str):
            raise ValueError("berriz.account must be a string")
        elif isinstance(user.get("account"), str):
            if check_email(user.get("account")) is False:
                raise ValueError("berriz.account must be a vaild E-mail")
        if not isinstance(user.get("password"), str):
            raise ValueError("berriz.password must be a tring")
        config["berriz"] = user
    
        # 11. logging
        log = config.get("logging", {})
        if not isinstance(log, dict):
            raise TypeError("logging must be a dict")
        if not isinstance(log.get("level"), str):
            raise ValueError("logging.level must be a string")
        elif isinstance(log.get("level"), str):
            if log.get("level").lower() not in ("debug", "info", "warning", "error", "critical"):
                raise ValueError("logging.level must be one of debug, info, warning, error, critical")
        if not isinstance(log.get("format"), str):
            raise ValueError("logging.format must be a string")
        config["logging"] = log

    def print_warning(invaild_message: str, invaild_value: str,correct_message: str) -> None:
        logger.warning(
            f"Unsupported value {Color.bg('ruby')}{invaild_message}{Color.reset()}"
            f"{Color.fg('gold')} in config: "
            f"{Color.fg('ruby')}{invaild_value} {Color.reset()}"
            f"{Color.fg('dove')}= {Color.reset()}"
            f"{Color.fg('ruby')}{type(invaild_value)}{Color.reset()}"
            f"{Color.fg('gold')} Try using "
            f"{Color.fg('red')}{correct_message} {Color.reset()}"
            f"{Color.fg('gold')}to continue ...{Color.reset()}"
            )

CFG = ConfigLoader.load()