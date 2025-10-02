import asyncio
from typing import Dict

from cookies.cookies import Berriz_cookie


class Lock_Cookie:
    """一個用於異步獲取並鎖定 Cookie 會話的類別"""
    
    @staticmethod
    async def cookie_session() -> Dict[str, str]:
        """異步獲取 Berriz 的 cookies"""
        return await Berriz_cookie().get_cookies()

cookie_session: Dict[str, str] = asyncio.run(Lock_Cookie.cookie_session())