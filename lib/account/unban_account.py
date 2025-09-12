import asyncio
import logging
import sys
import httpx
import uuid

from static.color import Color
from unit.handle_log import setup_logging


logging = setup_logging('unban_account', 'linen')


class Request:
    cookies = {
        'pcid': 'lI7rkSE16xpDltz1A14Zn',
        'pacode': 'fanplatf::app:android:phone',
        '__T_': '1',
        '__T_SECURE': '1',
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0',
        'Accept': 'application/json',
        'Referer': 'https://berriz.in/',
        'Origin': 'https://berriz.in',
        'Content-Type': 'application/json',
        'Connection': 'keep-alive',
    }

    params = {'languageCode': 'en'}
    
    def __init__(self):
        pass
        
    async def post(self, url, json_data):
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            response = await client.post(
                url,
                params=Request.params,
                cookies=Request.cookies,
                headers=Request.headers,
                json=json_data,
            )
            return response
        
    async def put(self, url, json_data):
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            response = await client.put(
                url,
                params=Request.params,
                cookies=Request.cookies,
                headers=Request.headers,
                json=json_data,
            )
            return response
R = Request()

async def berriz_verification_email_code(email: str):
    """不會和資料庫拿帳號ID或OAUTH驗證 沒有註冊過也會發"""
    json_data = {'sendTo': email}

    response = await R.post(
        'https://account.berriz.in/member/v1/verification-emails:send/UNBLOCK',
        json_data,
    )
    if str(response.status_code) == '201':
        if response.json()['code'] == '0000':
            return True
        elif response.json()['code'] != '0000':
            if response.json()['code'] == 'FS_ME2020':
                logging.error(f"{Color.bg('cyan')}You've exceeded the code request limit. Please try again after 1 hour.{Color.reset()}")
                raise RuntimeWarning('Max exceeded e-mail code')
            logging.warning(f"{Color.fg('golden')}{response.json()['message']}{Color.reset()}")
            return False
    else:
        logging.error(f" {response.status_code} 'https://account.berriz.in/member/v1/verification-emails:send/UNBLOCK'")
        return False

async def post_verification_key(email: str, otpInt: str):
    json_data = {'email': email, 'otpCode': str(otpInt)}

    response = await R.post(
        'https://account.berriz.in/member/v1/verification-emails:verify/UNBLOCK',
        json_data,
    )
    if response.json()['code'] == '0000':
        return response.json()['data']['verifiedKey']
    elif response.json()['code'] == 'FS_ME2050':
        logging.warning(f"{Color.fg('golden')}{response.json()['message']} resend a new code for {Color.reset()}{email}")
        await unban_main(email)
    if response.json()['code'] not in ("0000", "FS_ME2050"):
        logging.error('Fail to get verifiedKey')
        return None

async def member_unlock(email: str, verifiedKey: str):
    json_data = {'email': str(email), 'verifiedKey': str(verifiedKey)}
    response = await R.put(
        'https://account.berriz.in/member/v1/members:unblock',
        json_data,
    )
    if response.json()['code'] == '0000':
        logging.info(f"{Color.fg('green')}{response.json()['message']}{Color.reset()}")
        return True
    elif response.json()['code'] == 'FS_ER5010':
      logging.warning(f"{response.json()['message']} This account may not be registered in the Berriz database")
      return False
    if response.json()['code'] != '0000':
        logging.error(f"{Color.fg('golden')}{response.json()['message']}{Color.reset()}")
        return False

def handle_user_input(email):
    while True:
        logging.info(f"{Color.fg('light_gray')}Auto start unban account, Please enter the 6-digit code you received via email: {Color.fg('yellow')}{email} {Color.reset()}")
        otpCode = input(f'{Color.fg("honeydew")}Enter the 6-digit code you received via email:{Color.reset()} {Color.fg("yellow")}{email} {Color.reset()}').strip()
        if otpCode.isdigit() and len(otpCode) == 6:
            otpInt = str(otpCode.strip())
            return str(otpInt)
        logging.warning("Invalid OTP: must be exactly 6 digits")

async def unban_main(email):
    email = email.strip().lower()
    if await berriz_verification_email_code(email) is True:
        otpInt = handle_user_input(email)
        verification_key = await post_verification_key(email, otpInt)
        if verification_key is not None:
            if await member_unlock(email, verification_key) is True:
                logging.info(f"{Color.fg('light_gray')}Your account {Color.fg('yellow')}"
                            f"{email} {Color.fg('light_gray')}has been unlocked. Please log in again"
                            )
                return True
            else:
                sys.exit(1)