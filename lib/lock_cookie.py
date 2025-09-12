import asyncio
from cookies.cookies import Berriz_cookie


class Lock_Cookie:
    async def cookie_session():
        return await Berriz_cookie().get_cookies()
cookie_session = asyncio.run(Lock_Cookie.cookie_session())