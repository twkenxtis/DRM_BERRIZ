import asyncio
import sys

import httpx
from httpx import Response
from typing import Dict, Any, Optional

from static.color import Color
from unit.__init__ import USERAGENT
from unit.handle.handle_log import setup_logging

PCID = 'ZOqaqhZDP51ktDutTpV_F'
logger = setup_logging('unban_account', 'linen')


class Request:
    """
    HTTP 請求客戶端，封裝了 POST 和 PUT 方法
    """
    cookies: Dict[str, str] = {
        'pcid': str(PCID),
        'pacode': 'fanplatf::app:android:phone',
        '__T_': '1',
        '__T_SECURE': '1',
    }

    headers: Dict[str, str] = {
        'User-Agent': f"{USERAGENT}",
        'Accept': 'application/json',
        'Referer': 'https://berriz.in/',
        'Origin': 'https://berriz.in',
        'Content-Type': 'application/json',
        'Connection': 'keep-alive',
    }

    params: Dict[str, str] = {'languageCode': 'en'}
    
    def __init__(self) -> None:
        pass
        
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
        
    async def put(self, url: str, json_data: Dict[str, Any]) -> Response:
        """發送異步 PUT 請求"""
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            attempt: int = 0
            while attempt < 3:
                try:
                    response: Response = await client.put(
                        url,
                        params=Request.params,
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


R = Request()


async def berriz_verification_email_code(email: str) -> bool:
    """
    請求發送解鎖驗證碼到指定郵箱
    不會和資料庫拿帳號 ID 或 OAUTH 驗證，未註冊過也會發送
    """
    json_data: Dict[str, str] = {'sendTo': email}

    try:
        response: Response = await R.post(
            'https://account.berriz.in/member/v1/verification-emails:send/UNBLOCK',
            json_data,
        )
    except RuntimeError:
        return False # 捕獲 httpx 請求失敗

    response_json: Dict[str, Any] = response.json()

    if response.status_code == 201:
        if response_json.get('code') == '0000':
            return True
        elif response_json.get('code') == 'FS_ME2020':
            logger.error(f"{Color.bg('cyan')}You've exceeded the code request limit. Please try again after 1 hour.{Color.reset()}")
            raise RuntimeWarning('Max exceeded e-mail code')
        
        logger.warning(f"{Color.fg('golden')}{response_json.get('message', 'Unknown message')}{Color.reset()}")
        return False
    else:
        logger.error(f" {response.status_code} 'https://account.berriz.in/member/v1/verification-emails:send/UNBLOCK'")
        return False


async def post_verification_key(email: str, otpInt: str) -> Optional[str]:
    """
    驗證用戶收到的 OTP 碼，並獲取 verifiedKey
    """
    json_data: Dict[str, str] = {'email': email, 'otpCode': otpInt}

    try:
        response: Response = await R.post(
            'https://account.berriz.in/member/v1/verification-emails:verify/UNBLOCK',
            json_data,
        )
    except RuntimeError:
        return None

    response_json: Dict[str, Any] = response.json()
    code: Optional[str] = response_json.get('code')

    if code == '0000':
        return response_json['data']['verifiedKey']
    elif code == 'FS_ME2050':
        logger.warning(f"{Color.fg('golden')}{response_json.get('message', 'Code expired')} resend a new code for {Color.reset()}{email}")
        await unban_main(email)
    
    if code not in ("0000", "FS_ME2050"):
        logger.error('Fail to get verifiedKey')
        return None
    return None


async def member_unlock(email: str, verifiedKey: str) -> bool:
    """
    使用 verifiedKey 發起解鎖會員帳號的請求
    """
    json_data: Dict[str, str] = {'email': email, 'verifiedKey': verifiedKey}
    
    try:
        response: Response = await R.put(
            'https://account.berriz.in/member/v1/members:unblock',
            json_data,
        )
    except RuntimeError:
        return False

    response_json: Dict[str, Any] = response.json()
    code: Optional[str] = response_json.get('code')

    if code == '0000':
        logger.info(f"{Color.fg('green')}{response_json.get('message', 'Account unlocked successfully')}{Color.reset()}")
        return True
    elif code == 'FS_ER5010':
        logger.warning(f"{response_json.get('message', 'Error 5010')} This account may not be registered in the Berriz database")
        return False
    
    logger.error(f"{Color.fg('golden')}{response_json.get('message', 'Unknown unlock error')}{Color.reset()}")
    return False


def handle_user_input(email: str) -> str:
    """
    處理並驗證用戶輸入的 6 位數 OTP 碼
    """
    while True:
        logger.info(f"{Color.fg('light_gray')}Auto start unban account, Please enter the 6-digit code you received via email: {Color.fg('yellow')}{email} {Color.reset()}")
        otpCode: str = input(f'{Color.fg("honeydew")}Enter the 6-digit code you received via email:{Color.reset()} {Color.fg("yellow")}{email} {Color.reset()}').strip()
        
        if otpCode.isdigit() and len(otpCode) == 6:
            otpInt: str = otpCode.strip()
            return otpInt
        
        logger.warning("Invalid OTP: must be exactly 6 digits")


async def unban_main(email: str) -> bool:
    """
    主解鎖流程：發送郵箱驗證碼 -> 獲取用戶輸入 -> 獲取 Verified Key -> 解鎖帳號
    """
    email = email.strip().lower()
    
    try:
        if await berriz_verification_email_code(email):
            otpInt: str = handle_user_input(email)
            verification_key: Optional[str] = await post_verification_key(email, otpInt)
            
            if verification_key is not None:
                if await member_unlock(email, verification_key):
                    logger.info(f"{Color.fg('light_gray')}Your account {Color.fg('yellow')}"
                                f"{email} {Color.fg('light_gray')}has been unlocked. {Color.fg('green')}Please login again{Color.reset()}"
                    )
                    return True
                else:
                    sys.exit(1)
            else:
                return False # post_verification_key 返回 None
        else:
            return False # berriz_verification_email_code 返回 False
            
    except RuntimeWarning:
        # 處理郵箱發送次數超限
        return False
    except SystemExit:
        raise # 重新拋出 sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred in unban_main: {e}", exc_info=True)
        return False