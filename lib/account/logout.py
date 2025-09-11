import requests
def logout():
    cookies = {
        'pcid': '2a8efaf9a92eadb88b38a0324306edc75fc5fb7688b88a508e66f69d5dffdee4',
        'pacode': 'fanplatf::app:android:phone',
        '__T_': '1',
        '__T_SECURE': '1',
        'bz_a': 'eyJraWQiOiJUUWVSeENZSFhDMkxNQTdFY0Rma1hBQ3loSzBjMlAzajZ6VHZXT2h3Ujl3IiwiYWxnIjoiUlMyNTYifQ.eyJpc3MiOiJhY2NvdW50LmJlcnJpei5pbiIsImlhdCI6MTc1NzU3MDcyNiwiZXhwIjoxNzU3NTc0MzI2LCJzdWIiOiIwMTk4ODRkZS03ZGI2LWQwZGItZDc1NC03M2NkNmQ2ZGYzODMiLCJpZHBOYW1lIjoiRkFOWiJ9.ESt85glof_ip9rKKH9b8hp3yHZNhUq5EYidpLt__wtsNU5cruUGhdISqNnEilLoDFyxsMcnnNu2aL0wf2V22Wf_NEopH6yPJGgvVa1hiiHaviRGaFqcGcFR9oAwU0Jum9zP1VLtcrFpoDjLDwlNuziirjgkYB1oTSEC4Q0XURqXHUwZg-y3ObEwByc73S0oqV9uwDqKXOs0R4_cENBVnKItfQOG1rOQhMitTQLJE09MKCCpwh8G7UMI2RUwI1pw-Me7EJx9oN50DbNvaKmi_-PgEZgbtwjoHbrlSJz2W69woxu4JvhUE_U-5Ma5RpYJsXMcbpJvePbioB2m7yhV5hA',
        'bz_r': 'ydraKQJLCiyR3xa82Tw8bDMyrjIUYsqCtBwW4X20rKaIBnCF0OVjDdTnNaBFOJssDl3UUDFbnYhIMsF49AhmQr39xSSwy',
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