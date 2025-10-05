import asyncio
from typing import Any, Dict, List, Optional

from rich.table import Table
from rich.console import Console
from rich import box

from static.color import Color
from lib.lock_cookie import cookie_session, Lock_Cookie
from unit.handle.handle_log import setup_logging
from unit.http.request_berriz_api import My

logger = setup_logging('parse_my', 'ruby')

MY = My()


async def request_my() -> None:
    """
    異步請求多個使用者相關的 API 端點，處理 Cookie，並記錄解析後的個人資訊
    """
    if not cookie_session:
        await Lock_Cookie.cookie_session()

    try:
        results = await asyncio.gather(
            MY.fetch_my(),
            MY.fetch_location(),
            MY.notifications(),
            MY.fetch_me(),
            MY.get_me_info(),
            return_exceptions=True
        )
        
        if any(isinstance(r, Exception) for r in results):
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"API call {i} failed: {result}")
            return
        
        data, locat, notif, my_data, me = results
        if None in (data, locat, notif, my_data, me):
            logger.warning("One or more API calls returned None")
            return
        
        my_id: Optional[str] = data.get('data', {}).get('memberInfo', {}).get('memberKey')
        my_email: Optional[str] = data.get('data', {}).get('memberInfo', {}).get('memberEmail')
        location: Optional[str] = locat.get('data', {}).get('countryCode')
        
        me_info_1: Dict[str, Any] = my_data.get('data', {})
        memberKey: Optional[str] = me_info_1.get('memberKey')
        email: Optional[str] = me_info_1.get('email')
        passwordRegistered: Optional[bool] = me_info_1.get('passwordRegistered')
        passwordMismatchCount: Optional[int] = me_info_1.get('passwordMismatchCount')
        status: Optional[str] = me_info_1.get('status')
        createdAt: Optional[str] = me_info_1.get('createdAt')
        updatedAt: Optional[str] = me_info_1.get('updatedAt')
        
        me_info_2: Dict[str, Any] = me.get('data', {})
        email2: Optional[str] = me_info_2.get('email')
        contactEmail: Optional[str] = me_info_2.get('contactEmail')
        country: Optional[str] = me_info_2.get('country')
        phoneNumber: Optional[str] = me_info_2.get('phoneNumber')
        
        join_community: List[Dict[str, Any]] = notif.get('data', {}).get('contents', [])
        keys: List[str] = [
            key for item in join_community 
            if (key := item.get("communityKey")) is not None
        ]
        
        console = Console()

        table = Table(title="", show_header=False, box=box.ROUNDED, border_style="bright_blue")

        table.add_row("[bright_white]Login to[/]", f"[red]{my_id}[/]")
        table.add_row("[sky_blue1]Mail[/]", f"[light_sky_blue1]{my_email}[/]")
        table.add_row("[bright_magenta]Location[/]", f"[yellow]{location}[/]")

        table.add_row("[orange1]memberKey[/]", f"[navajo_white1]{memberKey}[/]")
        table.add_row("[medium_purple1]email[/]", f"[plum1]{email}[/]")
        table.add_row("[gold3]passwordRegistered[/]", f"[light_yellow]{passwordRegistered}[/]")
        table.add_row("[light_salmon1]passwordMismatchCount[/]", f"[orange3]{passwordMismatchCount}[/]")
        table.add_row("[light_steel_blue]status[/]", f"[light_goldenrod1]{status}[/]")
        table.add_row("[medium_spring_green]createdAt[/]", f"[light_sky_blue1]{createdAt}[/]")
        table.add_row("[deep_pink3]updatedAt[/]", f"[medium_purple]{updatedAt}[/]")

        table.add_row("[light_sea_green]email (me_info_2)[/]", f"[red3]{email2}[/]")
        table.add_row("[dark_orange3]contactEmail[/]", f"[light_cyan]{contactEmail}[/]")
        table.add_row("[light_sky_blue3]country[/]", f"[gold1]{country}[/]")
        table.add_row("[medium_orchid]phoneNumber[/]", f"[light_goldenrod2]{phoneNumber}[/]")

        console.print(table)

        if keys:
            logger.info(f"{Color.fg('gray')}My joined community: {Color.fg('pink')}{' | '.join(keys)}")
            
    except Exception as e:
        logger.error(f"Unexpected error in request_my: {e}", exc_info=True)
        raise  # Re-raise if critical
