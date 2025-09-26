import functools

from static.color import Color
from unit.http.request_berriz_api import Community
from unit.handle_log import setup_logging


logger = setup_logging('community', 'ivory')


PRELOADED_COMMUNITIES = [
    {'communityId': 1, 'communityKey': 'jsh'},
    {'communityId': 2, 'communityKey': 'kiiikiii'},
    {'communityId': 3, 'communityKey': 'crushology101'},
    {'communityId': 4, 'communityKey': 'monstax'},
    {'communityId': 5, 'communityKey': 'iu'},
    {'communityId': 6, 'communityKey': 'cravity'},
    {'communityId': 7, 'communityKey': 'ive'},
    {'communityId': 8, 'communityKey': 'idid'},
    {'communityId': 9, 'communityKey': 'wjsn'},
    {'communityId': 10, 'communityKey': 'woodz'},
    {'communityId': 11, 'communityKey': 'tempest'},
    {'communityId': 12, 'communityKey': 'ke_actors_audition'},
    {'communityId': 13, 'communityKey': 'theballadofus'},
    {'communityId': 804223749, 'communityKey': 'prod_test1'},
    {'communityId': 814223749, 'communityKey': 'prod_test2'},
    {'communityId': 824223749, 'communityKey': 'prod_test3'},
    {'communityId': 834223749, 'communityKey': 'prod_test4'},
    {'communityId': 844223749, 'communityKey': 'prod_test5'},
    {'communityId': 854223749, 'communityKey': 'prod_test6'},
    {'communityId': 887888888, 'communityKey': 'prod_test_tempest'},
    {'communityId': 888888888, 'communityKey': 'prod_test_iu'},
    {'communityId': 934223749, 'communityKey': 'prod_test'},
    {'communityId': 6888888888, 'communityKey': 'prod_test_berriz'},
    {'communityId': 8888348888, 'communityKey': 'prod_test_sm'},
    {'communityId': 8888358888, 'communityKey': 'prod_test_sm_riize'},
    {'communityId': 8888368888, 'communityKey': 'prod_test_sm_aespa'},
]

def async_cache(maxsize=256):
    cache = {}

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args):
            if args in cache:
                return cache[args]
            result = await func(*args)
            if len(cache) >= maxsize:
                cache.pop(next(iter(cache)))
            cache[args] = result
            return result
        return wrapper
    return decorator

def search_community(contents, query):
    if query is None:
        return contents

    try:
        query_id = int(query)
        for item in contents:
            if item.get("communityId") == query_id:
                return item.get("communityKey")
    except ValueError:
        pass

    normalized = str(query).strip().lower()
    for item in contents:
        if item.get("communityKey", "").lower() == normalized:
            return item.get("communityId")

    return None

def custom_dict(input_str):
    mapping = {
        'jsh': 'Jung Seung Hwan',
        'monstax': 'MONSTA X',
        'iu': 'IU',
        'kiiikiii': 'KiiiKiii',
        'ive': 'IVE',
        'cravity': 'CRAVITY',
        'idid': 'IDID',
        'wjsn': 'WJSN',
        'woodz': 'WOODZ',
        'tempest': 'Tempest'
    }

    # 建立反向對應表
    reverse_mapping = {v.lower(): k for k, v in mapping.items()}

    normalized = input_str.strip().lower()

    # 先查原始 key → value，再查反向 value → key
    return mapping.get(normalized) or reverse_mapping.get(normalized)
    
@async_cache(maxsize=256)
async def get_community(query: str | int | None = None):
    # 先查本地預設資料
    result = search_community(PRELOADED_COMMUNITIES, query)
    if isinstance(result, str):
        name = custom_dict(result) or result
        logger.info(
            f"{Color.fg('spring_green')}Community: "
            f"{Color.reset()}［{Color.fg('turquoise')}{name}{Color.reset()}］"
                    )
        return result.strip()
    if result is not None:
        return result

    # 查不到再發 API
    data = await Community().community_keys()
    if data.get("code") != '0000':
        return None

    contents = data.get("data", {}).get("contents", [])
    result = search_community(contents, query)
    if isinstance(result, str):
        logger.info(
            f"{Color.fg('spring_green')}Community: "
            f"{Color.reset()}［{Color.fg('turquoise')}{result}{Color.reset()}］"
                    )    
        return result.strip()
    return result

async def get_community_print():
    data = await Community().community_keys()
    if data.get("code") != '0000':
        return None
    data = data.get("data", {}).get("contents", [])
    for i in data:
        Community_id = i.get("communityId")
        communityKey = i.get("communityKey")
        logger.info(f"{Color.fg('light_gray')}Community_id: "
              f"{Color.fg('steel_blue')}{Community_id}, "
              f"{Color.fg('light_gray')}communityKey: "
              f"{Color.fg('plum')}{communityKey}"
              )
