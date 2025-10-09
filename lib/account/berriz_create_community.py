import asyncio
import sys

from typing import Optional, Dict, Any, Union, Tuple

from lib.__init__ import use_proxy
from static.color import Color
from static.api_error_handle import api_error_handle
from unit.http.request_berriz_api import Community
from unit.handle.handle_log import setup_logging


logger = setup_logging('berriz_create_community', 'peacock')


class BerrizCreateCommunity:
    def __init__(self, communityinput1: Union[int, str], communityinput2: Union[int, str]) -> None:
        communityinput1: Optional[int]
        communityinput2: Optional[str]
        self.communityinput1 = communityinput1
        self.communityinput2 = communityinput2
        self.Community: Community = Community()

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
        community_id, communityname = await self.community_id_name()
        name: str
        while True:
            logger.info(f"{Color.fg('light_gray')}try join to {Color.fg('aquamarine')}{communityname}{Color.reset()}")
            name = input(f"{Color.fg('light_yellow')}Please enter name for your {Color.fg('aquamarine')}[{communityname}]{Color.fg('light_yellow')} community's nickname:{Color.reset()} ").strip()
            
            if len(name) > 15:
                logger.warning(f'{name} community name only accept length < 15')
            else:
                break

        data: Dict[str, Any] = await self.Community.create_community(community_id, name, use_proxy)
        code :str = data.get('code')
        if code == '0000':
            logger.info(f'{Color.fg("light_gray")}Welcome to {Color.fg("aquamarine")}{communityname} {Color.fg("light_gray")}community{Color.reset()}')
            if 'data' in data and isinstance(data['data'], dict):
                self.print_data_with_fstring(data['data'])
            raise KeyboardInterrupt('exit program')
        elif code != '0000':
            logger.error(f"{api_error_handle(code)}")
            logger.error(f"{Color.fg('red')}Failed to join the {Color.fg('aquamarine')}{communityname} {Color.fg('light_gray')}community.{Color.reset()}")
            raise KeyboardInterrupt('exit program')
        else:
            logger.error(data)
            logger.error(f"{Color.fg('red')}Failed to join the {Color.fg('aquamarine')}{communityname} {Color.fg('light_gray')}community.{Color.reset()}")
            raise KeyboardInterrupt('exit program')


    async def leave_community_main(self) -> bool:
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
                
        data: Dict[str, Any] = await self.Community.leave_community(community_id, use_proxy)
        code :str = data.get('code')
        if code == '0000':
            logger.info(
                f"{Color.fg('rose')}Successfully left the "
                f"{Color.fg('aquamarine')}{communityname} {Color.fg('light_gray')}"
                f"community.{Color.reset()}"
            )
            raise KeyboardInterrupt('exit program')
        elif code != '0000':
            logger.error(f"{api_error_handle(code)}")
            logger.error(f"{Color.fg('red')}Failed to leave the {Color.fg('aquamarine')}{communityname} {Color.fg('light_gray')}community.{Color.reset()}")
            raise KeyboardInterrupt('exit program')
        else:
            logger.error(data)
            logger.error(f"{Color.fg('red')}Failed to leave the {Color.fg('aquamarine')}{communityname} {Color.fg('light_gray')}community.{Color.reset()}")
            raise KeyboardInterrupt('exit program')
            