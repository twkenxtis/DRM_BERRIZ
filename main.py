# v1.3
import asyncio
import sys

from lib.account.berriz_create_community import community_join, leave_community_main
from static.args import (
    had_key, clean_dl, skip_merge, fanclub, nofanclub,
    community, group, time_date, had_nocookie,
    join_community, leave_community, change_password,
    dev, board, show_help, mediaonly, liveonly, photoonly,
    noticeonly, hls_only_dl, skip_mux
)
from static.color import Color
from static.help import print_help
from unit.parameter import paramstore
from unit.handle_log import setup_logging
from lib.account.change_pawword import Change_Password


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

from unit.handle_choice import Handle_Choice
from unit.community import get_community, get_community_print
from unit.data.data import process_time_inputs 

if time_date():
    time_a, time_b = process_time_inputs()
else:
    time_a, time_b = None, None

async def run_communoty_join(j):
    if await community_join(j) is True:
        return
    else:
        raise RuntimeError(f'Fail to join community {j}')

async def run_leave_communoty(j):
    if await leave_community_main(j) is True:
        return
    else:
        raise RuntimeError(f'Fail to join community {j}')

async def main():
    try:
        if change_password():
            if await Change_Password().change_password() is True:
                pass
            else:
                raise RuntimeError('Something fail')
        if group():
            community_id = await get_community(group())
            if community_id is None:
                logger.error(
                    f"{Color.fg('ruby')}Input Community ID invaild{Color.reset()}"
                    f" → {Color.fg('gold')}【{group()}】"
                    )
                logger.info(
                    f"{Color.fg('sea_green')}Use {Color.fg('gold')}--community {Color.fg('sea_green')}for more info!{Color.reset()}"
                    )
                await get_community_print()
                sys.exit(1)

        j = await get_community(join_community())
        if join_community():
            await run_communoty_join(j)
        if leave_community():
            await run_leave_communoty(j)
        if not community():
            await Handle_Choice(community_id, time_a, time_b).handle_choice()
        else:
            await get_community_print()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Main program execution error: {e}", exc_info=True)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    logger.info(f"{Color.fg('orange')}Program interrupted by user{Color.reset()}")