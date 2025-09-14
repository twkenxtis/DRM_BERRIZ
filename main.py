# v1.1.1
import asyncio

from lib.account.berriz_create_community import community_join, leave_community_main
from static.args import (
    had_key, clean_dl, skip_merge, fanclub, nofanclub,
    community, _artis, time_date, had_nocookie,
    join_community, leave_community, change_password
)
from unit.parameter import paramstore
from unit.handle_log import setup_logging
from lib.account.change_pawword import Change_Password

logger = setup_logging('main', 'orange')


parameter = {}
if had_key():
    paramstore._store["key"] = True

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

if time_date():
    time_a, time_b = process_time_inputs()
else:
    time_a, time_b = None, None

from unit.handle_choice import handle_choice
from unit.community import get_community, get_community_print
from unit.data import process_time_inputs 


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
    if _artis():
        a = asyncio.run(get_community(_artis()))
        community_id = a
    if join_community():
        j = asyncio.run(get_community(join_community()))
        asyncio.run(run_communoty_join(j))
    if leave_community():
        j = asyncio.run(get_community(leave_community()))
        asyncio.run(run_leave_communoty(j))
    if not community():
        asyncio.run(handle_choice(community_id, time_a, time_b))
    else:
        asyncio.run(get_community_print())
except KeyboardInterrupt:
    raise SystemExit(0)
except Exception as e:
    logger.critical(f"Main program execution error: {e}", exc_info=True)