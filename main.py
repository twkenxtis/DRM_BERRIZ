# v1.4
import asyncio
import sys

from typing import Optional

import rich.traceback

from lib.account.berriz_create_community import BerrizCreateCommunity
from unit.community.community import custom_dict
from lib.click_types import *
from static.help import print_help
from static.color import Color
from unit.handle.handle_log import setup_logging


rich.traceback.install()


logger = setup_logging('main', 'orange')


from unit.handle.handle_choice import Handle_Choice
from unit.community.community import get_community_print
from unit.date.date import process_time_inputs 


if time_date():
    time_a, time_b = process_time_inputs()
else:
    time_a, time_b = None, None


async def main():
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
        
if __name__ == '__main__':
    if show_help():
        print_help()
        sys.exit(0)
        
    try:
        asyncio.run(main())
    except KeyboardInterrupt as e:
        if str(e) == "":
            logger.info(f"Program interrupted: {Color.fg('light_gray')}User canceled{Color.reset()}")
        else:
            logger.warning(f"Program interrupted: {Color.fg('light_gray')}{e}{Color.reset()}")
    except RuntimeError as e:
        if str(e) == 'Event loop is closed':
            logger.warning(
                f"Program interrupted: "
                f"{Color.fg('light_gray')}Event loop is closed re-run the program.{Color.reset()}"
                )
            asyncio.run(main())
        else:
            raise e