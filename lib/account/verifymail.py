import httpx
import uuid

class Request:
    cookies = {
        'pcid': '2a8efaf9a92eadb88b38a0324306edc75fc5fb7688b88a508e66f69d5dffdee4',
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

    params = {
        'languageCode': 'en',
    }
        
    async def post(url, json_data):
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            response = await client.post(
                url,
                params=Request.params,
                cookies=Request.cookies,
                headers=Request.headers,
                json=json_data,
            )
            return response.json()

    async def get(url, json_data):
        async with httpx.AsyncClient(http2=True, verify=True, timeout=13.0) as client:
            response = await client.get(
                url,
                params=Request.params,
                cookies=Request.cookies,
                headers=Request.headers,
                json=json_data,
            )
            return response.json()
R = Request()

def berriz_verification_email_code(email: str):
    """不會和資料庫拿帳號ID或OAUTH驗證 沒有註冊過也會發"""
    json_data = {'sendTo': {email}}

    response = R.post(
        'https://account.berriz.in/member/v1/verification-emails:send/UNBLOCK',
        json=json_data,
    )
    return response # {"code":"0000","message":"OK"}

def post_verification_key(email: str, otpCode: int):
    json_data = {'email': email, 'otpCode': '385224'}

    response = R.post(
        'https://account.berriz.in/member/v1/verification-emails:verify/UNBLOCK',
        json=json_data,
    )
    return response # {"code":"0000","message":"OK","data":{"verifiedKey":"01993736-a197-84b1-4033-13c0218182ec"}}

def member_unlock(email: str, verifiedKey: uuid):
    json_data = {'email': 'omenbibi26@gmail.com', 'verifiedKey': '01993736-a197-84b1-4033-13c0218182ec'}

    response = R.put(
        'https://account.berriz.in/member/v1/members:unblock',
        json=json_data,
    )
    return response.json() # {"code":"0000","message":"OK"}

email = ''.strip().lower()

data = berriz_verification_email_code(email)
print(data)
otpCode = input('Enter the code you received via email').strip()
otpCode = input('Enter the 6-digit code you received via email: ').strip()
if otpCode.isdigit() and len(otpCode) == 6:
    otpInt = int(otpCode)
else:
    print("Invalid OTP: must be exactly 6 digits")
verification_key = post_verification_key(email, otpCode)['data']['verifiedKey']

data = member_unlock(email, verification_key)
print(data)
print('Your account has been unlocked. Please log in again.')
