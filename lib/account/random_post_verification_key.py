import asyncio
import base64
from datetime import datetime, timedelta
import hashlib
import logging
import re
import secrets
from typing import Any, Dict, Optional, List, Tuple, Union
from urllib.parse import parse_qs, urlparse, ParseResult

import httpx


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)


_pw_re: "re.Pattern[str]" = re.compile(
    r'^'  # Start of string
    r'(?=.*[A-Za-z])'  # At least one letter
    r'(?=.*\d)'  # At least one digit
    r'(?=.*[!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])'  # At least one special character
    r'[\x20-\x7E]{8,32}'  # Printable ASCII characters, length 8-32
    r'$'  # End of string
)


class AuthManager:
    # 單例管理：確保全局只有一個 AuthManager 實例
    _instance: Optional["AuthManager"] = None

    # 動態屬性於 create()/from_dict() 中賦值
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
        - S256: 對 code_verifier 做 SHA256，輸出十六進制字串（64 字符）
        - plain: 直接返回 code_verifier
        """
        if method == 'S256':
            digest: bytes = hashlib.sha256(code_verifier.encode()).digest()
            # JS 端使用十六進制輸出，而非 Base64
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
        'pcid': 'jtDlEb93qRCg8MlrYbb86',
        'pacode': 'fanplatf::web:win:pc:',
        'NEXT_LOCALE': 'en',
        '__T_': '1',
        '__T_SECURE': '1',
    }

    headers: Dict[str, str] = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0',
        'Accept': 'application/json',
        'Referer': 'https://berriz.in/',
        'Origin': 'https://berriz.in',
        'Connection': 'keep-alive',
        'Pragma': 'no-cache',
    }

    async def post(self, url: str, p: Dict[str, Any], json_data: Dict[str, Any] = {}) -> httpx.Response:
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            response: httpx.Response = await client.post(
                url,
                params=p,
                cookies=Request.cookies,
                headers=Request.headers,
                json=json_data,
            )
            if response.status_code < 400:
                return response
            else:
                logging.error(f"{response.status_code} - {response.url}")
                raise RuntimeError(response.status_code)

    async def get(self, url: str, p: Dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            response: httpx.Response = await client.get(
                url,
                params=p,
                cookies=Request.cookies,
                headers=Request.headers,
            )
            if response.status_code < 400:
                return response
            else:
                logging.error(f"{response.status_code} - {response.url}")
                raise RuntimeError(response.status_code)


R: Request = Request()


async def send_verification_email(email: str) -> Optional[bool]:
    params: Dict[str, Any] = {
        'languageCode': 'en',
    }
    json_data: Dict[str, Any] = {
        'sendTo': email,
    }
    url: str = 'https://account.berriz.in/member/v1/verification-emails:send/SIGN_UP'
    logging.info(f'send to {email}')
    response: httpx.Response = await R.post(url, params, json_data)
    if response.json()['code'] == '0000':
        return True
    elif response.json()['code'] != '0000':
        logging.error(response.json())
    # 隱式返回 None，保持原行為

async def post_verification_key(email: str, otpInt: str) -> Optional[str]:
    params: Dict[str, Any] = {
        'languageCode': 'en',
    }

    json_data: Dict[str, Any] = {
        'email': email,
        'otpCode': otpInt,
    }
    url: str = 'https://account.berriz.in/member/v1/verification-emails:verify/SIGN_UP'
    response: httpx.Response = await R.post(url, params, json_data)
    if response.json()['code'] == '0000' and response.json()['message'] == 'OK':
        verifiedKey: str = response.json()['data']['verifiedKey']
        if len(verifiedKey) != 36:
            logging.error('verifiedKey not vaild uuid')
            raise ValueError('Check verifiedKey is uuid or not.')
        elif len(verifiedKey) == 36:
            return verifiedKey
    elif response.json()['code'] == 'FS_ME2050':
        logging.error(f"{response.json()['message']} resend a new code for {email}")
        await VerifiedKEY.sign_up(email)  # 型別上允許，保留原呼叫形式
    elif response.json()['code'] != '0000':
        logging.error(response.json())
        return None
    # 隱式返回 None，保持原行為

async def terms(email: str, password: str, verifiedKey: str) -> Optional[bool]:
    params: Dict[str, Any] = {
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
    if response.json()['code'] == '0000' and response.json()['message'] == 'OK':
        return True
    elif response.json()['code'] == 'FS_ME1050':
        logging.error(f"{response.json()['message']}")
    elif response.json()['code'] == 'FS_ER4010':
        logging.error('Please enter a combination of alphanumeric and special characters')
    elif response.json()['code'] != '0000':
        logging.error(response.json())
        raise Exception(response.json())
    # 隱式返回 None，保持原行為

async def authorizeKey(codeChallenge: str, state: str, clientId: str) -> str:
    params: Dict[str, Any] = {
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
    if response.json()['code'] == '0000' and response.json()['message'] == 'OK':
        return response.json()['data']['authorizeKey']
    elif response.json()['code'] != '0000':
        logging.error(response.json())
        raise Exception(response.json())

async def authenticateKey(authorizeKey: str, challenge: str, state_csrf: str, ENMAIL: str, PASSWORD: str, CLIENTID: str) -> str:
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
    if response.json()["code"] == "0000":
        key: str = response.json()["data"]["authenticateKey"]
        if not key or len(key) != 30:
            raise ValueError(f"Bad authenticateKey: {key}")
        return key
    elif response.json()["code"] == "FS_AU4002":
        logging.error(response.json()["message"])
        raise ValueError('DATA_INVALID')
    elif response.json()["code"] == "FS_AU4002":
        logging.error(response.json()["message"])
        raise ValueError('Enter a valid password')
    else:
        response.json()["code"] != '0000'
        logging.error(response.json())
        raise Exception(response.json())

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


class VerifiedKEY:
    def __init__(self, email: str, password: str):
        self.account: str = (email or "").strip().lower()
        self.password: str = (password or "").strip()
        self.CLIENTID: str = 'e8faf56c-575a-42d2-933d-7b2e279ad827'

    def validate_password_regex(self) -> bool:
        return bool(_pw_re.match(self.password))
    
    def check_challenge(self, ch: str) -> bool:
        return len(ch) == 64

    def check_state(self, st: str) -> bool:
        return len(st) == 21

    def check_code_verifier(self, cv: str) -> bool:
        return len(cv) == 21

    def check_location_url(self, url: str) -> bool:
        return (
            url.startswith("https://berriz.in/auth/token?code=")
            and len(url) > 110
        )

    def check_code_value(self, code: str) -> bool:
        return code is not None and len(code) == 30

    def check_code_value(self, code: str) -> bool:
        return code is not None and len(code) == 30

    def check_bz_a_bz_r(self, data: dict) -> bool:
        return data.get("code") == "0000" and isinstance(data.get("data"), dict)
    
    def sort_bz_a_bz_r(self, data: dict) -> Union[Tuple[str, str], None]:
        d = data["data"]
        a = d.get("accessToken")
        r = d.get("refreshToken")
        if isinstance(a, str) and isinstance(r, str) and len(a) == 598 and len(r) > 79:
            return a.strip(), r.strip()
        return None

    def get_auth_request(email, password, clientId) -> Tuple[str, str, str]:  # 保留原無 self 簽名
        res: Dict[str, Any] = create_auth_request(
            password=password,
            authorize_key='',
            email=email,
            challenge_method="S256",
            post_redirect_uri="https://berriz.in/auth/token&postRedirectUri=/",
            clientid=clientId,
        )
        m: AuthManager = res["auth_manager"]
        return m.challenge, m.state, m.code_verifier

    async def sign_up(self) -> Optional[bool]:
        # PKCE 請求
        codeChallenge, state, verifier = self.get_auth_request(self.password, self.CLIENTID)  # 原調用簽名保持不變
        if not all((self.check_challenge(codeChallenge),
                    self.check_state(state),
                    self.check_code_verifier(verifier))):
            return False
        print(codeChallenge, state, verifier)
        if await send_verification_email(self.account) is True:
            otpInt: str = self.handle_user_input()
            verifiedKey: Optional[str] = await post_verification_key(self.account, otpInt)
            logging.info(verifiedKey)
        else:
            logging.info(f'{email}: This email address is already registered')
        # 隱式返回 None，保持原行為

    def handle_user_input(self) -> str:
        prompt: str = f"Enter the 6-digit code you received via email: {self.account} "
        while True:
            logging.info(prompt)
            otp_code: str = input(prompt).strip()
            if otp_code.isdigit() and len(otp_code) == 6:
                return otp_code
            logging.warning("Invalid OTP: must be exactly 6 digits")


email: str = 'akmo5ud@concu.net'
clientId: str = 'e8faf56c-575a-42d2-933d-7b2e279ad827'
asyncio.run(VerifiedKEY(email, clientId).sign_up())