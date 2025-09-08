# v1.1.1
import asyncio

from static.args import had_key, clean_dl, skip_merge, fanclub, nofanclub, community, _artis, time_date
from unit.handle_choice import handle_choice
from unit.handle_log import setup_logging
from unit.parameter import paramstore
from unit.community import get_community, get_community_print
from unit.data import process_time_inputs 

logger = setup_logging('main', 'orange')

parameter = {}
if had_key():
    paramstore._store["key"] = True

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

try:
    if _artis():
        a = asyncio.run(get_community(_artis()))
        community_id = a
    if not community():
        asyncio.run(handle_choice(community_id, time_a, time_b))
    else:
        asyncio.run(get_community_print())
except KeyboardInterrupt:
    raise SystemExit(0)
except Exception as e:
    logger.critical(f"Main program execution error: {e}", exc_info=True)
