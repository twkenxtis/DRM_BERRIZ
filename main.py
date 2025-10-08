# v1.3
import asyncio
import sys

from typing import Union, Optional

import rich.traceback

from lib.account.berriz_create_community import BerrizCreateCommunity
from unit.community.community import custom_dict
from static.args import (
    had_key, clean_dl, skip_merge, fanclub, nofanclub,
    community, group, time_date, had_nocookie,
    join_community, leave_community, change_password,
    dev, board, show_help, mediaonly, liveonly, photoonly,
    noticeonly, hls_only_dl, skip_mux, signup
)
from static.color import Color
from static.help import print_help
from static.parameter import paramstore
from unit.handle.handle_log import setup_logging
from lib.account.change_pawword import Change_Password
from lib.account.signup import run_signup


rich.traceback.install()


logger = setup_logging('main', 'orange')


if show_help():
    print_help()
    sys.exit(0)

parameter = {}

if had_key():
    paramstore._store["key"] = True

if dev():
    paramstore._store["notify_mod"] = True

if had_nocookie():
    paramstore._store["no_cookie"] = True

if clean_dl() is False:
    paramstore._store["clean_dl"] = False

if skip_merge() is True:
    paramstore._store["skip_merge"] = True
    
if skip_mux() is True:
    paramstore._store["skip_mux"] = True

if fanclub():
    paramstore._store["fanclub"] = True
    
if nofanclub():
    paramstore._store["fanclub"] = False
    
if mediaonly():
    paramstore._store["mediaonly"] = True
else:
    paramstore._store["mediaonly"] = False
    
if liveonly():
    paramstore._store["liveonly"] = True
else:
    paramstore._store["liveonly"] = False

if photoonly():
    paramstore._store["photoonly"] = True
else:
    paramstore._store["photoonly"] = False

if noticeonly():
    paramstore._store["noticeonly"] = True
else:
    paramstore._store["noticeonly"] = False

if board():
    paramstore._store["board"] = True
else:
    paramstore._store["board"] = False
    
if hls_only_dl():
    paramstore._store["hls_only_dl"] = True
else:
    paramstore._store["hls_only_dl"] = False

if signup():
    try:
        asyncio.run(run_signup())
    except KeyboardInterrupt:
        logger.info(f"Program interrupted: {Color.fg('light_gray')}User canceled{Color.reset()}")
        sys.exit(0)
    
from unit.handle.handle_choice import Handle_Choice
from unit.community.community import get_community, get_community_print
from unit.data.data import process_time_inputs 


if time_date():
    time_a, time_b = process_time_inputs()
else:
    time_a, time_b = None, None

async def cm(input: Union[str, int]):
    community = await get_community(input)
    if community is None:
        logger.error(
            f"{Color.fg('ruby')}Input Community ID invaild{Color.reset()}"
            f" → {Color.fg('gold')}【{input}】"
            )
        logger.info(
            f"{Color.fg('sea_green')}Use {Color.fg('gold')}--community {Color.fg('sea_green')}for more info!{Color.reset()}"
            )
        await get_community_print()
        sys.exit(1)
    else:
        return community

async def main():
    if change_password():
        if await Change_Password().change_password() is True:
            pass
        else:
            raise RuntimeError('Something fail')
    if join_community():
        await BerrizCreateCommunity(await cm(join_community()), join_community()).community_join()
    if leave_community():
        await BerrizCreateCommunity(await cm(leave_community()), leave_community()).leave_community_main()
    if not community():
        community_id, communityname = await BerrizCreateCommunity(await cm(group()), group()).community_id_name()
        custom_name: Optional[str] = await custom_dict(communityname)
        logger.info(
            f"{Color.fg('spring_green')}Community:"
            f"{Color.reset()}［{Color.fg('turquoise')}{custom_name}{Color.reset()}］"
        )
        await Handle_Choice(community_id, communityname, time_a, time_b).handle_choice()
    else:
        await get_community_print()

try:
    asyncio.run(main())
except KeyboardInterrupt as e:
    if str(e) == "":
        logger.info(f"Program interrupted: {Color.fg('light_gray')}User canceled{Color.reset()}")
    else:
        logger.warning(f"Program interrupted: {Color.fg('light_gray')}{e}{Color.reset()}")