import sys
from typing import List, Dict, Any, Optional, Union

import aiofiles
import orjson

from lib.__init__ import use_proxy
from lib.path import Path
from static.color import Color
from static.route import Route
from unit.http.request_berriz_api import Community, My
from unit.handle.handle_log import setup_logging


logger = setup_logging('community', 'ivory')


# 定義社羣字典的結構別名
CommunityDict = Dict[str, Union[int, str]]


BASE_COMMUNITY_KEY_DICT: Path = Route().BASE_COMMUNITY_KEY_DICT
BASE_COMMUNITY_NAME_DICT: Path = Route().BASE_COMMUNITY_NAME_DICT


async def cm(input: Union[str, int]):
    community = await get_community(input)
    if community is None:
        logger.error(
            f"{Color.fg('black')}Input Community ID invaild{Color.reset()}"
            f" → {Color.fg('gold')}【{input}】"
            )
        logger.info(
            f"{Color.fg('sea_green')}Use {Color.fg('gold')}--community {Color.fg('sea_green')}for more info!{Color.reset()}"
            )
        await get_community_print()
        sys.exit(1)
    else:
        return community
    

async def file_Check() -> None:
    if not BASE_COMMUNITY_KEY_DICT.exists():
        async with aiofiles.open(BASE_COMMUNITY_KEY_DICT, 'w') as f:
            await f.write(orjson.dumps([]).decode('utf-8'))

    if not BASE_COMMUNITY_NAME_DICT.exists():
        async with aiofiles.open(BASE_COMMUNITY_NAME_DICT, 'w') as f:
            await f.write(orjson.dumps({}).decode('utf-8'))

def search_community(contents: List[CommunityDict], query: Union[str, int, None]) -> Union[str, int, None]:
    if query is None:
        return None
    query = int(query) if isinstance(query, str) and query.isdigit() else query
    logger.debug(f"{Color.fg('gold')}search_community {query}, {type(query)}{Color.reset()}")
    if isinstance(query, str):
        q = query.strip().lower()
        for item in contents:
            key = item.get("communityKey", "").lower()
            if q == key:
                return item.get("communityId")

    elif isinstance(query, int):
        for item in contents:
            if item.get("communityId") == query:
                return item.get("communityKey")
    return None

# custom_dict 的回傳值可以是 str (對應的 key/value) 或 None
async def custom_dict(input_str: Union[str, int]) -> Optional[str]:
    await file_Check()
    mapping: Dict[str, str] = {}
    try:
        async with aiofiles.open(BASE_COMMUNITY_NAME_DICT, 'rb') as f:
            contents = await f.read()
            mapping: Dict[str, str] = orjson.loads(contents)
    except orjson.JSONDecodeError:
        pass

    normalized: Optional[str[int]] = input_str.strip().lower()
    data = mapping.get(str(normalized))
    
    if data is None:
        match normalized:
            case 'crushology101':
                return 'Crushology 101'
            case 'tempest':
                return 'Tempest'
            case 'ke_actors_audition':
                return '2025 Kakao Ent. Actors Audition'
            case 'theballadofus':
                return 'The Ballad of Us'
            case _:
                merged_dict = {}
                try:
                    resp: dict = await My().fetch_home(use_proxy)
                    if resp.get("code") != '0000':
                        return None
                except AttributeError:
                    return None
                for i in resp['data']['active']:
                    name = i['title']
                    communityId = str(i['communityId'])
                    communityKey = str(i['communityKey'])
                    kv = {communityKey: name, communityId: name}
                    merged_dict.update(kv)
                async with aiofiles.open(BASE_COMMUNITY_NAME_DICT, 'wb') as f:
                    await f.write(orjson.dumps(merged_dict, option=orjson.OPT_INDENT_2))
                data = merged_dict.get(normalized) 
    return data
    
# get_community 的回傳值是 str (communityKey) 或 int (communityId) 或 None
async def get_community(query: Union[str, int, None] = None) -> Union[str, int, None]:
    await file_Check()
    try:
        async with aiofiles.open(BASE_COMMUNITY_KEY_DICT, 'rb') as f:
            contents = await f.read()
            PRELOADED_COMMUNITIES = orjson.loads(contents)
    except orjson.JSONDecodeError:
        PRELOADED_COMMUNITIES = [{}]
        pass
    # 先查本地預設資料
    result: Union[str, int, None] = search_community(PRELOADED_COMMUNITIES, query)
    if isinstance(result, str):
        return result.strip()
    if result is not None:
        # 如果 result 是 int (communityId)
        return result
    # 查不到再發 API
    data = await request_community_community_keys()
    if data == {}: return None

    contents: List[CommunityDict] = data.get("data", {}).get("contents", [])
    async with aiofiles.open(BASE_COMMUNITY_KEY_DICT, 'wb') as f:
        await f.write(orjson.dumps(contents, option=orjson.OPT_INDENT_2))

    result = search_community(contents, query)
    
    if isinstance(result, str):
        logger.info(
            f"{Color.fg('spring_green')}Community: "
            f"{Color.reset()}［{Color.fg('turquoise')}{result}{Color.reset()}］"
                        )    
        return result.strip()
    # 回傳 int (communityId) 或 None
    return result

async def get_community_print() -> None:
    data = await request_community_community_keys()
    if data == {}: return None
        
    contents: List[CommunityDict] = data.get("data", {}).get("contents", [])
    
    for i in contents:
        Community_id: Optional[int] = i.get("communityId")
        communityKey: Optional[str] = i.get("communityKey")
        logger.info(f"{Color.fg('light_gray')}Community_id: "
                    f"{Color.fg('steel_blue')}{Community_id}, "
                    f"{Color.fg('light_gray')}communityKey: "
                    f"{Color.fg('plum')}{communityKey}"
                    )
        
async def request_community_community_keys() -> Dict[str, Any]:
    try:
        data: Dict[str, Any] = await Community().community_keys(use_proxy)
        if data.get("code") == '0000':
            return data
    except AttributeError:
        return {}