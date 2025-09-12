import asyncio
import os
from datetime import datetime, timedelta
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jwt
import aiohttp
import aiofiles
import orjson

from lib.account.login import LoginManager
from static.color import Color
from unit.handle_log import setup_logging


DEFAULT_COOKIE = Path("cookies/Berriz/default.txt")
TEMP_JSON = Path("cookies/temp.json")
_refresh_lock = asyncio.Lock()


logger = setup_logging('cookies', 'firebrick')


class CookieUtils:
    BASE_URL = "https://berriz.in"
    REQUIRED_COOKIES = ["pcid"]

    async def _retry_with_action(self, action, error_log_cb, max_retries=5):
        retry_count = 0
        while retry_count < max_retries:
            try:
                return await action()
            except Exception as e:
                retry_count += 1
                error_log_cb(e, retry_count)
                await asyncio.sleep(1)
        error_log_cb("Max retry fail", retry_count)
        return None

    async def _read_cache_key(self, key: str) -> str:
        async def read_action():
            async with _refresh_lock:
                if not os.path.exists(TEMP_JSON):
                    return ""
                async with aiofiles.open(TEMP_JSON, "rb") as f:
                    content = await f.read()
                data = orjson.loads(content)
                return data.get('cache_cookie', {}).get(key, "")

        result = await self._retry_with_action(
            read_action,
            lambda e, rc: logger.warning(f"Read '{key}' issue: {e} ({rc}/5)")
        )
        if result is None:
            logger.error(f"Max retry fail to read '{key}'")
            return ""
        return result

    async def _write_cache_key(self, key: str, value: str) -> None:
        tmp_path = TEMP_JSON.with_suffix(".tmp")

        async def write_action():
            async with _refresh_lock:
                if not os.path.exists(TEMP_JSON):
                    logger.error(f"快取檔案不存在，無法Write '{key}' ")
                    return False
                async with aiofiles.open(TEMP_JSON, "rb") as f:
                    content = await f.read()
                data = orjson.loads(content)
                if 'cache_cookie' not in data:
                    logger.error("JSON 檔案結構錯誤：缺少 'cache_cookie' 鍵 ")
                    return False
                data['cache_cookie'][key] = value
                updated_content = orjson.dumps(data, option=orjson.OPT_INDENT_2)
                async with aiofiles.open(tmp_path, "wb") as f:
                    await f.write(updated_content)
                await aiofiles.os.replace(tmp_path, TEMP_JSON)
                return True

        result = await self._retry_with_action(
            write_action,
            lambda e, rc: logger.error(f"Write '{key}' 時發生錯誤：{e} ({rc}/5)")
        )

        if result is not True:
            logger.error(f"達到最大重試次數，Write '{key}' 失敗")
            raise Exception(f"無法更新 '{key}' 快取 ")

    async def read_bz_r(self) -> str:
        return await self._read_cache_key("bz_r")

    async def save_bz_r(self, bz_r: str) -> None:
        await self._write_cache_key("bz_r", bz_r)

    async def read_bz_a(self) -> str:
        return await self._read_cache_key("bz_a")

    async def save_bz_a(self, token: str) -> None:
        await self._write_cache_key("bz_a", token)

    async def read_pcid(self) -> str:
        return await self._read_cache_key("pcid")

    async def save_pcid(self, pcid: str) -> None:
        await self._write_cache_key("pcid", pcid)

    async def get_bz_r(self) -> str:
        try:
            bz_r1 = await self.read_bz_r()
            bz_r2 = await NetscapeCookieReader().get_cookie("bz_r")
            if len(bz_r1) > 79 and bz_r1 != bz_r2:
                if os.path.exists(TEMP_JSON):
                    os.remove(TEMP_JSON)
                    await Berriz_cookie().get_cookies()
                    return bz_r2
                else:
                    raise FileNotFoundError
            await self.save_bz_r(bz_r2)
            if not bz_r2:
                await Refresh_JWT(await self.session()).fsau4021()
            else:
                return bz_r2
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to load bz_r: {e}")
            raise

    async def get_default_cookies(self) -> dict:
        try:
            pcid = await self.read_pcid()
            if len(pcid) > 20:
                return {'pcid': pcid}
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
            await self.save_pcid(cookies.get('pcid', ''))
            return cookies.get('pcid', '')
        except (ValueError) as e:
            raise ValueError(e)

    async def get_initial_headers(self) -> dict:
        bz_r = await self.get_bz_r()
        if len(bz_r) < 80:
            return None
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
            "bz_r": bz_r,
        }
        return headers
    
    async def session(self):
        async with aiohttp.ClientSession() as session:
            return session

class Refresh_JWT:
    no_expires_log = False
    CU = CookieUtils()
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def refresh_token(self) -> str | None:
        """Refresh the JWT token and save it to bz_a"""
        url = "https://account.berriz.in/auth/v1/token:refresh?languageCode=en"
        headers = await Refresh_JWT.CU.get_initial_headers()
        json_data = {"clientId": "e8faf56c-575a-42d2-933d-7b2e279ad827"}
        if headers is not None:
            try:
                async with self.session.post(url, headers=headers, json=json_data) as resp:
                    data = await resp.json()
                if resp.status != 200:
                    if data['code'] == 'FS_AU4021':
                        LM = LoginManager()
                        if await LM.load_info() is True:
                            bz_a, bz_r = await LM.new_refresh_cookie()
                            if all([bz_a, bz_r]) is not None and await self.update_cookie_file(bz_a, bz_r) is True:
                                logger.info(f"{Color.fg('light_red')}Token refresh failed, try auto re-login {Color.fg('olive')}success!{Color.reset()}")
                            return True
                        else:
                            logger.info(f"{Color.fg('light_red')}Token refresh failed, try auto re-login stil {Color.fg('gold')}Fail{Color.reset()}")
                            return None
                access_token = data["data"]["accessToken"]
                try:
                    decoded = jwt.decode(access_token, options={"verify_signature": False})
                    exp_time = datetime.fromtimestamp(decoded["exp"]).strftime("%Y-%m-%d %H:%M:%S")
                    if Refresh_JWT.no_expires_log is False:
                        logger.info(f"{Color.fg('beige')}Token expires at {exp_time}{Color.reset()}")
                        Refresh_JWT.no_expires_log = True
                except Exception as e:
                    logger.warning(f"Failed to decode token: {e}")
                await Refresh_JWT.CU.save_bz_a(access_token)
                return access_token

            except Exception as e:
                logger.error(f"Token refresh error: {e}")
                return None
        else:
            raise ValueError('bz_r is None')
            

    async def fsau4021(self):
        LM = LoginManager()
        if await LM.load_info() is True:
            bz_a, bz_r = await LM.new_refresh_cookie()
            if all([bz_a, bz_r]) is not None and await self.update_cookie_file(bz_a, bz_r) is True:
                logger.info(f"{Color.fg('light_red')}Token refresh failed, try auto re-login {Color.fg('olive')}success!{Color.reset()}")
            return True
        else:
            logger.info(f"{Color.fg('light_red')}Token refresh failed, try auto re-login stil {Color.fg('gold')}Fail{Color.reset()}")
            return None

    async def update_cookie_file(self, bz_a_new: str, bz_r_new: str):
        updated_lines = []
        try:
            async with _refresh_lock:
                async with aiofiles.open(DEFAULT_COOKIE, "r", encoding="utf-8") as f:
                    async for line in f:
                        if line.startswith("# ") or not line.strip():
                            updated_lines.append(line)
                            continue

                        parts = line.strip().split("\t")
                        for i, part in enumerate(parts):
                            if part == "bz_a" and i + 1 < len(parts):
                                parts[i + 1] = bz_a_new
                            elif part == "bz_r" and i + 1 < len(parts):
                                parts[i + 1] = bz_r_new

                        updated_lines.append("\t".join(parts) + "\n")

                async with aiofiles.open(DEFAULT_COOKIE, "w", encoding="utf-8") as f:
                    await f.writelines(updated_lines)
                    
                return True
        except Exception as e:
            logger.error(f"Failed to update cookie file: {e}")
            return False
        
    async def my_state_test(self) -> None:
        """Test cookie validity by making a state request."""
        async with asyncio.TaskGroup() as tg:
            cookies_task = tg.create_task(Refresh_JWT.CU.get_default_cookies())
            bz_a_task = tg.create_task(Refresh_JWT.CU.read_bz_a())
            headers_task = tg.create_task(Refresh_JWT.CU.get_initial_headers())
        if headers is None:
            raise ValueError('bz_r is None')
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
        except Exception as e:
            print(data.text)
            logger.error(f"State test error: {e}")
            raise('Cookie test fail')

    async def refresh_and_test(self) -> str | None:
        """Refresh token and test cookie validity."""
        access_token = await self.refresh_token()
        if access_token:
            await self.my_state_test()
            return access_token
        else:
            logger.error("Initial token refresh failed")
            return False

    async def should_refresh(self) -> bool:
        retry_count = 0
        max_retries = 5
        refresh_time: Optional[str] = None

        while retry_count < max_retries:
            try:
                async with aiofiles.open(TEMP_JSON, mode="rb") as f:
                    content = await f.read()
                data = orjson.loads(content)
                
                refresh_time = data.get('cache_cookie', {}).get('refresh_time')
                if not refresh_time:
                    return True
                
                break
            except FileNotFoundError:
                logger.warning(f"快取檔案不存在：{TEMP_JSON}")
                return True
            except (orjson.JSONDecodeError, KeyError) as e:
                retry_count += 1
                logger.warning(f"檔案格式錯誤或缺少鍵：{e}({retry_count}/{max_retries})")
                await asyncio.sleep(1)
            except Exception as e:
                retry_count += 1
                logger.warning(f"讀取檔案時發生意外錯誤：{e}({retry_count}/{max_retries})")
                await asyncio.sleep(1)

        if retry_count == max_retries:
            logger.error("Max retry fail to read快取檔案")
            return True

        try:
            next_refresh = datetime.fromtimestamp(float(refresh_time))
            delta = (next_refresh - datetime.now()).total_seconds()
            return delta < 60
        except (TypeError, ValueError) as ve:
            logger.warning(f"時間格式無效：{ve}，強製刷新")
            return True

    async def write_next_refresh_time(self) -> None:
        next_time = datetime.now() + timedelta(minutes=50)

        retry_count = 0
        max_retries = 5

        while retry_count < max_retries:
            try:
                async with _refresh_lock:
                    if not os.path.exists(TEMP_JSON):
                        logger.error("快取檔案不存在，無法Write刷新時間")
                        raise FileNotFoundError

                    async with aiofiles.open(TEMP_JSON, 'rb') as f:
                        content = await f.read()

                    data = orjson.loads(content)

                    if 'cache_cookie' in data:
                        data['cache_cookie']['refresh_time'] = str(next_time.timestamp())
                    else:
                        logger.error("檔案結構錯誤：缺少 'cache_cookie' 鍵")
                        break

                    updated_content = orjson.dumps(data, option=orjson.OPT_INDENT_2)

                    async with aiofiles.open(TEMP_JSON, 'wb') as f:
                        await f.write(updated_content)
                    
                    if Refresh_JWT.no_expires_log:
                        logger.info(f"Next cookie refresh time: {next_time:%Y-%m-%d %H:%M:%S}")
                        Refresh_JWT.no_expires_log = False
                    break

            except Exception as e:
                retry_count += 1
                logger.error(f"Write下次刷新時間時發生錯誤：{e} ({retry_count}/{max_retries})")
                await asyncio.sleep(1)

        if retry_count == max_retries:
            logger.error("達到最大重試次數，Write下次刷新時間失敗")
            raise RuntimeError("達到最大重試次數，Write下次刷新時間失敗")

    async def main(self) -> None:
        """Main method to handle token refresh if needed."""
        
        if (os.path.exists(DEFAULT_COOKIE) and os.path.getsize(DEFAULT_COOKIE) > 0) is False:
            return
        if await self.should_refresh():
            if await self.refresh_and_test():
                asyncio.create_task(self.write_next_refresh_time())
                return True
            else:
                return False


class NetscapeCookieReader:
    """Class to read cookies from a Netscape format cookie file."""

    def __init__(self):
        self.file_path = Path(DEFAULT_COOKIE)

    async def cookies(self) -> Dict[str, str]:
        if not os.path.exists(self.file_path):
            os.makedirs(self.file_path.parent, exist_ok=True)
            return {}

        try:
            async with aiofiles.open(self.file_path, "r", encoding="utf-8") as f:
                lines = []
                async for line in f:
                    line = line.strip()
                    if line and not line.startswith("# "):
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
    CU = CookieUtils()
    _instance = None
    show_no_cookie_log = True
    _cookie_refresh_count = 0

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
            if await self.trigger_rwt() is False:
                return

            # 載入 cookies
            async with asyncio.TaskGroup() as tg:
                default_task = tg.create_task(Berriz_cookie.CU.get_default_cookies())
                bz_a_task = tg.create_task(Berriz_cookie.CU.read_bz_a())
                bz_r_task = tg.create_task(Berriz_cookie.CU.get_bz_r())

            self._cookies = default_task.result()
            self._cookies["bz_a"] = bz_a_task.result()
            self._cookies["bz_r"] = bz_r_task.result()
            await self.get_cookies()
            await self.check_cookie()
            logger.info(f"{Color.fg('chartreuse')}Cookies loaded: {Color.fg('dark_gray')}{list(self._cookies.values())}{Color.reset()}")
        except Exception as e:
            if Berriz_cookie.show_no_cookie_log:
                if not os.path.exists(DEFAULT_COOKIE):
                    logger.warning(f"{Color.fg('light_gray')}No cookie found, {Color.fg('pink')}request without cookies{Color.reset()}")
                Berriz_cookie.show_no_cookie_log = False
            self._cookies = {}
            
    async def get_cookies(self) -> dict:
        empty_cache_json = self.default_json()
        if not os.path.exists(DEFAULT_COOKIE):
            await self.create_empty_cookie()
        if not os.path.exists(TEMP_JSON):
            try:
                content_bytes = orjson.dumps(empty_cache_json, option=orjson.OPT_INDENT_2)
                async with aiofiles.open(TEMP_JSON, 'wb') as f:
                    await f.write(content_bytes)
            except Exception as e:
                logger.error(f"Write {TEMP_JSON} 檔案時發生錯誤：{e}")
                raise FileExistsError
        else:
            if not hasattr(self, "_cookies") or not self._cookies:
                retry_count = 0
                max_retries = 5

                while retry_count < max_retries:
                    try:
                        await self.load_cookies()
                        break 
                    except Exception as e:
                        retry_count += 1
                        logger.warning(f"載入 cookie 時發生錯誤：{e} ({retry_count}/{max_retries})")
                        await asyncio.sleep(1)

                if retry_count == max_retries:
                    logger.error("達到最大重試次數，無法載入 cookie")
                    return {}
            
            return self._cookies
    
    def default_json(self) -> dict:
        return {
            "cache_cookie": {
                "bz_a": "",
                "bz_r": "",
                "pcid": "",
                "refresh_time": 0
            }
        }

    async def check_cookie(self):
        if len(self._cookies.get('bz_a', '')) != 598:
            if not os.path.exists(TEMP_JSON):
                raise FileNotFoundError(f"Cache cookie json not found: {TEMP_JSON}")
            retry_count = 0
            max_retries = 5
            while retry_count < max_retries:
                try:
                    os.remove(TEMP_JSON)
                    break 
                except Exception as e:
                    retry_count += 1
                    logger.error(f"處理檔案時發生錯誤：{e} ({retry_count}/{max_retries})")
                    await asyncio.sleep(1)
            
            if retry_count == max_retries:
                raise Exception("無法處理cookie cache josn")
            else:
                if await self.trigger_rwt() is False:
                    return
                await self.load_cookies()
                
    async def trigger_rwt(self):
        # 觸發 token 重新整理
        async with aiohttp.ClientSession() as session:
            bool = await Refresh_JWT(session).main()
            Berriz_cookie._cookie_refresh_count +=1
            if bool is False:
                raise
    
    async def create_empty_cookie(self) -> None:
        cookie_text = textwrap.dedent("""\
        # Netscape HTTP Cookie File
        # http://curl.haxx.se/rfc/cookie_spec.html
        # This is a generated file!  Do not edit.

        .berriz.in\tTRUE\t/en\tFALSE\t0\t__T_\t1
        .berriz.in\tTRUE\t/en\tTRUE\t0\t__T_SECURE\t1
        berriz.in\tFALSE\t/\tFALSE\t1792088189\tapp_install_confirmed\tTRUE
        .berriz.in\tTRUE\t/\tTRUE\t0\tpacode\t'fanplatf::app:android:phone'
        .berriz.in\tTRUE\t/\tFALSE\t0\tNEXT_LOCALE\ten
        .berriz.in\tTRUE\t/\tFALSE\t0\t__T_\t1
        .berriz.in\tTRUE\t/\tTRUE\t0\t__T_SECURE\t1
        berriz.in\tFALSE\t/\tFALSE\t1792088189\tcookie_policy_confirmed\tTRUE
        .berriz.in\tTRUE\t/\tTRUE\t0\tpcid\tsPj0iNAHjd7KzbDEBsBUB
        berriz.in\tFALSE\t/\tFALSE\t0\tNEXT_LOCALE\ten
        .berriz.in\tTRUE\t/\tTRUE\t0\tbz_r\t25565
        .berriz.in\tTRUE\t/\tTRUE\t0\tbz_a\t25565
        berriz.in\tFALSE\t/\tFALSE\t1757531775\tauth_status\tauthenticated
        """)

        async with aiofiles.open(DEFAULT_COOKIE, "w", encoding="utf-8") as f:
            await f.write(cookie_text)
