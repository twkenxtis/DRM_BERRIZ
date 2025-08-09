import logging
import os
import time
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import jwt
import requests


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("cookies")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "cookies.py.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)

    app_logger.addHandler(console_handler)
    app_logger.addHandler(app_file_handler)
    return app_logger


logger = setup_logging()


class CookieUtils:
    """Static class for common cookie-related utilities."""

    BASE_URL = "https://berriz.in"
    REQUIRED_COOKIES = ["_T_ANO", "pacode", "pcid", "__T_", "__T_SECURE"]

    @staticmethod
    def get_bz_r(file_path: str = "cookies/Berriz/default.txt") -> str:
        """Get the bz_r value from the Netscape cookie file."""
        try:
            cookie_reader = NetscapeCookieReader(file_path)
            bz_r = cookie_reader.get_cookie("bz_r")
            if not bz_r:
                logger.error(f"bz_r cookie not found in {file_path}")
                raise ValueError(f"bz_r cookie not found in {file_path}")
            return bz_r
        except FileNotFoundError as e:
            logger.error(f"Failed to load bz_r: {e}")
            raise

    @staticmethod
    def get_default_cookies(file_path: str = "cookies/Berriz/default.txt") -> dict:
        """Get default cookies from the Netscape cookie file."""
        try:
            cookie_reader = NetscapeCookieReader(file_path)
            cookies = {}
            missing_cookies = []
            for cookie_name in CookieUtils.REQUIRED_COOKIES:
                cookie_value = cookie_reader.get_cookie(cookie_name)
                if not cookie_value:
                    missing_cookies.append(cookie_name)
                else:
                    cookies[cookie_name] = cookie_value
            if missing_cookies:
                logger.error(f"Missing required cookies in {file_path}: {missing_cookies}")
                raise ValueError(f"Missing required cookies in {file_path}: {missing_cookies}")
            return cookies
        except FileNotFoundError as e:
            logger.error(f"Failed to load default cookies: {e}")
            raise

    @staticmethod
    def get_initial_headers(file_path: str = "cookies/Berriz/default.txt") -> dict:
        """Get initial headers with bz_r from the cookie file."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Referer": CookieUtils.BASE_URL + "/",
            "Origin": CookieUtils.BASE_URL,
            "Alt-Used": "account.berriz.in",
            "Connection": "keep-alive",
            "TE": "trailers",
        }
        headers["bz_r"] = CookieUtils.get_bz_r(file_path)
        return headers

    @staticmethod
    def load_bz_a(file_path: str = "cookies/bz_a.txt") -> str:
        """Load bz_a token from the specified file."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("")
            return ""


class NetscapeCookieReader:
    """Class to read cookies from a Netscape format cookie file."""

    def __init__(self, file_path: str = "cookies/Berriz/default.txt"):
        self.file_path = Path(file_path)
        self.cookies = {}
        self.load_cookies()

    def load_cookies(self) -> None:
        """Load cookies from the Netscape cookie file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"Cookie file not found: {self.file_path}")

        with open(self.file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        name = parts[5]
                        value = parts[6]
                        self.cookies[name] = value
                    else:
                        logger.warning(f"Skipping malformed cookie line: {line}")

    def get_cookie(self, name: str) -> str:
        """Get a specific cookie value by name."""
        return self.cookies.get(name, "")


class Refresh_JWT:
    REFRESH_FILE = Path("cookies/refresh_time.txt")

    if not os.path.exists("cookies"):
        os.mkdir("cookies")

    @staticmethod
    def refresh_token(current_access_token=None):
        url = "https://account.berriz.in/auth/v1/token:refresh?languageCode=en"
        headers = CookieUtils.get_initial_headers()
        json_data = {"clientId": "e8faf56c-575a-42d2-933d-7b2e279ad827"}

        try:
            response = requests.post(url, headers=headers, json=json_data)
            logger.info(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] - {response.status_code} {url}"
            )

            if response.status_code == 200:
                json_obj = response.json()
                access_token = json_obj["data"]["accessToken"]

                try:
                    decoded_token = jwt.decode(
                        access_token, options={"verify_signature": False}
                    )
                    exp_time = decoded_token["exp"]
                    readable_time = datetime.fromtimestamp(exp_time).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    logger.info(f"Token will expire at {readable_time}")
                except Exception as decode_error:
                    logger.warning(f"Failed to decode token: {decode_error}")

                with open("cookies/bz_a.txt", "w") as f:
                    f.write(access_token)

                logger.info(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] - Access Token saved to bz_a.txt"
                )
                return access_token
            else:
                logger.error(f"FAILED: {response.text}")
                return None
        except Exception as e:
            logger.error(f"ERROR: {e}")
            return None

    @staticmethod
    def my_state_test():
        bz_a = CookieUtils.load_bz_a()
        cookies = CookieUtils.get_default_cookies()
        cookies["bz_a"] = bz_a

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148; "
                "iPhone17.6.1; fanz-ios 1.1.4; iPhone12,3"
            ),
            "Accept": "application/json",
            "Referer": CookieUtils.BASE_URL + "/",
            "Alt-Used": "svc-api.berriz.in",
            "Connection": "keep-alive",
        }

        params = {"languageCode": "en"}

        response = requests.get(
            "https://svc-api.berriz.in/service/v1/my/state",
            params=params,
            cookies=cookies,
            headers=headers,
        )
        response_json = response.json()
        if response_json.get("message") == "SUCCESS":
            logger.info("Cookie test successful.")
        else:
            logger.error("Cookie test failed.")

    @staticmethod
    def refresh_and_test():
        token = Refresh_JWT.refresh_token()
        if not token:
            logger.error("Initial token refresh failed.")
            return None
        time.sleep(1)
        Refresh_JWT.my_state_test()
        return token

    @staticmethod
    def should_refresh() -> bool:
        if not Refresh_JWT.REFRESH_FILE.exists():
            return True

        try:
            with open(Refresh_JWT.REFRESH_FILE, "r") as f:
                timestamp_str = f.read().strip()
                next_refresh_time = datetime.strptime(
                    timestamp_str, "%Y-%m-%d %H:%M:%S"
                )
                now = datetime.now()
                delta = (next_refresh_time - now).total_seconds()
                return delta < 60
        except Exception as e:
            logger.warning(f"Failed to parse refresh_time.txt: {e}")
            return True

    @staticmethod
    def write_next_refresh_time():
        next_time = datetime.now() + timedelta(minutes=50)
        with open(Refresh_JWT.REFRESH_FILE, "w") as f:
            f.write(next_time.strftime("%Y-%m-%d %H:%M:%S"))
        logger.info(
            f"Next refresh time written to {Refresh_JWT.REFRESH_FILE}: {next_time}"
        )

    @staticmethod
    def main():
        if Refresh_JWT.should_refresh():
            logger.info("Token refresh triggered.")
            token = Refresh_JWT.refresh_and_test()
            if token:
                Refresh_JWT.write_next_refresh_time()
            else:
                logger.warning("Refresh failed, next refresh time not updated.")
        else:
            pass


class Berriz_cookie:
    def __init__(self):
        self._cookies = {}
        self.load_cookies()

    def load_cookies(self) -> None:
        bz_a = CookieUtils.load_bz_a()
        self._cookies = CookieUtils.get_default_cookies()
        self._cookies["bz_a"] = bz_a
        self._cookies["bz_r"] = CookieUtils.get_bz_r()
