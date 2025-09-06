# v1.1.1
import asyncio

from static.args import had_key, clean_dl, skip_merge
from unit.handle_choice import handle_choice
from unit.handle_log import setup_logging
from unit.parameter import paramstore

logger = setup_logging('main', 'orange')

parameter = {}
community_id = 7

if had_key():
    paramstore._store["key"] = True

if clean_dl() is False:
    paramstore._store["clean_dl"] = False

if skip_merge() is True:
    paramstore._store["skip_merge"] = True

try:
    asyncio.run(handle_choice(community_id))
except KeyboardInterrupt:
    pass
except Exception as e:
    logger.critical(f"Main program execution error: {e}", exc_info=True)
