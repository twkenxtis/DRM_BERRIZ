import os
import re
import sys

import aiohttp

from cookies.cookies import Refresh_JWT, Berriz_cookie
from static.color import Color
from mystate.parse_my import request_my
from unit.http.request_berriz_api import Password_Change
from unit.handle_log import setup_logging


logger = setup_logging('change_pawword', 'magenta_pink')


_pw_re = re.compile(
    r'^'  # Start of string
    r'(?=.*[A-Za-z])'  # At least one letter
    r'(?=.*\d)'  # At least one digit
    r'(?=.*[!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])'  # At least one special character
    r'[\x20-\x7E]{8,32}'  # Printable ASCII characters, length 8-32
    r'$'  # End of string
)

class Change_Password:
    def __init__(self):
        self.response = None
        self.bz_a = None
        self.bz_r = None
    
    def validate_password_regex(self, password) -> bool:
        return bool(_pw_re.match(password))
        
    async def change_password(self):
        await request_my()
        try:
            while True:
                logger.info(f"{Color.bg('dark_magenta')}Start password change{Color.reset()}")
                currentPassword = input(f"{Color.fg('light_gray')}enter {Color.fg('crimson')}current {Color.fg('light_gray')}password: {Color.reset()}").strip()
                newPassword = input(f"{Color.fg('light_gray')}enter {Color.fg('crimson')}new {Color.fg('light_gray')}password: {Color.reset()}").strip()
                if self.validate_password_regex(newPassword) and self.validate_password_regex(currentPassword) is False:
                    logger.warning('Your password must contain 8 to 32 alphanumeric and special characters')
                else:
                    break
            data = await Password_Change().update_password(currentPassword, newPassword)
            if data is not None:
                self.response = data
                bool = await self.handle_response()
                return bool
            else:
                raise ValueError(f'response is {data}')

        except KeyboardInterrupt:
            sys.exit(0)
        except EOFError:
            sys.exit(0)
            
    async def update_default_cookie(self):
        async with aiohttp.ClientSession() as session:
            if await Refresh_JWT(session).update_cookie_file(self.bz_a, self.bz_r) is True:
                await Berriz_cookie.create_temp_json()
                await Berriz_cookie().get_cookies()
                return True
            else:
                logger.error('Fail update default.txt cookie file with new accessToken and refreshToken')
                sys.exit(1)
    
    async def handle_response(self):
        try:
            if self.response['code'] == '0000' and self.response is not None:
                bz_a = self.response['data']['accessToken']
                bz_r = self.response['data']['refreshToken']
                self.bz_a, self.bz_r = bz_a, bz_r
                if await self.update_default_cookie() is True:
                    return True
                else:
                    logger.warning('Fail update default.txt cookie file with new accessToken and refreshToken')
                    return True
            else:
                logger.error('Fail change password')
                return None, None
        except TypeError as e:
            logger.error(e)
            sys.exit(1)