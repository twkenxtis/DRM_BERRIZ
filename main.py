# v1.3
import asyncio
import sys

from lib.account.berriz_create_community import community_join, leave_community_main
from static.args import (
    had_key, clean_dl, skip_merge, fanclub, nofanclub,
    community, group, time_date, had_nocookie,
    join_community, leave_community, change_password,
    dev, board, show_help, mediaonly, liveonly, photoonly
)
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

from unit.handle_choice import handle_choice
from unit.community import get_community, get_community_print
from unit.data import process_time_inputs 

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

try:
    if change_password():
        if asyncio.run(Change_Password().change_password()) is True:
            pass
        else:
            raise RuntimeError('Something fail')
    if group():
        a = asyncio.run(get_community(group()))
        community_id = a
    if join_community():
        j = asyncio.run(get_community(join_community()))
        asyncio.run(run_communoty_join(j))
    if leave_community():
        j = asyncio.run(get_community(leave_community()))
        asyncio.run(run_leave_communoty(j))
    if not community():
        if board():
            paramstore._store["board"] = True
            asyncio.run(handle_choice(community_id, time_a, time_b))
            sys.exit(0)
        else:
            paramstore._store["board"] = False
            asyncio.run(handle_choice(community_id, time_a, time_b))
            
    else:
        asyncio.run(get_community_print())
except KeyboardInterrupt:
    raise SystemExit(0)
except Exception as e:
    logger.critical(f"Main program execution error: {e}", exc_info=True)