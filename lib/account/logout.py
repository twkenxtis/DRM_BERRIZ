import requests
def logout():
    cookies = {
        'pcid': 'sPj0iNAHjd7KzbDEBsBUB',
        'pacode': 'fanplatf::app:android:phone',
        '__T_': '1',
        '__T_SECURE': '1',
        'bz_a': 'eyJraWQiOiJUUWVSeENZSFhDMkxNQTdFY0Rma1hBQ3loSzBjMlAzajZ6VHZXT2h3Ujl3IiwiYWxnIjoiUlMyNTYifQ.eyJpc3MiOiJhY2NvdW50LmJlcnJpei5pbiIsImlhdCI6MTc1NzY0MTQ5NywiZXhwIjoxNzU3NjQ1MDk3LCJzdWIiOiIwMTk5MzhlNC03YTYyLWEyZDgtZTNiYy01YTc4MDNhNmQ5ZDEiLCJpZHBOYW1lIjoiRkFOWiJ9.CvXuC8kQcoAjhZt0Xhjan2lMOOWRlv9_ax0lKmfUQkdO8G0Y_EuKAxaxjTHxBKgIoJ1u1s3kwf0ONSLkJUeU6oQxsLhNqpNI4C5OaVSCl8J88CzRdVjMrULxdpBn5pRnHpow0G9A46Wj2Vnrpfa9NzpDBcN9dHA17BeqL1YK7Dw7Rw2Kn2nc-7QXOdmZIFaQxP0yp_mcDw3JrH6Xp1FNKCGH-hgv4u--3aJ5TdfL1jybkTt2idNa6CPK1Kp63Ldlc9Du1SuYwyUbBQkcD9_sdDMFo3_x2JITDtEswR4FUHROOyxkbr0f2PovS5BjbATgTNK-OU_X01vGodjYl34wRg',
        'bz_r': 'wr5dmr9YsyN0aiRCEY9jYi4qLsqSKGFa8Su3xrntjDqri2LYxQmJoDQj7OIQNEeaerBsfxErv9DPfbki1FUFhx7LXZCwgUZyiT',
    }

    headers = {
        'Host': 'account.berriz.in',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Referer': 'https://berriz.in/',
        'Origin': 'https://berriz.in',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache',
    }

    params = {
        'languageCode': 'en',
    }

    json_data = {
        'clientId': 'e8faf56c-575a-42d2-933d-7b2e279ad827',
    }

    response = requests.post(
        'https://account.berriz.in/auth/v1/token:revoke',
        params=params,
        cookies=cookies,
        headers=headers,
        json=json_data,
        verify=True,
    )
    return response.json() # {"code":"0000","message":"OK","data":true}
print(logout())