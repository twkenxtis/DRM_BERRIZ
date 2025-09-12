import asyncio
import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import yaml

from static.color import Color
from unit.handle_log import setup_logging
import aiofiles
import orjson


logger = setup_logging('login', 'flamingo_pink')


class AuthManager:
    # 單例管理：確保全局只有一個 AuthManager 實例
    _instance = None

    @classmethod
    def create(cls, challenge_method='S256'):
        """
        創建新的認證管理器實例，對應 JS 端 a.R.create() 的行為
        - 生成 code_verifier、code_challenge、state
        - 設定實例的有效期限（10 分鐘）
        """
        instance = cls()
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
    def get(cls):
        """
        獲取現有的認證管理器實例，對應 JS 端 a.R.get() 的行為
        只有在實例存在且未過期時才返回，否則返回 None
        """
        inst = cls._instance
        if inst and inst._is_valid():
            return inst
        return None

    @classmethod
    def _generate_code_verifier(cls):
        """
        生成 PKCE code_verifier - 匹配 JS 端 21 字符長度
        1. 16 字節隨機數據
        2. Base64-URL 編碼
        3. 移除 '=' 填充
        4. 截斷至 21 字符
        """
        random_bytes = secrets.token_bytes(16)
        verifier = base64.urlsafe_b64encode(random_bytes).decode()
        verifier = verifier.replace('=', '')  # 去掉填充符
        return verifier[:21]                  # 確保長度

    @classmethod
    def _generate_challenge(cls, code_verifier, method='S256'):
        """
        生成 PKCE code_challenge，對應 JS 端的行為
        - S256: 對 code_verifier 做 SHA256，輸出十六進制字串（64 字符）
        - plain: 直接返回 code_verifier
        """
        if method == 'S256':
            digest = hashlib.sha256(code_verifier.encode()).digest()
            # JS 端使用十六進制輸出，而非 Base64
            challenge = digest.hex()
            return challenge
        elif method == 'plain':
            return code_verifier
        else:
            raise ValueError(f"Unsupported challenge method: {method}")

    @classmethod
    def _generate_state(cls):
        """
        生成防 CSRF 的 state，行為與 code_verifier 相同
        - 16 字節隨機數據
        - Base64-URL 編碼
        - 去除 '=' 填充
        - 截斷至 21 字符
        """
        random_bytes = secrets.token_bytes(16)
        state = base64.urlsafe_b64encode(random_bytes).decode().replace('=', '')
        return state[:21]

    def _is_valid(self):
        """檢查單例實例是否在有效期限內"""
        return datetime.now() < self.expires_at

    def to_dict(self):
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
    def from_dict(cls, data):
        """
        從字典恢復 AuthManager 實例，對應 JS 端 a.R 從 localStorage 讀取行為
        """
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
        client_id,
        redirect_uri,
        post_redirect_uri='/',
        language_code='en'
    ):
        """
        生成 OAuth 授權請求的 URL，對應 JS 端 authorize:init 參數
        """
        base_url = "https://account.berriz.in/auth/v1/authorize:init"
        params = {
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
    password,
    authorize_key,
    email,
    clientid,
    challenge_method='S256',
    post_redirect_uri=None
):
    """
    複製原始 JavaScript 功能的完整實現
    - 先嘗試從單例 get() 拿取，否則 create() 新實例
    - 構建 authenticate 所需的請求體
    """
    auth_manager = AuthManager.get() or AuthManager.create(challenge_method)

    request_data = {
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
    cookies = {
        'pcid': '2a8efaf9a92eadb88b38a0324306edc75fc5fb7688b88a508e66f69d5dffdee4',
        'pacode': 'fanplatf::app:android:phone',
        '__T_': '1',
        '__T_SECURE': '1',
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Referer': 'https://berriz.in/',
        'Origin': 'https://berriz.in',
        'Connection': 'keep-alive',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }

        
    async def post(self, url, p, json_data):
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            response = await client.post(
                url,
                params=p,
                cookies=Request.cookies,
                headers=Request.headers,
                json=json_data,
            )
            return response

    async def get(self, url, p):
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            response = await client.get(
                url,
                params=p,
                cookies=Request.cookies,
                headers=Request.headers,
                
            )
            return response
R = Request()

async def vaild_email(ENMAIL):
    params = {
        'email': ENMAIL,
    }
    url = 'https://account.berriz.in/member/v1/members:email-exists'
    response = await R.get(url, params)
    return response.json()
    

async def authorizeKey(challenge, state, CLIENTID):
    params = {
        'clientId': CLIENTID,
        'codeChallenge': challenge,
        'challengeMethod': 'S256',
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/en/',
        'state': state,
        'languageCode': 'en',
    }
    url = 'https://account.berriz.in/auth/v1/authorize:init'
    response = await R.get(url, params)
    return response.json()


async def get_code(CLIENTID, challenge, state_csrf, authenticatekey):
    params = {
        'clientId': CLIENTID,
        'codeChallenge': challenge,
        'challengeMethod': 'S256',
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/',
        'state': state_csrf,
        'authenticateKey': authenticatekey,
    }
    url = 'https://account.berriz.in/auth/v1/authorize'
    response = await R.get(url, params)
    location_header = response.headers.get('location')
    return location_header

async def authenticateKey(authorizeKey, challenge, state_csrf, ENMAIL, PASSWORD, CLIENTID):
    params = {
        'languageCode': 'en',
    }

    json_data = {
        'password': PASSWORD,
        'clientId': CLIENTID,
        'authorizeKey': authorizeKey,
        'challengeMethod': 'S256',
        'codeChallenge': challenge,
        'state': state_csrf,
        'email': ENMAIL,
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/en/',
    }
    url = 'https://account.berriz.in/auth/v1/authenticate'
    response = await R.post(url, params, json_data)
    return response.json()

async def token_issue(CLIENTID, code_value, code_verifier):
    params = {
        'languageCode': 'en',
    }

    json_data = {
        'code': code_value,
        'clientId': CLIENTID,
        'codeVerifier': code_verifier,
        'redirectUri': 'https://berriz.in/auth/token',
        'postRedirectUri': '/',
    }
    url = 'https://account.berriz.in/auth/v1/token:issue'
    response = await R.post(url, params, json_data)
    return response.json()

def extract_url_params(url_string):
    """
    從網址字串中解析並提取 'code' 和 'postRedirectUri' 參數
    """
    parsed_url = urlparse(url_string)
    query_params = parse_qs(parsed_url.query)
    code = query_params.get('code', [None])[0]
    postRedirectUri = query_params.get('postRedirectUri', [None])[0]
    return code, postRedirectUri


class LoginManager:
    
    EMAIL_REGEX = re.compile(r".+@.+\..+")
    
    YAML_PATH = Path("cookies") / "account.yaml"
    CLIENTID = 'e8faf56c-575a-42d2-933d-7b2e279ad827'

    def __init__(self):
        self.account = None
        self.password = None
        self.bz_a = None
        self.bz_r = None
        pass

    async def load_info(self):
        if not LoginManager.YAML_PATH.exists():
            raise FileNotFoundError
        async with aiofiles.open(LoginManager.YAML_PATH, 'r', encoding='utf-8') as f:
            data = await f.read()
            if self.sort_yaml(yaml.safe_load(data)) is True:
                if await self.run_login() is True:
                    return True
        
    def sort_yaml(self, yaml_dict):
        if yaml_dict is not None and type(yaml_dict) is dict:
            account = yaml_dict['berriz']['account']
            password = yaml_dict['berriz']['password']
            account = account.strip().lower()
            password = password.strip()
            if LoginManager.EMAIL_REGEX.match(account) and len(password) > 7 and len(account) > 2:
                self.account = account
                self.password = password
                return True

    async def run_login(self):
        if await self.check_mail() is True:
            challenge, state_pks, code_verifier = self.get_auth_request()
            if not all([self.check_challenge, self.check_state, self.check_code_verifier]):
                return
            authkey_data = await authorizeKey(challenge, state_pks, LoginManager.CLIENTID)
            authkey = self.check_authkey(authkey_data)
            authenticatekey_data =  await authenticateKey(authkey, challenge, state_pks, self.account, self.password, LoginManager.CLIENTID)
            authenticatekey = self.check_authenticatekey(authenticatekey_data)
            location_url = await get_code(LoginManager.CLIENTID, challenge, state_pks, authenticatekey)
            if self.check_location_url(location_url) is False:
                return
            code_value, postRedirectUri_value = extract_url_params(location_url)
            if self.check_code_value(code_value) is False:
                return
            bz_a_bz_r = await token_issue(LoginManager.CLIENTID, code_value, code_verifier)
            if self.check_bz_a_bz_r(bz_a_bz_r) is False:
                return
            result = self.sort_bz_a_bz_r(bz_a_bz_r)
            if result is not None:
                bz_a, bz_r = result
                self.bz_a = bz_a
                self.bz_r = bz_r
                return True
            
    async def check_mail(self):
        email = await vaild_email(self.account)
        if email is not None and email['code'] == '0000':
            if email['data']['exists'] is False:
                raise ValueError(f"Account does not exist: {self.account}")
            return True
        elif email is not None and email['code'] == 'FS_ME2120':
            return False
        else:
            raise Exception('Unknown error at check mail')
            
    def get_auth_request(self):
        result = create_auth_request(
            password = self.password,
            email = self.account,
            authorize_key='',
            challenge_method='S256',
            post_redirect_uri='https://berriz.in/auth/token&postRedirectUri=/en',
            clientid = LoginManager.CLIENTID,
        )
        try:
            challenge = result['auth_manager'].challenge
            state_csrf = result['auth_manager'].state
            code_verifier = result['auth_manager'].code_verifier
            if all([challenge, state_csrf, code_verifier]):
                return challenge, state_csrf, code_verifier
        except Exception as e:
            raise ValueError(f"Failed to get auth request: {e}")

    def check_authkey(self, authkey):
        if authkey is None:
            raise ValueError("Auth key is None")
        elif authkey['code'] == '0000' and authkey['message'] == 'OK':
            key = authkey['data']['authorizeKey']
            if key is not None and len(key) == 30:
                    return key
            elif key is not None and len(key) != 30:
                raise ValueError(key, "Auth key length is not 30", len(key))
        elif authkey['code'] != '0000':
            raise ValueError(f"Auth key error: {authkey}")
        
    def check_challenge(self, challenge):
        if len(challenge) == 64:
            return True
        return False

    def check_state(self, state_pks):
        if len(state_pks) == 21:
            return True
        return False

    def check_code_verifier(self, code_verifier):
        if len(code_verifier) == 21:
            return True
        return False
    
    def check_authenticatekey(self, authenticatekey_data):
        if authenticateKey is None:
            raise ValueError("Auth key is None")
        elif authenticatekey_data['code'] == '0000' and authenticatekey_data['message'] == 'OK':
            key = authenticatekey_data['data']['authenticateKey']
            if key is not None and len(key) == 30:
                    return key
            elif key is not None and len(key) != 30:
                raise ValueError(key, "Auth key length is not 30", len(key))
        elif authenticatekey_data['code'] != '0000':
            raise ValueError(f"Auth key error: {authenticatekey_data}")
        
    def check_location_url(self, location_url):
        if location_url is None:
            raise ValueError("Location URL is None")
        
        if location_url.startswith('https://berriz.in/auth/token?code='):
            if len(location_url) > 110:
                return True
        return False
    
    def check_code_value(self, code_value):
        if code_value is None:
            raise ValueError("Code value is None")
        elif len(code_value) == 30:
            return True
        return False
    
    def check_bz_a_bz_r(self, bz_a_bz_r):
        if bz_a_bz_r is None:
            raise ValueError("bz_a_bz_r is None")
        elif bz_a_bz_r['code'] == '0000' and bz_a_bz_r['message'] == 'OK':
            return True
        return False
    
    def sort_bz_a_bz_r(self, bz_a_bz_r):
        if not isinstance(bz_a_bz_r, dict):
            return None

        data = bz_a_bz_r.get('data')
        if not isinstance(data, dict):
            return None

        bz_a = data.get('accessToken')
        bz_r = data.get('refreshToken')

        if isinstance(bz_a, str) and isinstance(bz_r, str):
            if len(bz_a) == 598 and len(bz_r) > 79:
                return bz_a.strip(), bz_r.strip()
        return None
    
    async def new_refresh_cookie(self):
        return self.bz_a, self.bz_r