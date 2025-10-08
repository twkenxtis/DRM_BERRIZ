import asyncio
import base64
from datetime import datetime, timedelta
import hashlib
import logging
import re
import secrets
from typing import List, Tuple, Union, Optional, Dict, Any, Literal

import httpx

from static.api_error_handle import api_error_handle
from static.color import Color
from unit.__init__ import USERAGENT
from urllib.parse import parse_qs, urlparse
from unit.handle.handle_log import setup_logging


logger = setup_logging('signup', 'periwinkle')
_session: Optional[httpx.AsyncClient] = None


# 密碼強度正則表達式檢查
_pw_re: re.Pattern[str] = re.compile(
    r'^'  # Start of string
    r'(?=.*[A-Za-z])'  # 至少一個字母
    r'(?=.*\d)'  # 至少一個數字
    r'(?=.*[!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])'  # 至少一個特殊字符
    r'[\x20-\x7E]{8,32}'  # 可列印 ASCII 字符, 長度 8-32
    r'$'  # End of string
)

PCID = 'ZOqaqhZDP51ktDutTpV_F'
CLIENTID: str = 'e8faf56c-575a-42d2-933d-7b2e279ad827'

class AuthManager:
    """
    PKCE 認證流程的狀態管理器
    作為一個單例 (Singleton) 使用，用於在不同請求間保持 code_verifier 和 state
    """
    _instance: Optional['AuthManager'] = None

    def __init__(self) -> None:
        # 實例變數初始化
        self.code_verifier: str = ''
        self.challenge: str = ''
        self.state: str = ''
        self.created_at: datetime = datetime.min
        self.expires_at: datetime = datetime.min

    @classmethod
    def create(cls, challenge_method: Literal['S256', 'plain'] = 'S256') -> 'AuthManager':
        """
        創建新的認證管理器實例，並生成 PKCE 相關的 key
        """
        instance = cls()
        # 1. 生成符合 JS 實作的 21 字符 code_verifier
        instance.code_verifier = cls._generate_code_verifier()
        # 2. 根據 code_verifier 生成 code_challenge
        instance.challenge = cls._generate_challenge(
            instance.code_verifier,
            challenge_method
        )
        # 3. 生成防 CSRF 的 state（21 字符）
        instance.state = cls._generate_state()
        # 實例時間標記與過期時間（10 分鐘）
        instance.created_at = datetime.now()
        instance.expires_at = instance.created_at + timedelta(minutes=10)

        # 保存單例
        cls._instance = instance
        return instance

    @classmethod
    def get(cls) -> Optional['AuthManager']:
        """
        獲取現有的認證管理器實例只有在實例存在且未過期時才返回
        """
        inst = cls._instance
        if inst and inst._is_valid():
            return inst
        return None

    @classmethod
    def _generate_code_verifier(cls) -> str:
        """
        生成 PKCE code_verifier (21 字符長度)
        """
        random_bytes: bytes = secrets.token_bytes(16)
        verifier: str = base64.urlsafe_b64encode(random_bytes).decode()
        verifier = verifier.replace('=', '')  # 去掉填充符
        return verifier[:21]

    @classmethod
    def _generate_challenge(cls, code_verifier: str, method: Literal['S256', 'plain']) -> str:
        """
        生成 PKCE code_challenge
        - S256: SHA256 後轉為十六進製字串 (64 字符)
        - plain: 直接返回 code_verifier
        """
        if method == 'S256':
            digest: bytes = hashlib.sha256(code_verifier.encode()).digest()
            # 匹配 JS 端的十六進製輸出
            challenge: str = digest.hex()
            return challenge
        elif method == 'plain':
            return code_verifier
        else:
            raise ValueError(f"Unsupported challenge method: {method}")

    @classmethod
    def _generate_state(cls) -> str:
        """
        生成防 CSRF 的 state (21 字符長度)
        """
        random_bytes: bytes = secrets.token_bytes(16)
        state: str = base64.urlsafe_b64encode(random_bytes).decode().replace('=', '')
        return state[:21]

    def _is_valid(self) -> bool:
        """檢查單例實例是否在有效期限內"""
        return datetime.now() < self.expires_at

    def to_dict(self) -> Dict[str, str]:
        """將實例轉換為字典，用於持久化存儲"""
        return {
            'code_verifier': self.code_verifier,
            'challenge': self.challenge,
            'state': self.state,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'AuthManager':
        """從字典恢復 AuthManager 實例"""
        instance = cls()
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
        """生成 OAuth 授權請求的 URL"""
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
        return f"{base_url}?{httpx.QueryParams(params)}"


def create_auth_request(
    password: str,
    authorize_key: str,
    email: str,
    clientid: str,
    challenge_method: Literal['S256', 'plain'] = 'S256',
    post_redirect_uri: Optional[str] = None
) -> Dict[str, Any]:
    """
    獲取或創建 AuthManager 實例，並構建 'authenticate' API 請求所需數據
    """
    auth_manager: AuthManager = AuthManager.get() or AuthManager.create(challenge_method)

    request_data: Dict[str, Optional[str]] = {
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
    request_data = {k: v for k, v in request_data.items() if v is not None} # type: ignore

    # 構建 httpx 請求配置
    request_config: Dict[str, Any] = {
        'url': 'https://account.berriz.in/auth/v1/authenticate',
        'method': 'POST',
        'headers': {
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        'data': request_data
    }

    return {
        'auth_manager': auth_manager,
        'request_data': request_data,
        'request_config': request_config
    }


class Request:
    """
    異步 HTTP 請求封裝，使用 httpx
    """
    cookies: Dict[str, str] = {
        'pcid': str(PCID),
        'pacode': 'fanplatf::app:android:phone',
        'NEXT_LOCALE': 'en',
        '__T_': '1',
        '__T_SECURE': '1',
    }

    headers: Dict[str, str] = {
        'User-Agent': f"{USERAGENT}",
        'Accept': 'application/json',
        'Referer': 'https://berriz.in/',
        'Origin': 'https://berriz.in',
        'Connection': 'keep-alive',
        'Pragma': 'no-cache',
    }
    
    def __init__(self):
        self.retry_http_status: set[int] = frozenset({400, 401, 403, 500, 502, 503, 504})

    def get_session(self) -> httpx.AsyncClient:
        global _session
        if _session is None:
            _session = httpx.AsyncClient(http2=True, timeout=4, verify=True)
        return _session
    
    async def close_session(self):
        global _session
        if _session is not None:
            await _session.aclose()
            _session = None

    async def post(self, url: str, p: Dict[str, Any], json_data: Dict[str, Any]) -> httpx.Response:
        attempt: int = 0
        while attempt < 3:
            try:
                session = self.get_session()
                response: httpx.Response = await session.post(
                    url,
                    params=p,
                    cookies=Request.cookies,
                    headers=Request.headers,
                    json=json_data,
                )
                if response.status_code in self.retry_http_status:
                    raise httpx.HTTPStatusError(
                        f"Retryable server error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                return response
            except httpx.HTTPStatusError as e:
                if e.response is not None:
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
        attempt: int = 0
        while attempt < 3:
            try:
                session = self.get_session()
                response: httpx.Response = await session.get(
                    url,
                    params=p,
                    cookies=Request.cookies,
                    headers=Request.headers,
                )
                if response.status_code in self.retry_http_status:
                    raise httpx.HTTPStatusError(
                        f"Retryable server error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                return response
            except httpx.HTTPStatusError as e:
                if e.response is not None:
                    logger.warning(f"HTTP server error: {e.response.status_code}, retry {attempt + 1}/{3}")
                else:
                    logger.error(f"HTTP error for {url}: {e} {Color.bg('gold')}{response}{Color.reset()}")
                    return None
            attempt += 1
            sleep: float = min(2.0, 0.5 * (2 ** attempt))
            await asyncio.sleep(sleep)
        logger.error(f"Retry exceeded for {url}")
        return None


R = Request()


async def valid_email(email: str) -> Optional[bool]:
    """
    檢查電子郵件是否存在（已註冊）
    (修正了函數名稱 typo: vaild_email -> valid_email)
    """
    params: Dict[str, str] = {
        'email': email,
        'languageCode': 'en',
    }
    url: str = 'https://account.berriz.in/member/v1/members:signup-email-exists'
    response: httpx.Response = await R.get(url, params)
    response_json: Dict[str, Any] = response.json()
    code: str = response_json.get('code')
    if code == '0000':
        # 預期是 False (不存在)
        return response_json.get('data', {}).get('exists')
    elif code != '0000':
        logger.warning(f"{api_error_handle(code)} → {email}")
        return None
    else:
        logger.error(response_json)
        raise Exception(response_json)

async def step2(email: str) -> bool:
    """
    請求發送驗證碼到電子郵件
    (修正了函數名稱 typo: setp2 -> step2)
    """
    params: Dict[str, str] = {
        'languageCode': 'en',
    }
    json_data: Dict[str, str] = {
        'sendTo': email,
    }
    url: str = 'https://account.berriz.in/member/v1/verification-emails:send/SIGN_UP'
    response: httpx.Response = await R.post(url, params, json_data)
    response_json: Dict[str, Any] = response.json()

    if response_json.get('code') == '0000':
        return True
    else:
        logger.error(response_json)
        return False

async def post_verification_key(email: str, otpInt: str) -> Optional[str]:
    """
    提交 OTP 碼並獲取 verifiedKey
    """
    params: Dict[str, str] = {
        'languageCode': 'en',
    }

    json_data: Dict[str, str] = {
        'email': email,
        'otpCode': otpInt,
    }
    url: str = 'https://account.berriz.in/member/v1/verification-emails:verify/SIGN_UP'
    response: httpx.Response = await R.post(url, params, json_data)
    response_json: Dict[str, Any] = response.json()
    code: str = response_json.get('code')
    if code == '0000' and response_json.get('message') == 'OK':
        verifiedKey: Optional[str] = response_json.get('data', {}).get('verifiedKey')
        if verifiedKey and len(verifiedKey) == 36:
            return verifiedKey
        else:
            logger.error('verifiedKey not valid uuid')
            raise ValueError('Check verifiedKey is uuid or not.')
    elif code == 'FS_ME2050':
        logger.error(f"{response_json.get('message')} resend a new code for {email}")
        await SignupManager(email, '', '').sign_up()
        return None
    else:
        logger.error(response_json)
        return None

async def terms(email: str, password: str, verifiedKey: str) -> bool:
    """
    提交會員註冊資訊，包含服務條款接受
    """
    params: Dict[str, str] = {
        'languageCode': 'en',
    }

    json_data: Dict[str, Any] = {
        'email': email,
        'password': password,
        'verifiedKey': verifiedKey,
        'acceptTermSet': [
            {
                'termKey': '0193608e-f5bb-6c0b-6996-ba7a603abe02',
                'isAccepted': True,
            },
            {
                'termKey': '0193608f-cd05-65e9-b56d-e74dead216b9',
                'isAccepted': True,
            },
        ],
        'hasAgreedToAgeLimit': True,
    }
    url: str = 'https://account.berriz.in/member/v1/members:sign-up'
    response: httpx.Response = await R.post(url, params, json_data)
    response_json: Dict[str, Any] = response.json()
    code :str = response_json.get('code')
    if code == '0000' and response_json.get('message') == 'OK':
        return True
    elif code != '0000':
        logger.error(f"{api_error_handle(code)}")
        return False
    else:
        logger.error(response_json)
        raise Exception(response_json)

async def authorizeKey(codeChallenge: str, state: str, clientId: str) -> Optional[str]:
    """
    獲取授權金鑰 (authorizeKey)
    """
    params: Dict[str, str] = {
        'clientId': clientId,
        'codeChallenge': codeChallenge,
        'challengeMethod': 'S256',
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/',
        'state': state,
        'languageCode': 'en',
    }
    url: str = 'https://account.berriz.in/auth/v1/authorize:init'
    response: httpx.Response = await R.get(url, params)
    response_json: Dict[str, Any] = response.json()

    if response_json.get('code') == '0000' and response_json.get('message') == 'OK':
        return response_json.get('data', {}).get('authorizeKey')
    else:
        logger.error(response_json)
        raise Exception(response_json)

async def authenticateKey(
    authorizeKey: str,
    challenge: str,
    state_csrf: str,
    ENMAIL: str,
    PASSWORD: str,
    CLIENTID: str
) -> str:
    """
    提交憑證並獲取認證金鑰 (authenticateKey)
    """
    params: Dict[str, str] = {
        'languageCode': 'en',
    }

    json_data: Dict[str, str] = {
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
    response_json: Dict[str, Any] = response.json()
    code: str = response_json.get("code")
    if code == "0000":
        key: Optional[str] = response_json.get("data", {}).get("authenticateKey")
        if not key or len(key) != 30:
            raise ValueError(f"Bad authenticateKey: {key}")
        return key
    elif code == "FS_AU4002":
        logger.error(response_json.get("message"))
        raise ValueError('DATA_INVALID')
    else:
        logger.error(response_json)
        raise Exception(response_json)

async def get_code(CLIENTID: str, challenge: str, state_csrf: str, authenticatekey: str) -> Optional[str]:
    """
    使用 authenticateKey 換取授權碼 (code)，返回包含 code 的 location header URL
    """
    params: Dict[str, str] = {
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

async def token_issue(CLIENTID: str, code_value: str, code_verifier: str) -> Dict[str, Any]:
    """
    使用授權碼 (code) 和 code_verifier 獲取存取令牌 (token)
    """
    params: Dict[str, str] = {
        'languageCode': 'en',
    }

    json_data: Dict[str, str] = {
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
    parsed_url = urlparse(url_string)
    query_params: Dict[str, List[str]] = parse_qs(parsed_url.query)
    code: Optional[str] = query_params.get('code', [None])[0]
    postRedirectUri: Optional[str] = query_params.get('postRedirectUri', [None])[0]
    return code, postRedirectUri


class SignupManager:
    """
    處理會員註冊和密碼相關檢查的管理器
    (修正了類別名稱 typo: SignupMannger -> SignupManager)
    """
    def __init__(self, email: str, password: str) -> None:
        self.account: str = (email or "").strip().lower()
        self.password: str = (password or "").strip()
        self.CLIENTID: str = CLIENTID

    def validate_password_regex(self) -> bool:
        """檢查密碼是否符合強度要求"""
        return bool(_pw_re.match(self.password))

    def check_challenge(self, ch: str) -> bool:
        """檢查 code challenge 長度"""
        return len(ch) == 64

    def check_state(self, st: str) -> bool:
        """檢查 state 長度"""
        return len(st) == 21

    def check_code_verifier(self, cv: str) -> bool:
        """檢查 code verifier 長度"""
        return len(cv) == 21

    def check_location_url(self, url: str) -> bool:
        """檢查 location URL 格式"""
        return (
            url.startswith("https://berriz.in/auth/token?code=")
            and len(url) > 110
        )

    def check_code_value(self, code: Optional[str]) -> bool:
        """檢查授權碼 (code) 值"""
        return code is not None and len(code) == 30

    def check_bz_a_bz_r(self, data: Dict[str, Any]) -> bool:
        """檢查 token 響應是否成功"""
        return data.get("code") == "0000" and isinstance(data.get("data"), dict)

    def sort_bz_a_bz_r(self, data: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """提取並驗證 access_token 和 refresh_token"""
        d: Dict[str, Any] = data.get("data", {})
        a: Any = d.get("accessToken")
        r: Any = d.get("refreshToken")
        # 這裡假設 access token 長度為 598 是有效的驗證標準 和 refresh token 長度為 80 以上是有效的驗證標準 (bz_r 長度不一定 80是隨機測試的avg)
        if isinstance(a, str) and isinstance(r, str) and len(a) == 598 and len(r) > 79:
            return a.strip(), r.strip()
        return None

    @staticmethod
    def get_auth_request(password: str, clientId: str) -> Tuple[str, str, str]:
        """
        生成並返回 PKCE 相關的 challenge, state, verifier
        (新增了 @staticmethod 裝飾器)
        """
        res: Dict[str, Any] = create_auth_request(
            password=password,
            authorize_key='',
            email='',
            challenge_method="S256",
            post_redirect_uri="/",
            clientid=clientId,
        )
        m: AuthManager = res["auth_manager"]
        return m.challenge, m.state, m.code_verifier

    async def sign_up(self) -> Union[str, bool]:
        """
        執行完整的會員註冊流程
        """
        if not self.validate_password_regex():
            logger.warning('Your password must contain 8 to 32 alphanumeric and special characters')
            return False

        # PKCE 請求
        codeChallenge, state, verifier = SignupManager.get_auth_request(self.password, self.CLIENTID)
        if not all((self.check_challenge(codeChallenge),
                    self.check_state(state),
                    self.check_code_verifier(verifier))):
            return False

        email_exists: Optional[bool] = await valid_email(self.account)
        if email_exists is False:
            if await step2(self.account):
                otpInt: str = self.handle_user_input()
                verifiedKey: Optional[str] = await post_verification_key(self.account, otpInt)

                if verifiedKey:
                    if await terms(self.account, self.password, verifiedKey) is True:
                        authkey: Optional[str] = await authorizeKey(codeChallenge, state, self.CLIENTID)
                        if authkey:
                            ak_data: str = await authenticateKey(
                                authkey, codeChallenge, state, self.account, self.password, self.CLIENTID,
                            )
                            return f"{Color.fg('gray')}One-time auth temp_token: {ak_data}{Color.reset()} Success create account → {Color.fg('gold')}{self.account}"
            return False
        elif email_exists is True:
            logger.info(f'{self.account}: This email address is already registered')
            return False
        else:
            # valid_email 返回 None 或拋出異常的情況
            return False

    def handle_user_input(self) -> str:
        """
        處理 CLI 上的使用者輸入 OTP 碼
        """
        prompt: str = f"Enter the 6-digit code you received via email: {self.account} "
        while True:
            logger.info(prompt)
            try:
                otp_code: str = input(prompt).strip()
            except EOFError:
                logger.error("Input not available. Cannot prompt for OTP code.")
                raise
                
            if otp_code.isdigit() and len(otp_code) == 6:
                return otp_code
            logger.warning("Invalid OTP: must be exactly 6 digits")


async def run_signup() -> Union[str, bool]:
    EMAIL_REGEX: "re.Pattern[str]" = re.compile(r".+@.+\..+")
    try:
        while True:
            email = input("Enter your email: ")
            if EMAIL_REGEX.match(email):
                logger.info('Password is contain 8 to 32 alphanumeric and special characters.')
                password = input("Enter your password: ")
                resp = await SignupManager(email, password).sign_up()
                if resp is not False:
                    logger.info(f"{resp}{Color.reset()} | {Color.fg('cyan')}{password}{Color.reset()}")
                    break
            else:
                logger.warning("Invalid email format")
    except EOFError:
        pass