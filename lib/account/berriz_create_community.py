import asyncio
import sys

from typing import Optional, Dict, Any, Union, Tuple

from static.color import Color
from unit.community.community import get_community
from unit.http.request_berriz_api import Community
from unit.handle.handle_log import setup_logging


logger = setup_logging('berriz_create_community', 'chocolate')


class BerrizCreateCommunity:
    def __init__(self, communityinput1: Union[int, str], communityinput2: Union[int, str]) -> None:
        communityinput1: Optional[int]
        communityinput2: Optional[str]
        self.communityinput1 = communityinput1
        self.communityinput2 = communityinput2

    async def community_id_name(self) -> Tuple[Optional[int], Optional[str]]:
        community_id: Optional[int] = None
        communityname: Optional[str] = None
        if isinstance(self.communityinput1, int):
            community_id = self.communityinput1
            communityname = self.communityinput2
        else:
            community_id = self.communityinput2
            communityname = self.communityinput1
        return community_id, communityname

    def print_data_with_fstring(self, data: Dict[str, Any]) -> None:
        for key, value in data.items():
            logger.info(f"{Color.fg('violet')}{key}:  {Color.fg('pink')}{value}{Color.reset()}")

    async def community_join(self) -> bool:
        try:
            community_id, communityname = await self.community_id_name()
            name: str
            while True:
                logger.info(f"{Color.fg('light_gray')}try join to {Color.fg('aquamarine')}{communityname}{Color.reset()}")
                name = input(f"{Color.fg('light_yellow')}Please enter name for your {Color.fg('aquamarine')}[{communityname}]{Color.fg('light_yellow')} community's nickname:{Color.reset()} ").strip()
                
                if len(name) > 15:
                    logger.warning(f'{name} community name only accept length < 15')
                else:
                    break
                    
            data: Dict[str, Any] = await Community().create_community(community_id, name)
            
            if data.get('code') == '0000':
                logger.info(f'{Color.fg("light_gray")}Welcome to {Color.fg("aquamarine")}{communityname} {Color.fg("light_gray")}community{Color.reset()}')
                if 'data' in data and isinstance(data['data'], dict):
                    self.print_data_with_fstring(data['data'])
                return True
            else:
                code: str = str(data.get('code'))
                message: str = str(data.get('message', 'Unknown error'))
                
                if code == 'FS_CJ1011':
                    logger.info(
                        f"{Color.fg('gold')}{message}{Color.reset()} "
                        f"{Color.fg('light_gray')}in community "
                        f"{Color.fg('aquamarine')}{communityname}{Color.reset()}"
                    )
                    return True
                elif code == 'FS_CJ1017':
                    """"You cannot join again within 24 hours you leave"""
                    logger.warning(
                        f'{message} {Color.fg("light_gray")}→ '
                        f'{Color.fg("aquamarine")}{communityname} {Color.fg("light_gray")}community{Color.reset()}'
                    )
                    return True
                else:
                    logger.error(f"Fail to join {communityname}. Response data: {data}")
                    return False
        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except (EOFError, AttributeError, TypeError, ValueError):
            sys.exit(1)
        except Exception:
            return False

    async def leave_community_main(self) -> bool:
        try:
            community_id, communityname = await self.community_id_name()

            userinput: str
            while True:
                logger.info(f"{Color.fg('light_gray')}try leave to {Color.fg('aquamarine')}{communityname}{Color.reset()}")
                print(
                    f"{Color.bold()}{Color.fg('plum')}Note:\n{Color.reset()}"
                    f"{Color.fg('mint')}Leave this community?\n"
                    f"You won’t be able to edit or delete posts and comments made with this profile. "
                    f"Even if you rejoin, your previous activity cannot be restored.{Color.reset()}"
                )
                await asyncio.sleep(0.65)
                userinput = input(f'{Color.fg("gold")}typing YES to accept: {Color.reset()}').strip()
                
                if userinput == 'YES':
                    break
                elif userinput == 'yes':
                    logger.warning('Try typing in all caps')
                    
            data: Dict[str, Any] = await Community().leave_community(community_id)
            
            if data.get('code') == '0000':
                logger.info(
                    f"{Color.fg('rose')}Successfully left the "
                    f"{Color.fg('aquamarine')}{communityname} {Color.fg('light_gray')}"
                    f"community.{Color.reset()}"
                )
                return True
            else:
                code: str = str(data.get('code'))
                message: str = str(data.get('message', 'Unknown error'))
                
                if code == 'FS_CM1010':
                    logger.info(f"{Color.fg('light_gray')}{message}{Color.reset()}")
                    logger.info(f"{Color.fg('gold')}You are already leave {Color.fg('aquamarine')}{communityname}{Color.reset()}")
                    return True
                else:
                    logger.critical(f"Failed to leave community. Response data: {data}")
                    return False
                    
        except KeyboardInterrupt:
            raise KeyboardInterrupt
        except (EOFError, AttributeError, TypeError, ValueError):
            sys.exit(1)
        except Exception:
            return False