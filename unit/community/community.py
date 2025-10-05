import functools
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple, Callable

import aiofiles
import orjson

from static.color import Color
from unit.http.request_berriz_api import Community, My
from unit.handle.handle_log import setup_logging


logger = setup_logging('community', 'ivory')


# 定義社羣字典的結構別名
CommunityDict = Dict[str, Union[int, str]]


BASE_COMMUNITY_KEY_DICT = Path('static') / 'community_keys.json'
BASE_COMMUNITY_NAME_DICT = Path('static') /'community_name.json'


async def file_Check() -> None:
    if not BASE_COMMUNITY_KEY_DICT.exists():
        async with aiofiles.open(BASE_COMMUNITY_KEY_DICT, 'w') as f:
            await f.write(orjson.dumps([]).decode('utf-8'))

    if not BASE_COMMUNITY_NAME_DICT.exists():
        async with aiofiles.open(BASE_COMMUNITY_NAME_DICT, 'w') as f:
            await f.write(orjson.dumps({}).decode('utf-8'))

# 定義 async_cache 裝飾器的回傳型別，它是一個接受函式並返回函式的函式
Decorator = Callable[[Callable[..., Any]], Callable[..., Any]]

def async_cache(maxsize: int = 13) -> Decorator:
    # 緩存的鍵是 Tuple (args)，值是 Any (函式的回傳值)
    cache: Dict[Tuple[Any, ...], Any] = {}

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any) -> Any:
            # 由於裝飾的是一個非同步函式，所以 wrapper 必須是 async
            if args in cache:
                return cache[args]
                
            # 呼叫原始的非同步函式
            result: Any = await func(*args) 
            
            if len(cache) >= maxsize:
                # 移除最舊的項目 (第一個鍵)
                cache.pop(next(iter(cache)))
            
            cache[args] = result
            return result
            
        return wrapper
        
    return decorator

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
                    resp: dict = await My().fetch_home()
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
@async_cache(maxsize=256)
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
        # 假設 custom_dict 返回 str 或 None
        name: Optional[str] = await custom_dict(result) or result
        logger.info(
            f"{Color.fg('spring_green')}Community: "
            f"{Color.reset()}［{Color.fg('turquoise')}{name}{Color.reset()}］"
        )
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
        data: Dict[str, Any] = await Community().community_keys()
        if data.get("code") == '0000':
            return data
    except AttributeError:
        return {}