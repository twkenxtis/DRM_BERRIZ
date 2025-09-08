import asyncio
import os
import time
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import List, Dict, Any

import jwt
import requests

from static.color import Color
from unit.handle_log import setup_logging

DEFAULT_COOKIE = Path("cookies/Berriz/default.txt")
REFRESH_FILE = Path("cookies/refresh_time.txt")
BZ_A_PATH = Path("cookies/bz_a.bin")

logger = setup_logging('cookies', 'firebrick')


class CookieUtils:
    """Static class for common cookie-related utilities."""

    BASE_URL = "https://berriz.in"
    REQUIRED_COOKIES = ["pcid"]

    @staticmethod
    def _ensure_directory(file_path: str) -> None:
        """Ensure the directory for the given file path exists."""
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)

    @staticmethod
    def get_bz_r() -> str:
        """Get the bz_r value from the Netscape cookie file."""
        try:
            bz_r = NetscapeCookieReader().get_cookie("bz_r")
            if not bz_r:
                raise ValueError(f"bz_r cookie not found in {DEFAULT_COOKIE}")
            return bz_r
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to load bz_r: {e}")
            raise

    @staticmethod
    def get_default_cookies() -> dict:
        """Get default cookies from the Netscape cookie file."""
        try:
            cookie_reader = NetscapeCookieReader()
            cookies = {
                name: cookie_reader.get_cookie(name)
                for name in CookieUtils.REQUIRED_COOKIES
                if cookie_reader.get_cookie(name)
            }
            if len(cookies) != len(CookieUtils.REQUIRED_COOKIES):
                missing = [
                    name for name in CookieUtils.REQUIRED_COOKIES if name not in cookies
                ]
                raise ValueError(f"Missing required cookies in {DEFAULT_COOKIE}: {missing}")
            return cookies
        except (ValueError) as e:
            raise ValueError(e)

    @staticmethod
    def get_initial_headers() -> dict:
        """Get initial headers with bz_r from the cookie file."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": f"{CookieUtils.BASE_URL}/",
            "Origin": CookieUtils.BASE_URL,
            "Alt-Used": "account.berriz.in",
            "Connection": "keep-alive",
            "TE": "trailers",
            "bz_r": CookieUtils.get_bz_r(),
        }
        return headers

    
    @staticmethod
    def save_bz_a(token: str) -> None:
        CookieUtils._ensure_directory(BZ_A_PATH)
        
        with open(BZ_A_PATH, "wb") as f:
            f.write(token.encode("utf-8"))

    @staticmethod
    def load_bz_a() -> str:
        if not BZ_A_PATH.exists():
            return ""
            
        try:
            with open(BZ_A_PATH, "rb") as f:
                return f.read().decode("utf-8").strip()
        except Exception:
            return ""


class NetscapeCookieReader:
    """Class to read cookies from a Netscape format cookie file."""

    def __init__(self):
        self.file_path = Path(DEFAULT_COOKIE)
        CookieUtils._ensure_directory(DEFAULT_COOKIE)
        self.cookies = {}
        self.load_cookies()

    def load_cookies(self) -> None:
        """Load cookies from the Netscape cookie file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"Cookie file not found: {self.file_path}")
        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and len(line.split("\t")) >= 7:
                    name, value = line.split("\t")[5:7]
                    self.cookies[name] = value
                else:
                    logger.warning(f"Skipping malformed cookie line: {line}")

    def get_cookie(self, name: str) -> str:
        """Get a specific cookie value by name."""
        return self.cookies.get(name, "")


class Refresh_JWT:
    @staticmethod
    def refresh_token() -> str | None:
        """Refresh the JWT token and save it to bz_a"""
        url = "https://account.berriz.in/auth/v1/token:refresh?languageCode=en"
        headers = CookieUtils.get_initial_headers()
        json_data = {"clientId": "e8faf56c-575a-42d2-933d-7b2e279ad827"}

        try:
            response = requests.post(url, headers=headers, json=json_data)
            logger.info(
                f"{Color.fg('light_gray')}{response.status_code} {url}{Color.reset()}"
            )
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.text}")
                return None

            access_token = response.json()["data"]["accessToken"]
            try:
                decoded = jwt.decode(access_token, options={"verify_signature": False})
                exp_time = datetime.fromtimestamp(decoded["exp"]).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                logger.info(
                    f"{Color.fg('beige')}Token expires at {exp_time}{Color.reset()}"
                )
            except Exception as e:
                logger.warning(f"Failed to decode token: {e}")

            CookieUtils.save_bz_a(access_token)
            logger.info(
                f"{Color.fg('peach')}Access Token saved to {BZ_A_PATH}{Color.reset()}"
            )
            return access_token
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None

    @staticmethod
    def my_state_test() -> None:
        """Test cookie validity by making a state request."""
        cookies = CookieUtils.get_default_cookies()
        cookies["bz_a"] = CookieUtils.load_bz_a()
        headers = CookieUtils.get_initial_headers()
        params = {"languageCode": "en"}

        response = requests.get(
            "https://svc-api.berriz.in/service/v1/my/state",
            params=params,
            cookies=cookies,
            headers=headers,
        )
        logger.info(
            f"{Color.fg('chartreuse') if response.json().get('message') == 'SUCCESS' else Color.fg('red')}Cookie test {'successful' if response.json().get('message') == 'SUCCESS' else 'failed'}.{Color.reset()}"
        )

    @staticmethod
    def refresh_and_test() -> str | None:
        """Refresh token and test cookie validity."""
        token = Refresh_JWT.refresh_token()
        if token:
            Refresh_JWT.my_state_test()
        else:
            logger.error("Initial token refresh failed.")
        return token

    @staticmethod
    def should_refresh() -> bool:
        """Check if token refresh is needed based on refresh_time.txt."""
        if not REFRESH_FILE.exists():
            return True
        try:
            with open(REFRESH_FILE, "r") as f:
                next_refresh = datetime.strptime(f.read().strip(), "%Y-%m-%d %H:%M:%S")
                return (next_refresh - datetime.now()).total_seconds() < 60
        except Exception as e:
            logger.warning(f"Failed to parse refresh_time.txt: {e}")
            return True

    @staticmethod
    def write_next_refresh_time() -> None:
        """Write the next refresh time to refresh_time.txt."""
        next_time = datetime.now() + timedelta(minutes=50)
        CookieUtils._ensure_directory(str(REFRESH_FILE))
        with open(REFRESH_FILE, "w") as f:
            f.write(next_time.strftime("%Y-%m-%d %H:%M:%S"))
        logger.info(f"{Color.fg('plum')}Next refresh: {next_time}{Color.reset()}")

    @staticmethod
    def main() -> None:
        """Main method to handle token refresh if needed."""
        
        if (os.path.exists(DEFAULT_COOKIE) and os.path.getsize(DEFAULT_COOKIE) > 0) is False:
            return
        
        if Refresh_JWT.should_refresh():
            logger.info(
                f"{Color.fg('dark_red')}Token refresh triggered.{Color.reset()}"
            )
            if Refresh_JWT.refresh_and_test():
                Refresh_JWT.write_next_refresh_time()
            else:
                logger.warning("Refresh failed, next refresh time not updated.")


class NetscapeCookieReader:
    """Class to read cookies from a Netscape format cookie file."""
    def __init__(self):
        self.file_path = Path(DEFAULT_COOKIE)

    @cached_property
    def cookies(self) -> dict:
        if not self.file_path.exists():
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            raise FileNotFoundError(f"Cookie file not found: {self.file_path}")

    @cached_property
    def cookies(self) -> Dict[str, str]:
        if not self.file_path.exists():
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            return {}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        except Exception as e:
            logger.error(f"Failed to read cookie file: {e}")
            return {}

        cookies_dict = {}
        for line in lines:
            parts = line.split("\t")
            if len(parts) >= 7:
                try:
                    name, value = parts[5], parts[6]
                    cookies_dict[name] = value
                except IndexError:
                    logger.warning(f"Skipping malformed cookie line (invalid parts): {line}")
            else:
                logger.warning(f"Skipping malformed cookie line (too few parts): {line}")
        
        return cookies_dict

    def get_cookie(self, name: str) -> str:
        """Get a specific cookie value by name."""
        return self.cookies.get(name, "")


class Berriz_cookie:
    _instance = None
    show_no_cookie_log = True

    def __new__(cls):
        if cls._instance is None:
            # 如果不存在，創建一個新的實例
            cls._instance = super(Berriz_cookie, cls).__new__(cls)
            cls._instance.load_cookies()
        return cls._instance

    def __init__(self):
        pass

    def load_cookies(self) -> None:
        """Load cookies from disk."""
        self._cookies = {}
        try:
            # 觸發 token 重新整理
            Refresh_JWT.main()
            # 載入 cookies
            self._cookies = CookieUtils.get_default_cookies()
            self._cookies["bz_a"] = CookieUtils.load_bz_a()
            self._cookies["bz_r"] = CookieUtils.get_bz_r()
            
            logger.info(f"{Color.fg('chartreuse')}Cookies loaded: {Color.fg('dark_gray')}{list(self._cookies.values())}{Color.reset()}")
        except Exception as e:
            if Berriz_cookie.show_no_cookie_log:
                logger.warning(f"{Color.fg('light_gray')}No cookie found, {Color.fg('pink')}request without cookies{Color.reset()}")
                Berriz_cookie.show_no_cookie_log = False
            self._cookies = {}