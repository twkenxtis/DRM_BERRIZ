import asyncio
import base64
from datetime import datetime, timedelta
import hashlib
import re
import secrets
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple, Union
from urllib.parse import parse_qs, urlparse, ParseResult

import aiofiles
import httpx
import yaml

from lib.account.unban_account import unban_main
from static.color import Color
from static.route import Route
from unit.__init__ import USERAGENT
from unit.handle.handle_log import setup_logging


logger = setup_logging('login', 'flamingo_pink')


YAML_PATH: Path = Route().YAML_path
PCID = 'ZOqaqhZDP51ktDutTpV_F'

class AuthManager:
    # 單例管理：確保全局只有一個 AuthManager 實例
    _instance: Optional["AuthManager"] = None

    # 動態建立屬性於 create()/from_dict() 中
    code_verifier: str
    challenge: str
    state: str
    created_at: datetime
    expires_at: datetime

    @classmethod
    def create(cls, challenge_method: str = 'S256') -> "AuthManager":
        """
        創建新的認證管理器實例，對應 JS 端 a.R.create() 的行為
        - 生成 code_verifier、code_challenge、state
        - 設定實例的有效期限（10 分鐘）
        """
        instance: "AuthManager" = cls()
        # 1. 生成符合 JS 實作的 21 字符 code_verifier
        instance.code_verifier = cls._generate_code_verifier()
        # 2. 根據 code_verifier 生成相同格式的 code_challenge
        instance.challenge = cls._generate_challenge(
            instance.code_verifier,
            challenge_method
        )
        # 3. 生成防 CSRF 的 state（21 字符）
        instance.state = cls._generate_state()
        # 實例時間標記與過期時間
        instance.created_at = datetime.now()
        instance.expires_at = instance.created_at + timedelta(minutes=10)

        # 保存單例，供後續 get() 調用
        cls._instance = instance
        return instance

    @classmethod
    def get(cls) -> Optional["AuthManager"]:
        """
        獲取現有的認證管理器實例，對應 JS 端 a.R.get() 的行為
        只有在實例存在且未過期時才返回，否則返回 None
        """
        inst: Optional["AuthManager"] = cls._instance
        if inst and inst._is_valid():
            return inst
        return None

    @classmethod
    def _generate_code_verifier(cls) -> str:
        """
        生成 PKCE code_verifier - 匹配 JS 端 21 字符長度
        1. 16 字節隨機數據
        2. Base64-URL 編碼
        3. 移除 '=' 填充
        4. 截斷至 21 字符
        """
        random_bytes: bytes = secrets.token_bytes(16)
        verifier: str = base64.urlsafe_b64encode(random_bytes).decode()
        verifier = verifier.replace('=', '')  # 去掉填充符
        return verifier[:21]                 # 確保長度

    @classmethod
    def _generate_challenge(cls, code_verifier: str, method: str = 'S256') -> str:
        """
        生成 PKCE code_challenge，對應 JS 端的行為
        - S256: 對 code_verifier 做 SHA256，輸出十六進製字串（64 字符）
        - plain: 直接返回 code_verifier
        """
        if method == 'S256':
            digest: bytes = hashlib.sha256(code_verifier.encode()).digest()
            # JS 端使用十六進製輸出，而非 Base64
            challenge: str = digest.hex()
            return challenge
        elif method == 'plain':
            return code_verifier
        else:
            raise ValueError(f"Unsupported challenge method: {method}")

    @classmethod
    def _generate_state(cls) -> str:
        """
        生成防 CSRF 的 state，行為與 code_verifier 相同
        - 16 字節隨機數據
        - Base64-URL 編碼
        - 去除 '=' 填充
        - 截斷至 21 字符
        """
        random_bytes: bytes = secrets.token_bytes(16)
        state: str = base64.urlsafe_b64encode(random_bytes).decode().replace('=', '')
        return state[:21]

    def _is_valid(self) -> bool:
        """檢查單例實例是否在有效期限內"""
        return datetime.now() < self.expires_at

    def to_dict(self) -> Dict[str, str]:
        """
        轉換實例為字典，用於持久化存儲
        包含 code_verifier、challenge、state 及時間資訊
        """
        return {
            'code_verifier': self.code_verifier,
            'challenge': self.challenge,
            'state': self.state,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "AuthManager":
        """
        從字典恢復 AuthManager 實例，對應 JS 端 a.R 從 localStorage 讀取行為
        """
        instance: "AuthManager" = cls()
        instance.code_verifier = data['code_verifier']
        instance.challenge = data['challenge']
        instance.state = data['state']
        instance.created_at = datetime.fromisoformat(data['created_at'])
        instance.expires_at = datetime.fromisoformat(data['expires_at'])
        cls._instance = instance
        return instance

    def get_authorization_url(
        self,
        client_id: str,
        redirect_uri: str,
        post_redirect_uri: str = '/',
        language_code: str = 'en'
    ) -> str:
        """
        生成 OAuth 授權請求的 URL，對應 JS 端 authorize:init 參數
        """
        base_url: str = "https://account.berriz.in/auth/v1/authorize:init"
        params: Dict[str, str] = {
            'clientId': client_id,
            'codeChallenge': self.challenge,
            'challengeMethod': 'S256',
            'redirectUri': redirect_uri,
            'postRedirectUri': post_redirect_uri,
            'state': self.state,
            'languageCode': language_code,
        }
        # httpx.QueryParams 自動處理 URL 編碼
        return f"{base_url}?{httpx.QueryParams(params)}"


# 獲取或創建認證管理器 - 對應 let d = a.R.get() ?? a.R.create()
def create_auth_request(
    password: str,
    authorize_key: str,
    email: str,
    clientid: str,
    challenge_method: str = 'S256',
    post_redirect_uri: Optional[str] = None
) -> Dict[str, Any]:
    """
    複製原始 JavaScript 功能的完整實現
    - 先嘗試從單例 get() 拿取，否則 create() 新實例
    - 構建 authenticate 所需的請求體
    """
    auth_manager: AuthManager = AuthManager.get() or AuthManager.create(challenge_method)

    request_data: Dict[str, Any] = {
        'password': password,
        'clientId': clientid,
        'authorizeKey': authorize_key,
        'challengeMethod': challenge_method,
        'codeChallenge': auth_manager.challenge,
        'state': auth_manager.state,
        'email': email,
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': post_redirect_uri
    }
    # 移除 None 項，保持請求參數乾淨
    request_data = {k: v for k, v in request_data.items() if v is not None}
    return {
        'auth_manager': auth_manager,  # 保存實例用於後續 token 發行
        'request_data': request_data,
        'request_config': {
            'url': 'https://account.berriz.in/auth/v1/authenticate',
            'method': 'POST',
            'headers': {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            'data': request_data
        }
    }


class Request:
    cookies: Dict[str, str] = {
        'pcid': str(PCID),
        'pacode': 'fanplatf::app:android:phone',
        '__T_': '1',
        '__T_SECURE': '1',
    }

    headers: Dict[str, str] = {
        'User-Agent': f"{USERAGENT}",
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Referer': 'https://berriz.in/',
        'Origin': 'https://berriz.in',
        'Connection': 'keep-alive',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }

    async def post(self, url: str, p: Dict[str, Any], json_data: Dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            attempt: int = 0
            while attempt < 3:
                try:
                    response: httpx.Response = await client.post(
                        url,
                        params=p,
                        cookies=Request.cookies,
                        headers=Request.headers,
                        json=json_data,
                    )
                    if response.status_code <= 400:
                        raise httpx.HTTPStatusError(
                            f"Retryable server error: {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response
                except httpx.HTTPStatusError as e:
                    if e.response is not None and e.response.status_code <= 400:
                        logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{3}")
                    else:
                        logger.error(f"HTTP error for {url}: {e} {Color.bg('gold')}{response}{Color.reset()}")
                        return None
                attempt += 1
                sleep: float = min(2.0, 0.5 * (2 ** attempt))
                await asyncio.sleep(sleep)
        logger.error(f"Retry exceeded for {url}")
        return None


    async def get(self, url: str, p: Dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            attempt: int = 0
            while attempt < 3:
                try:
                    response: httpx.Response = await client.get(
                        url,
                        params=p,
                        cookies=Request.cookies,
                        headers=Request.headers,
                    )
                    if response.status_code <= 400:
                        raise httpx.HTTPStatusError(
                            f"Retryable server error: {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response
                except httpx.HTTPStatusError as e:
                    if e.response is not None and e.response.status_code <= 400:
                        logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{3}")
                    else:
                        logger.error(f"HTTP error for {url}: {e} {Color.bg('gold')}{response}{Color.reset()}")
                        return None
                attempt += 1
                sleep: float = min(2.0, 0.5 * (2 ** attempt))
                await asyncio.sleep(sleep)
        logger.error(f"Retry exceeded for {url}")
        return None


R: Request = Request()


async def vaild_email(ENMAIL: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        'email': ENMAIL,
    }
    url: str = 'https://account.berriz.in/member/v1/members:email-exists'
    response: httpx.Response = await R.get(url, params)
    return response.json()


async def authorizeKey(challenge: str, state: str, CLIENTID: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        'clientId': CLIENTID,
        'codeChallenge': challenge,
        'challengeMethod': 'S256',
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/',
        'state': state,
        'languageCode': 'en',
    }
    url: str = 'https://account.berriz.in/auth/v1/authorize:init'
    response: httpx.Response = await R.get(url, params)
    return response.json()


async def get_code(CLIENTID: str, challenge: str, state_csrf: str, authenticatekey: str) -> Optional[str]:
    params: Dict[str, Any] = {
        'clientId': CLIENTID,
        'codeChallenge': challenge,
        'challengeMethod': 'S256',
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/',
        'state': state_csrf,
        'authenticateKey': authenticatekey,
    }
    url: str = 'https://account.berriz.in/auth/v1/authorize'
    response: httpx.Response = await R.get(url, params)
    location_header: Optional[str] = response.headers.get('location')
    return location_header


async def authenticateKey(authorizeKey: str, challenge: str, state_csrf: str, ENMAIL: str, PASSWORD: str, CLIENTID: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        'languageCode': 'en',
    }

    json_data: Dict[str, Any] = {
        'password': PASSWORD,
        'clientId': CLIENTID,
        'authorizeKey': authorizeKey,
        'challengeMethod': 'S256',
        'codeChallenge': challenge,
        'state': state_csrf,
        'email': ENMAIL,
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/',
    }
    url: str = 'https://account.berriz.in/auth/v1/authenticate'
    response: httpx.Response = await R.post(url, params, json_data)
    return response.json()


async def token_issue(CLIENTID: str, code_value: str, code_verifier: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        'languageCode': 'en',
    }

    json_data: Dict[str, Any] = {
        'code': code_value,
        'clientId': CLIENTID,
        'codeVerifier': code_verifier,
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/',
    }
    url: str = 'https://account.berriz.in/auth/v1/token:issue'
    response: httpx.Response = await R.post(url, params, json_data)
    return response.json()


def extract_url_params(url_string: str) -> Tuple[Optional[str], Optional[str]]:
    """
    從網址字串中解析並提取 'code' 和 'postRedirectUri' 參數
    """
    parsed_url: ParseResult = urlparse(url_string)
    query_params: Dict[str, List[str]] = parse_qs(parsed_url.query)
    code: Optional[str] = query_params.get('code', [None])[0]
    postRedirectUri: Optional[str] = query_params.get('postRedirectUri', [None])[0]
    return code, postRedirectUri


class LoginManager:
    EMAIL_REGEX: "re.Pattern[str]" = re.compile(r".+@.+\..+")
    CLIENTID: str = "e8faf56c-575a-42d2-933d-7b2e279ad827"

    def __init__(self):
        self.account: Optional[str] = None
        self.password: Optional[str] = None
        self.bz_a: Optional[str] = None
        self.bz_r: Optional[str] = None

    async def load_info(self) -> bool:
        if not YAML_PATH.exists():
            raise FileNotFoundError(f"YAML file not found: {YAML_PATH}")

        async with aiofiles.open(YAML_PATH, "r", encoding="utf-8") as f:
            raw: str = await f.read()
            data: Dict[str, Dict[str, str]] = yaml.safe_load(raw)
        try:
            for entry in data.values():
                acct: str = entry.get("account", "").strip().lower()
                pwd: str = entry.get("password", "").strip()
                if LoginManager.EMAIL_REGEX.match(acct) and len(pwd) > 7:
                    self.account = acct
                    self.password = pwd
                    return await self.run_login()
            raise ValueError('No valid account/password in YAML')
        except ValueError as e:
            logger.error(f"{e} - Fail to use account password re-login in")
            

    async def run_login(self) -> bool:
        # 校驗郵箱
        ok: bool = await self.check_mail()
        if not ok:
            return False

        # PKCE 請求
        challenge, state, verifier = self.get_auth_request()
        if not all((self.check_challenge(challenge),
                    self.check_state(state),
                    self.check_code_verifier(verifier))):
            return False

        # authorizeKey
        authkey_data: Dict[str, Any] = await authorizeKey(challenge, state, self.CLIENTID)
        authkey: str = self.check_authkey(authkey_data)

        # authenticateKey
        ak_data: Dict[str, Any] = await authenticateKey(
            authkey, challenge, state,
            self.account, self.password, self.CLIENTID  # type: ignore[arg-type]
        )
        authk: str = await self.check_authenticatekey(ak_data)
        # 拿到重定向 URL 回應header裡面有資料
        location: Optional[str] = await get_code(self.CLIENTID, challenge, state, authk)
        if not self.check_location_url(location or ""):
            return False

        # 提取 code from 回應header的資料
        code, _ = extract_url_params(location or "")
        if not self.check_code_value(code or ""):
            return False

        # PKCE 發起請求 set-cookie 取得
        tokens: Dict[str, Any] = await token_issue(self.CLIENTID, code or "", verifier)
        if not self.check_bz_a_bz_r(tokens):
            return False

        # 確認 bz_a bz_r 返回 True 到 cookie.py 完成 Login
        pair: Optional[Tuple[str, str]] = self.sort_bz_a_bz_r(tokens)
        if not pair:
            return False

        self.bz_a, self.bz_r = pair
        return True

    async def check_mail(self) -> bool:
        info: Dict[str, Any] = await vaild_email(self.account or "")
        if info["code"] == "0000":
            if not info["data"]["exists"]:
                raise ValueError(f"Account does not exist: {self.account}")
            return True
        if info["code"] == "FS_ME2120":
            return False
        raise Exception("Unknown error at check_mail")

    def get_auth_request(self) -> Tuple[str, str, str]:
        res: Dict[str, Any] = create_auth_request(
            password=self.password or "",
            authorize_key='',
            email=self.account or "",
            challenge_method="S256",
            post_redirect_uri="https://berriz.in/auth/token&postRedirectUri=/",
            clientid=self.CLIENTID,
        )
        m: AuthManager = res["auth_manager"]
        return m.challenge, m.state, m.code_verifier

    def check_authkey(self, data: Dict[str, Any]) -> str:
        if data["code"] != "0000":
            raise ValueError(f"Auth key error: {data}")
        key: str = data["data"]["authorizeKey"]
        if not key or len(key) != 30:
            raise ValueError(f"Bad authorizeKey: {key}")
        return key

    async def check_authenticatekey(self, data: Dict[str, Any]) -> str:
        if data["code"] != "0000":
            if data["code"] == 'FS_AU4030':
                logger.info(f"{Color.fg('gold')}{data['message']}{Color.reset()}")
                """{'code': 'FS_AU4030', 'message': 'Unfortunately, 
                your account has been suspended. Additional authentication is required to re-enable.'}"""
                if await unban_main(self.account or "") is True:
                    logger.info(f"{Color.fg('light_green')}Account unlocked ! Try login now{Color.reset()}")
                    await self.run_login()
            else:
                raise ValueError(f"Authenticate key error: {data}")
        key: str = data["data"]["authenticateKey"]
        if not key or len(key) != 30:
            raise ValueError(f"Bad authenticateKey: {key}")
        return key

    def check_challenge(self, ch: str) -> bool:
        return len(ch) == 64

    def check_state(self, st: str) -> bool:
        return len(st) == 21

    def check_code_verifier(self, cv: str) -> bool:
        return len(cv) == 21

    def check_location_url(self, url: str) -> bool:
        return (
            url.startswith("https://berriz.in/auth/token?code=")
            and len(url) >= 110
        )

    def check_code_value(self, code: str) -> bool:
        return code is not None and len(code) == 30

    def check_bz_a_bz_r(self, data: Dict[str, Any]) -> bool:
        return data.get("code") == "0000" and isinstance(data.get("data"), dict)

    def sort_bz_a_bz_r(self, data: Dict[str, Any]) -> Union[Tuple[str, str], None]:
        d: Dict[str, Any] = data["data"]
        a: Any = d.get("accessToken")
        r: Any = d.get("refreshToken")
        if isinstance(a, str) and isinstance(r, str) and len(a) == 598 and len(r) > 79:
            return a.strip(), r.strip()
        return None

    async def new_refresh_cookie(self) -> Tuple[Optional[str], Optional[str]]:
        return self.bz_a, self.bz_r