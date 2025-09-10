import asyncio
import os
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, List

import jwt
import aiohttp
import aiofiles

from static.color import Color
from unit.handle_log import setup_logging


DEFAULT_COOKIE = Path("cookies/Berriz/default.txt")
REFRESH_FILE = Path("cookies/refresh_time.txt")
BZ_A_PATH = Path("cookies/bz_a.bin")
_refresh_lock = asyncio.Lock()


logger = setup_logging('cookies', 'firebrick')


class CookieUtils:
    """Static class for common cookie-related utilities."""

    BASE_URL = "https://berriz.in"
    REQUIRED_COOKIES = ["pcid"]

    @staticmethod
    async def get_bz_r() -> str:
        """Get the bz_r value from the Netscape cookie file."""
        try:
            bz_r = await NetscapeCookieReader().get_cookie("bz_r")
            if not bz_r:
                raise ValueError(f"bz_r cookie not found in {DEFAULT_COOKIE}")
            return bz_r
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to load bz_r: {e}")
            raise

    @staticmethod
    async def get_default_cookies() -> dict:
        """Get default cookies from the Netscape cookie file."""
        try:
            cookie_reader = NetscapeCookieReader()
            cookies = {
                name: await cookie_reader.get_cookie(name)
                for name in CookieUtils.REQUIRED_COOKIES
                if await cookie_reader.get_cookie(name)
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
    async def get_initial_headers() -> dict:
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
            "bz_r": await CookieUtils.get_bz_r(),
        }
        return headers

    @staticmethod
    async def save_bz_a(token: str) -> None:
        path = Path(BZ_A_PATH)
        await aiofiles.os.makedirs(path.parent, exist_ok=True)

        tmp_path = path.with_suffix(".tmp")
        try:
            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(token.encode("utf-8"))
            await aiofiles.os.replace(tmp_path, path)
        except Exception:
            if await aiofiles.os.path.exists(tmp_path):
                await aiofiles.os.remove(tmp_path)
            raise

    @staticmethod
    async def load_bz_a() -> str:
        path = Path(BZ_A_PATH)
        if not await aiofiles.os.path.exists(path):
            return ""

        try:
            async with aiofiles.open(path, "rb") as f:
                content = await f.read()
                return content.decode("utf-8").strip()
        except Exception:
            return ""


class Refresh_JWT:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def refresh_token(self) -> str | None:
        """Refresh the JWT token and save it to bz_a"""
        url = "https://account.berriz.in/auth/v1/token:refresh?languageCode=en"
        headers = await CookieUtils.get_initial_headers()
        json_data = {"clientId": "e8faf56c-575a-42d2-933d-7b2e279ad827"}

        try:
            async with self.session.post(url, headers=headers, json=json_data) as resp:
                data = await resp.json()
                
            if resp.status != 200:
                logger.error(f"Token refresh failed: {data}")
                return None

            access_token = data["data"]["accessToken"]
            try:
                decoded = jwt.decode(access_token, options={"verify_signature": False})
                exp_time = datetime.fromtimestamp(decoded["exp"]).strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"{Color.fg('beige')}Token expires at {exp_time}{Color.reset()}")
            except Exception as e:
                logger.warning(f"Failed to decode token: {e}")

            await CookieUtils.save_bz_a(access_token)
            logger.info(f"{Color.fg('peach')}Access Token saved to {BZ_A_PATH}{Color.reset()}")
            return access_token

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return None

    async def my_state_test(self) -> None:
        """Test cookie validity by making a state request."""
        async with asyncio.TaskGroup() as tg:
            cookies_task = tg.create_task(CookieUtils.get_default_cookies())
            bz_a_task = tg.create_task(CookieUtils.load_bz_a())
            headers_task = tg.create_task(CookieUtils.get_initial_headers())

        cookies = cookies_task.result()
        cookies["bz_a"] = bz_a_task.result()
        headers = headers_task.result()
        params = {"languageCode": "en"}

        try:
            async with self.session.get(
                "https://svc-api.berriz.in/service/v1/my/state",
                params=params,
                cookies=cookies,
                headers=headers,
            ) as resp:
                data = await resp.json()

                if resp.status != 200:
                    logger.error(f"Cookie test failed: {data}")
                    return
                elif data.get("message") != "SUCCESS":
                    logger.error(f"Cookie test failed: {data}")
                    return
                
                success = data.get("message") == "SUCCESS"
                logger.info(
                    f"{Color.fg('chartreuse') if success else Color.fg('red')}Cookie test {'successful' if success else 'failed'}.{Color.reset()}"
                )
        except Exception as e:
            logger.error(f"State test error: {e}")
            raise('Cookie test fail')

    async def refresh_and_test(self) -> str | None:
        """Refresh token and test cookie validity."""
        access_token = await self.refresh_token()
        if access_token:
            await self.my_state_test()
        else:
            logger.error("Initial token refresh failed.")
        return access_token

    async def should_refresh(self) -> bool:
        """Check if token refresh is needed based on refresh_time.txt using aiofiles."""
        if not REFRESH_FILE.exists():
            return True
        try:
            async with aiofiles.open(REFRESH_FILE, mode="r") as f:
                content = await f.read()
            next_refresh = datetime.strptime(content.strip(), "%Y-%m-%d %H:%M:%S")
            delta = (next_refresh - datetime.now()).total_seconds()
            return delta < 60
        except FileNotFoundError:
            return True
        except ValueError as ve:
            logger.warning(f"Invalid timestamp format in {REFRESH_FILE}: {ve}")
            return True
        except Exception as e:
            logger.warning(f"Error reading {REFRESH_FILE}: {e}")
            return True

    async def write_next_refresh_time(self) -> None:
        """Write the next refresh time safely with aiofiles and atomic replace."""
        next_time = datetime.now() + timedelta(minutes=50)
        tmp_file = REFRESH_FILE.with_suffix(".tmp")

        # Prevent concurrent reads/writes
        async with _refresh_lock:
            # Ensure the directory exists
            REFRESH_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Write to a temp file first
            async with aiofiles.open(tmp_file, mode="w") as f:
                await f.write(next_time.strftime("%Y-%m-%d %H:%M:%S"))

            # Atomically replace the old schedule
            await aiofiles.os.replace(str(tmp_file), str(REFRESH_FILE))

        logger.info(f"Next refresh: {next_time:%Y-%m-%d %H:%M:%S}")

    async def main(self) -> None:
        """Main method to handle token refresh if needed."""
        
        if (os.path.exists(DEFAULT_COOKIE) and os.path.getsize(DEFAULT_COOKIE) > 0) is False:
            return
        
        if await self.should_refresh():
            logger.info(
                f"{Color.fg('dark_red')}Token refresh triggered.{Color.reset()}"
            )
            if await self.refresh_and_test():
                asyncio.create_task(self.write_next_refresh_time())
            else:
                logger.warning("Refresh failed, next refresh time not updated.")


class NetscapeCookieReader:
    """Class to read cookies from a Netscape format cookie file."""

    def __init__(self):
        self.file_path = Path(DEFAULT_COOKIE)

    async def cookies(self) -> Dict[str, str]:
        if not await aiofiles.os.path.exists(self.file_path):
            await aiofiles.os.makedirs(self.file_path.parent, exist_ok=True)
            return {}

        try:
            async with aiofiles.open(self.file_path, "r", encoding="utf-8") as f:
                lines = []
                async for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        lines.append(line)
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

    async def get_cookie(self, name: str) -> str:
        """Get a specific cookie value by name."""
        cookies = await self.cookies()
        return cookies.get(name, "")

class Berriz_cookie:
    _instance = None
    show_no_cookie_log = True

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_cookies"):
            self._cookies = {}

    async def load_cookies(self) -> None:
        """Load cookies from disk."""
        self._cookies = {}
        try:
            # 觸發 token 重新整理
            await self.trigger_rwt()

            # 載入 cookies
            async with asyncio.TaskGroup() as tg:
                default_task = tg.create_task(CookieUtils.get_default_cookies())
                bz_a_task = tg.create_task(CookieUtils.load_bz_a())
                bz_r_task = tg.create_task(CookieUtils.get_bz_r())

            self._cookies = default_task.result()
            self._cookies["bz_a"] = bz_a_task.result()
            self._cookies["bz_r"] = bz_r_task.result()
            await self.check_cookie()
            logger.info(f"{Color.fg('chartreuse')}Cookies loaded: {Color.fg('dark_gray')}{list(self._cookies.values())}{Color.reset()}")
        except Exception as e:
            if Berriz_cookie.show_no_cookie_log:
                logger.warning(f"{Color.fg('light_gray')}No cookie found, {Color.fg('pink')}request without cookies{Color.reset()}")
                Berriz_cookie.show_no_cookie_log = False
            self._cookies = {}
            
    async def get_cookies(self) -> dict:
        if not hasattr(self, "_cookies") or not self._cookies:
            await self.load_cookies()
        return self._cookies
    
    async def check_cookie(self):
        if len(self._cookies.get('bz_a')) < 500:
            if os.path.exists(REFRESH_FILE):
                os.remove(REFRESH_FILE)
                await self.trigger_rwt()
                await self.load_cookies()
                
    async def trigger_rwt(self):
        # 觸發 token 重新整理
        async with aiohttp.ClientSession() as session:
            await Refresh_JWT(session).main()