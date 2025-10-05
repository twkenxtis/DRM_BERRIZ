import asyncio
import os
from datetime import datetime, timedelta
import sys
import base64
import json
import uuid
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from static.parameter import paramstore
from static.route import Route

import jwt
import httpx
import aiofiles
from aiofiles import os as aioos
import orjson

from static.color import Color
from lib.account.login import LoginManager
from unit.__init__ import USERAGENT
from unit.handle.handle_log import setup_logging

route = Route()
DEFAULT_COOKIE: Path = route.default_cookie
TEMP_JSON: Path = route.temp_cookie
file_lock: asyncio.Lock = asyncio.Lock()


logger = setup_logging('cookies', 'firebrick')


class CookieUtils:
    BASE_URL: str = "https://berriz.in"
    REQUIRED_COOKIES: List[str] = ["pcid"]
    
    def __init__(self):
        pass

    async def _retry_with_action(self, action, error_log_cb, max_retries: int = 5) -> Optional[Any]:
        retry_count: int = 0
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
        async with file_lock:
            if not os.path.exists(TEMP_JSON):
                return ""
            async with aiofiles.open(TEMP_JSON, "r") as f:
                content: str = await f.read()
            data: Dict[str, Any] = orjson.loads(content)
            return data.get('cache_cookie', {}).get(key, "")

    async def _write_cache_key(self, key: str, value: str) -> bool:
        tmp_path: Path = TEMP_JSON.with_suffix(".tmp")
        async with file_lock:
            if not os.path.exists(TEMP_JSON):
                logger.error(f"快取檔案不存在，無法Write '{key}' ")
                return False
            async with aiofiles.open(TEMP_JSON, "r") as f:
                content: str = await f.read()
            data: Dict[str, Any] = orjson.loads(content)
            if 'cache_cookie' not in data:
                logger.error("JSON 檔案結構錯誤：缺少 'cache_cookie' 鍵 ")
                return False
            data['cache_cookie'][key] = value
            updated_content: bytes = orjson.dumps(data, option=orjson.OPT_INDENT_2)
            async with aiofiles.open(tmp_path, "wb") as f:
                await f.write(updated_content)
            await aioos.replace(tmp_path, TEMP_JSON)
            return True

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
            bz_r1: str = await self.read_bz_r()
            bz_r2: str = await NetscapeCookieReader().get_cookie("bz_r")
            
            # default bz_r 改變 換帳號
            if len(bz_r1) > 79 and bz_r1 != bz_r2:
                if os.path.exists(TEMP_JSON):
                    logger.info('Account change, reset temp.json file')
                    async with aiofiles.open(TEMP_JSON, 'w') as f:
                        await f.write("")
                        await Berriz_cookie.create_temp_json()
                        await self.save_bz_r(bz_r2)
                        await self.save_bz_a('eyJpc3MiOiJhY2NvdW50LmJlcnJpei5pbiIsImlkcE5hbWUiOiJHT09HTEUifQ')
                        await self.get_default_cookies()
                        return bz_r2
                else:
                    raise FileNotFoundError
            
            # default.txt 讀取失敗 沒有bz_r 嘗試用fsau4021 觸發login.py 來刷新default.txt
            if not bz_r2:
                await Refresh_JWT().fsau4021()
            else:
                # 讀取到default.txt 內的 bz_r 寫入到json並返回作為請求結果
                await self.save_bz_r(bz_r2)
                return bz_r2
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Failed to load bz_r: {e}")
            raise FileExistsError("Failed to load bz_r")

    async def get_default_cookies(self) -> Dict[str, str] | str:
        try:
            pcid: str = await self.read_pcid()
            if len(pcid) > 20:
                return {'pcid': pcid}
            cookie_reader: NetscapeCookieReader = NetscapeCookieReader()
            cookies: Dict[str, str] = {
                name: await cookie_reader.get_cookie(name)
                for name in CookieUtils.REQUIRED_COOKIES
                if await cookie_reader.get_cookie(name)
            }
            if len(cookies) != len(CookieUtils.REQUIRED_COOKIES):
                missing: List[str] = [
                    name for name in CookieUtils.REQUIRED_COOKIES if name not in cookies
                ]
                raise ValueError(f"Missing required cookies in {DEFAULT_COOKIE}: {missing}")
            await self.save_pcid(cookies.get('pcid', ''))
            return cookies.get('pcid', '')
        except (ValueError) as e:
            raise ValueError(e)

    async def get_initial_headers(self) -> Dict[str, str]:
        bz_r: str = await self.get_bz_r()
        headers: Dict[str, str] = {
            "User-Agent": f"{USERAGENT}",
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


class Refresh_JWT:
    no_expires_log: bool = False
    CU: CookieUtils = CookieUtils()
    show_no_passwd_log: bool = True
    fsau4021_log: bool = True
    no_LOGIN_log: bool = True

    def __init__(self):
        pass

    async def refresh_token(self) -> Optional[str]:
        """Refresh the JWT token and save it to bz_a"""
        url: str = "https://account.berriz.in/auth/v1/token:refresh?languageCode=en"
        headers: Dict[str, str] = await Refresh_JWT.CU.get_initial_headers()
        json_data: Dict[str, str] = {"clientId": "e8faf56c-575a-42d2-933d-7b2e279ad827"}
        data: httpx.Response = await _send_post_http(url, json_data, headers)
        if data['code'] == 'FS_AU4021': 
            if Refresh_JWT.fsau4021_log == True:
                Refresh_JWT.fsau4021_log = False
                logger.warning(f"{data['code']} - {data['message']}")
            await self.fsau4021()
        access_token: str = data["data"]["accessToken"]
        try:
            decoded: Dict[str, Any] = jwt.decode(access_token, options={"verify_signature": False})
            exp_time: str = datetime.fromtimestamp(decoded["exp"]).strftime("%Y-%m-%d %H:%M:%S")
            if Refresh_JWT.no_expires_log is False:
                logger.info(f"{Color.fg('beige')}Token expires at {exp_time}{Color.reset()}")
                Refresh_JWT.no_expires_log = True
        except Exception as e:
            logger.warning(f"Failed to decode token: {e}")
        await Refresh_JWT.CU.save_bz_a(access_token)
        return access_token

    async def fsau4021(self) -> Optional[bool]:
        if paramstore.get('no_cookie') is not True:
            LM: LoginManager = LoginManager()
            try:
                if await LM.load_info() is True:
                    bz_a, bz_r = await LM.new_refresh_cookie()
                    if all([bz_a, bz_r]) is not None and await self.update_cookie_file(bz_a, bz_r) is True:
                        if await self.update_json_file(bz_a, bz_r) is True:
                            logger.info(
                                f"{Color.fg('light_gray')}Token refresh failed, "
                                f"{Color.fg('light_red')}try auto re-login {Color.fg('olive')}success!{Color.reset()}"
                            )
                            return True
                        else:
                            pass
                else:
                    logger.info(f"{Color.fg('light_gray')}Token refresh failed, "
                                f"{Color.fg('light_red')}try auto re-login stil {Color.fg('gold')}Fail{Color.reset()}")
                    sys.exit(1)
            except Exception as e:
                if Refresh_JWT.no_LOGIN_log == True:
                    Refresh_JWT.no_LOGIN_log = False
                    logger.error(f"[Login] {e}")
        return None

    async def update_cookie_file(self, bz_a_new: str, bz_r_new: str) -> bool:
        updated_lines: List[str] = []
        try:
            async with file_lock:
                async with aiofiles.open(DEFAULT_COOKIE, "r", encoding="utf-8") as f:
                    async for line in f:
                        if line.startswith("# ") or not line.strip():
                            updated_lines.append(line)
                            continue

                        parts: List[str] = line.strip().split("\t")
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
        
    async def update_json_file(self, bz_a_new: str, bz_r_new: str) -> bool:
        try:
            async with aiofiles.open(TEMP_JSON, 'r') as f:
                content: str = await f.read()
            data: Dict[str, Any] = orjson.loads(content)

            data['cache_cookie']['bz_a'] = bz_a_new
            data['cache_cookie']['bz_r'] = bz_r_new

            updated_content = orjson.dumps(data).decode()

            async with aiofiles.open(TEMP_JSON, 'w') as f:
                await f.write(updated_content)
            return True
        except (FileNotFoundError, orjson.JSONDecodeError) as e:
            logger.error(f"Failed to read temp.json file: {e}")
            return False
        except Exception as e:
            logger.error(e)
            return False
        
    async def refresh_and_test(self) -> Optional[str]:
        """Refresh token and test cookie validity."""
        access_token: Optional[str] = await self.refresh_token()
        if access_token:
            return access_token
        else:
            logger.error("Initial token refresh failed")
            return None

    async def should_refresh(self) -> bool:
        retry_count: int = 0
        max_retries: int = 3
        refresh_time: Optional[str] = None

        while retry_count < max_retries:
            try:
                async with file_lock:
                    async with aiofiles.open(TEMP_JSON, mode="r") as f:
                        content: str = await f.read()
                    data: Dict[str, Any] = orjson.loads(content)
                    
                    refresh_time = data.get('cache_cookie', {}).get('refresh_time')
                    if not refresh_time:
                        return True
                    break
            except FileNotFoundError:
                logger.warning(f"快取檔案不存在：{TEMP_JSON}")
                return False
            except (orjson.JSONDecodeError, KeyError) as e:
                retry_count += 1
                if isinstance(e, orjson.JSONDecodeError) and e.lineno == 1 and e.colno == 1:
                    await Berriz_cookie.create_temp_json()
                    logger.info(
                        f"{Color.fg('light_amber')}Reset {Color.fg('light_gray')}{TEMP_JSON} {Color.fg('light_amber')}"
                        f"to initialization complete{Color.reset()}"
                        )
                else:
                    logger.warning(f"檔案格式錯誤或缺少鍵：{e} ({retry_count}/{max_retries})")
                await asyncio.sleep(1)
            except Exception as e:
                retry_count += 1
                logger.warning(f"讀取檔案時發生意外錯誤：{e}({retry_count}/{max_retries})")
                await asyncio.sleep(1)

        if retry_count == max_retries:
            logger.error("Max retry fail to read 快取檔案")
            sys.exit(1)

        try:
            next_refresh: datetime = datetime.fromtimestamp(float(refresh_time))
            delta: float = (next_refresh - datetime.now()).total_seconds()
            return delta < 60
        except (TypeError, ValueError) as ve:
            logger.warning(f"時間格式無效：{ve}，強製刷新")
            return True


    async def write_next_refresh_time(self) -> None:
        next_time: datetime = datetime.now() + timedelta(minutes=50)

        retry_count: int = 0
        max_retries: int = 5

        while retry_count < max_retries:
            try:
                async with file_lock:
                    if not os.path.exists(TEMP_JSON):
                        logger.error("快取檔案不存在，無法Write刷新時間")
                        raise FileNotFoundError

                    async with aiofiles.open(TEMP_JSON, 'r') as f:
                        content: str = await f.read()

                    data: Dict[str, Any] = orjson.loads(content)

                    if 'cache_cookie' in data:
                        data['cache_cookie']['refresh_time'] = str(next_time.timestamp())
                    else:
                        logger.error("檔案結構錯誤：缺少 'cache_cookie' 鍵")
                        break

                    updated_content: bytes = orjson.dumps(data, option=orjson.OPT_INDENT_2)

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

    async def main(self) -> Optional[bool]:
        """Main method to handle token refresh if needed."""
        if (os.path.exists(DEFAULT_COOKIE) and os.path.getsize(DEFAULT_COOKIE) > 0) is False:
            return await Refresh_JWT().fsau4021()
        if await self.should_refresh():
            k: Optional[str] = await self.refresh_and_test()
            if k:
                asyncio.create_task(self.write_next_refresh_time())
                return True
            return False
        return None


class NetscapeCookieReader:
    """Class to read cookies from a Netscape format cookie file."""
    def __init__(self):
        self.file_path: Path = Path(DEFAULT_COOKIE)

    async def cookies(self) -> Dict[str, str]:
        if not os.path.exists(self.file_path):
            os.makedirs(self.file_path.parent, exist_ok=True)
            return {}

        try:
            async with aiofiles.open(self.file_path, "r", encoding="utf-8") as f:
                lines: List[str] = []
                async for line in f:
                    line = line.strip()
                    if line and not line.startswith("# "):
                        lines.append(line)
        except Exception as e:
            logger.error(f"Failed to read cookie file: {e}")
            return {}

        cookies_dict: Dict[str, str] = {}
        for line in lines:
            parts: List[str] = line.split("\t")
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
        cookies: Dict[str, str] = await self.cookies()
        return cookies.get(name, "")


class Berriz_cookie:
    CU: CookieUtils = CookieUtils()
    
    _instance: Optional["Berriz_cookie"] = None
    show_no_cookie_log: bool = True
    count_rwt: int = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_cookies"):
            self._cookies: Dict[str, Any] = {}
        self.rwt: Optional[bool] = None

    async def load_cookies(self) -> None:
        """Load cookies from disk."""
        self._cookies = {}
        self.rwt = await self.trigger_rwt()
        try:
            # 觸發 token 重新整理
            if self.rwt is False:
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
    
    # 進入點 
    async def get_cookies(self) -> Dict[str, Any]:
        if paramstore.get('no_cookie') is not True:
            if not os.path.exists(DEFAULT_COOKIE):
                await self.create_empty_cookie()
            if not os.path.exists(TEMP_JSON):
                await Berriz_cookie.create_temp_json()
            else:
                c: Dict[str, Any] = await self.get_valid_cookie()
                return c
        else:
            # no cookie
            return {}
        return {}

    async def get_valid_cookie(self) -> Dict[str, Any]:
        try:
            for attempt in range(4):
                cookie: Dict[str, Any] = await self.check_hasattr()
                if cookie not in (None, {}):
                    return cookie
            raise RuntimeError("Fail to get cookie")
        except Exception as e:
            logger.critical(e)
            sys.exit(1)

    @staticmethod
    def default_json() -> Dict[str, Any]:
        return {
            "cache_cookie": {
                "bz_a": "",
                "bz_r": "",
                "pcid": "ijJSuDryGDdgE-JmRUhAK",
                "refresh_time": 0
            }
        }

    async def check_cookie(self) -> None:
        bz_a: str = self._cookies.get('bz_a', '')
        try:
            header_b64, payload_b64, signature_b64 = bz_a.split('.')
            payload: Dict[str, Any] = json.loads(self.b64url_decode(payload_b64))
            sub: Optional[str] = payload.get("sub")
            if not sub:
                logger.error("JWT Payload had not 'sub'?")
                return
            try:
                uuid.UUID(sub)
            except ValueError:
                logger.error(f"UUID invaild：{sub}")
                await self.jwt_error_handle()
        except Exception as e:
            logger.error(f"JWT Token bz_a Structural error or parsing failure：{e}")
            await self.get_cookies()
            await self.jwt_error_handle()

    async def jwt_error_handle(self) -> None:
        if not os.path.exists(TEMP_JSON):
            raise FileNotFoundError(f"Cache cookie json not found: {TEMP_JSON}")
        retry_count: int = 0
        max_retries: int = 1
        while retry_count < max_retries:
            try:
                os.remove(TEMP_JSON)
                break 
            except Exception as e:
                retry_count += 1
                logger.error(f"處理got error：{e} ({retry_count}/{max_retries})")
                await asyncio.sleep(1)
        
        if retry_count == max_retries:
            raise Exception("無法處理cookie cache josn")
        else:
            await Refresh_JWT().refresh_token()
            await self.get_cookies()

    def b64url_decode(self, data: str) -> bytes:
        padding: str = '=' * (-len(data) % 4)
        return base64.urlsafe_b64decode(data + padding)
                
    async def trigger_rwt(self) -> Optional[bool]:
        if paramstore.get('no_cookie') is not True:
            # 觸發 token 重新整理
            if Berriz_cookie.count_rwt < 2:
                Berriz_cookie.count_rwt +=1
                bool_result: Optional[bool] = await Refresh_JWT().main()
                return bool_result
        else:
            return False
        return None
    
    async def create_empty_cookie(self) -> None:
        os.makedirs(Path(DEFAULT_COOKIE).parent, exist_ok=True)
        cookie_text: str = textwrap.dedent("""\
        # Netscape HTTP Cookie File
        # [http://curl.haxx.se/rfc/cookie_spec.html](http://curl.haxx.se/rfc/cookie_spec.html)
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
        .berriz.in\tTRUE\t/\tTRUE\t0\tbz_r\tNOCOOKIE_BZ_R
        .berriz.in\tTRUE\t/\tTRUE\t0\tbz_a\tNOCOOKIE_BZ_A
        berriz.in\tFALSE\t/\tFALSE\t1757531775\tauth_status\tauthenticated
        """)

        async with aiofiles.open(DEFAULT_COOKIE, "w", encoding="utf-8") as f:
            await f.write(cookie_text)

    async def check_cache_json_info(self) -> bool:
        bz_a: str = await Berriz_cookie.CU._read_cache_key('bz_a')
        bz_r: str = await Berriz_cookie.CU._read_cache_key('bz_r')
        pcid: str = await Berriz_cookie.CU._read_cache_key('pcid')

        # 判斷三個都是 str 且長度 > 0
        if all(isinstance(v, str) and len(v) > 0 for v in (bz_a, bz_r, pcid)):
            return True
        return False

    @staticmethod
    async def create_temp_json() -> None:
        try:
            content_bytes: bytes = orjson.dumps(Berriz_cookie.default_json(), option=orjson.OPT_INDENT_2)
            async with aiofiles.open(TEMP_JSON, 'wb') as f:
                await f.write(content_bytes)
        except Exception as e:
            logger.error(f"Write {TEMP_JSON} got error：{e}")
            raise FileExistsError
        
    async def check_hasattr(self) -> Dict[str, Any]:
        if not hasattr(self, "_cookies") or not self._cookies:
            retry_count: int = 0
            max_retries: int = 7

            while retry_count < max_retries:
                try:
                    await self.load_cookies()
                    break 
                except Exception as e:
                    retry_count += 1
                    logger.warning(f"Load cookie error：{e} ({retry_count}/{max_retries})")
                    await asyncio.sleep(1)

            if retry_count == max_retries:
                logger.error("Max retry fail to load cookie")
                return {}
        
        return self._cookies


async def _send_post_http(url: str, json_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Optional[httpx.Response]:
    try:
        params: Dict[str, str] = {"languageCode": 'en'}
        async with httpx.AsyncClient(http2=True, timeout=7, verify=True) as client:
            response: httpx.Response = await client.post(
                url,
                params=params,
                cookies={},
                headers=headers,
                json=json_data,
            )
        if response.status_code not in range(200, 300):
            logger.error(f"HTTP error for {url}: {response.status_code}")
        return response.json()
    except httpx.ConnectTimeout:
        logger.warning(f"{Color.fg('light_gray')}Request timeout:{Color.reset()} {Color.fg('periwinkle')}{url}{Color.reset()}")
