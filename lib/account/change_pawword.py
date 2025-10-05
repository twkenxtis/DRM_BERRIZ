import re
import sys
from typing import Optional, Dict, Any

from cookies.cookies import Refresh_JWT, Berriz_cookie
from static.color import Color
from mystate.parse_my import request_my
from unit.http.request_berriz_api import Password_Change
from unit.handle.handle_log import setup_logging


logger = setup_logging('change_pawword', 'magenta_pink')


_pw_re: re.Pattern[str] = re.compile(
    r'^'  # Start of string
    r'(?=.*[A-Za-z])'  # At least one letter
    r'(?=.*\d)'  # At least one digit
    r'(?=.*[!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])'  # At least one special character
    r'[\x20-\x7E]{8,32}'  # Printable ASCII characters, length 8-32
    r'$'  # End of string
)


class Change_Password:
    """
    處理密碼變更流程的管理器
    負責驗證密碼格式、發起 API 請求、處理響應和更新本地 Cookie 文件
    """
    def __init__(self) -> None:
        # 使用 Optional 標記可能為 None 的屬性
        self.response: Optional[Dict[str, Any]] = None
        self.bz_a: Optional[str] = None
        self.bz_r: Optional[str] = None
    
    def validate_password_regex(self, password: str) -> bool:
        """檢查密碼是否符合強度要求 (8-32字元, 包含字母, 數字, 特殊符號)"""
        return bool(_pw_re.match(password))
        
    async def change_password(self) -> Optional[bool]:
        """
        引導使用者輸入密碼並執行密碼變更 API 請求
        
        Returns:
            Optional[bool]: 密碼是否變更成功並完成 Cookie 更新
        """
        await request_my()
        
        try:
            currentPassword: str
            newPassword: str
            
            while True:
                logger.info(f"{Color.bg('dark_magenta')}Start password change{Color.reset()}")
                # 提示使用者輸入當前密碼
                currentPassword = input(
                    f"{Color.fg('light_gray')}enter {Color.fg('crimson')}current {Color.fg('light_gray')}password: {Color.reset()}"
                ).strip()
                # 提示使用者輸入新密碼
                newPassword = input(
                    f"{Color.fg('light_gray')}enter {Color.fg('crimson')}new {Color.fg('light_gray')}password: {Color.reset()}"
                ).strip()
                
                if not self.validate_password_regex(newPassword) or not self.validate_password_regex(currentPassword):
                    logger.warning('Your password must contain 8 to 32 alphanumeric and special characters')
                else:
                    break
            
            data: Optional[Dict[str, Any]] = await Password_Change().update_password(currentPassword, newPassword)
            
            if data is not None:
                self.response = data
                success: Optional[bool] = await self.handle_response()
                return success
            else:
                logger.error('API call returned None data when attempting to change password.')
                raise ValueError('API call failed or returned empty data.')
        except Exception as e:
            logger.error(f"An unexpected error occurred during password change: {e}", exc_info=True)
            return False
            
    async def update_default_cookie(self) -> bool:
        """使用新的 accessToken 和 refreshToken 更新本地 Cookie 文件"""
        if self.bz_a is None or self.bz_r is None:
            logger.error("Error: Tokens (bz_a or bz_r) are missing for cookie update.")
            return False

        if await Refresh_JWT().update_cookie_file(self.bz_a, self.bz_r):
            await Berriz_cookie.create_temp_json()
            await Berriz_cookie().get_cookies()
            logger.info("Successfully updated default cookie file.")
            return True
        else:
            logger.error('Fail to update default.txt cookie file with new accessToken and refreshToken')
            return False
    
    async def handle_response(self) -> Optional[bool]:
        """處理 API 響應，提取新的 token 並觸發 cookie 更新"""
        if self.response is None:
            logger.error("Attempted to handle a None response.")
            return False
            
        try:
            response_data: Dict[str, Any] = self.response
            
            if response_data.get('code') == '0000' and 'data' in response_data:
                data: Dict[str, Any] = response_data['data']
                
                # 提取並驗證 tokens
                bz_a: Optional[str] = data.get('accessToken')
                bz_r: Optional[str] = data.get('refreshToken')
                
                if isinstance(bz_a, str) and isinstance(bz_r, str):
                    self.bz_a = bz_a
                    self.bz_r = bz_r
                    
                    # 進行 Cookie 更新
                    if await self.update_default_cookie():
                        return True
                    else:
                        logger.warning('Password changed successfully, but local cookie file update failed.')
                        return True # 密碼變更 True
                else:
                    logger.error("API response missing or has invalid accessToken/refreshToken format.")
                    return False
            else:
                logger.error(f"Fail change password. API Response: {self.response}")
                return False
                
        except TypeError as e:
            logger.error(f"Error parsing API response structure: {e}", exc_info=True)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error in handle_response: {e}", exc_info=True)
            sys.exit(1)