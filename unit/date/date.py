import re
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateutil_parser
from typing import List, Optional, Tuple

from inputimeout import inputimeout, TimeoutOccurred

from static.color import Color
from lib.load_yaml_config import CFG, ConfigLoader
from unit.handle.handle_log import setup_logging

logger = setup_logging('data', 'soft_coral')


def get_time_zone(yaml_config = CFG['TimeZone']['time']) -> str:
    return yaml_config

tz_offset_hours = get_time_zone()

# 定義時區常數的型別
KST: timezone = timezone(timedelta(hours=tz_offset_hours))

# 定義模式元組的型別別名
DatePattern = Tuple[str, Optional[int]]

class FlexibleDateParser:
    tz: timezone
    enable_fuzzy: bool
    patterns: List[DatePattern]

    def __init__(self, enable_fuzzy: bool = True) -> None:
        self.tz: timezone = timezone(timedelta(hours=tz_offset_hours))
        self.enable_fuzzy: bool = enable_fuzzy
        self.patterns: List[DatePattern] = [
            ("%Y%m%d%H%M%S", 14),
            ("%Y%m%d%H%M", 12),
            ("%y%m%d%H%M", 10),
            ("%Y%m%d", 8),
            ("%y%m%d", 6),
            ("%Y-%m-%d %H:%M:%S", None),
            ("%Y/%m/%d %H:%M:%S", None),
            ("%Y-%m-%d %I:%M %p", None),
            ("%Y/%m/%d %I:%M %p", None),
            ("%Y.%m.%d-%H:%M:%S", None),
            ("%Y_%m_%d__%H%M%S", None),
            ("%Y年%m月%d日", None),
        ]

    def _is_date_only_format(self, fmt: str) -> bool:
        return fmt in {"%Y%m%d", "%y%m%d", "%Y年%m月%d日"}

    def parse(self, dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None

        raw_str: str = dt_str.strip()
        # re.sub 的替換結果是字串
        raw_str = re.sub(r'[年月日]', '-', raw_str)
        raw_str = re.sub(r'\s+', ' ', raw_str)

        for fmt, length in self.patterns:
            try:
                # re.sub(r'\D', '', raw_str) 的結果是字串
                if length and len(re.sub(r'\D', '', raw_str)) != length:
                    continue
                
                # datetime.strptime 返回 datetime 物件
                dt_obj: datetime = datetime.strptime(raw_str, fmt)
                # 不在此處補時間，由外層邏輯依 最早時間/最晚時間 決定補 00:00 或 23:59
                return dt_obj.replace(tzinfo=self.tz, microsecond=0)
            except ValueError:
                continue

        if self.enable_fuzzy:
            try:
                # dateutil_parser.parse 返回 datetime 物件
                dt_obj = dateutil_parser.parse(raw_str)
                
                # 若沒有 tzinfo，補預設 YAML
                if dt_obj.tzinfo is None:
                    dt_obj = dt_obj.replace(tzinfo=self.tz)
                return dt_obj.replace(microsecond=0)
            except (ValueError, TypeError):
                pass

        return None


# 輔助函式的型別提示
def _coerce_now_if_none(dt: Optional[datetime]) -> datetime:
    # datetime.now(tz=KST).replace(microsecond=0) 返回 datetime
    return dt if dt is not None else datetime.now(tz=KST).replace(microsecond=0)

def _strip_to_kst(dt: datetime) -> datetime:
    # 確保有 KST，並移除微秒
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    # dt.astimezone(KST).replace(microsecond=0) 返回 datetime
    return dt.astimezone(KST).replace(microsecond=0)

def _date_only(dt: datetime) -> bool:
    return dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0

# 主要處理函式的型別提示
def process_time_inputs(time: str) -> Tuple[datetime, datetime]:
    try:
        parser: FlexibleDateParser = FlexibleDateParser()

        dt_str1 = str(time)
        
        try:
            dt_str2: str = ""
            logger.info('[Optional] by default using datetime now can press enter to skip')
            dt_str2 = inputimeout(prompt="Please enter the second date (optional) [accept any format]: ", timeout=7)
        except TimeoutOccurred:
            pass
        except KeyboardInterrupt:
            logger.info(f"Program interrupted: {Color.fg('light_gray')}User canceled{Color.reset()}")

        if not dt_str1 and not dt_str2:
            logger.error("Both input date strings cannot be empty at the same time")
            raise ValueError("empty input.")

        dt1: Optional[datetime] = parser.parse(dt_str1) if dt_str1 else None
        dt2: Optional[datetime] = parser.parse(dt_str2) if dt_str2 else None

        dt1 = _coerce_now_if_none(dt1)
        dt2 = _coerce_now_if_none(dt2)

        # 標準化為 KST、去微秒
        dt1 = _strip_to_kst(dt1)
        dt2 = _strip_to_kst(dt2)

        # 先暫存是否 原始輸入為單純日期 的判斷依據：
        # 規則：若原始解析沒有時間成分（或視為 00:00:00），視為 date-only
        # 此處以「時間為 00:00:00」作為近似判斷，解析階段未主動補時間
        date_only_1: bool = _date_only(dt1)
        date_only_2: bool = _date_only(dt2)

        # 先排序，確保 start <= end
        # sorted 返回一個包含兩個 datetime 物件的 List[datetime]
        sorted_dts: List[datetime] = sorted([dt1, dt2])
        start: datetime = sorted_dts[0]
        end: datetime = sorted_dts[1]

        # 依需求補時間：
        # - 若 start 是 date-only，補 00:00
        # - 若 end 是 date-only，補 23:59
        # 注意：排序後，date-only 標記需要隨者對應到的物件重新匹配
        # 重新推導：如果排序後的 start 等於原 dt1，則沿用 date_only_1；否則用 date_only_2
        start_was_dt1: bool = (start == dt1)
        start_is_date_only: bool = date_only_1 if start_was_dt1 else date_only_2
        end_is_date_only: bool = date_only_2 if start_was_dt1 else date_only_1

        if start_is_date_only:
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if end_is_date_only:
            end = end.replace(hour=23, minute=59, second=0, microsecond=0)

        # 保證順序（理論上仍然成立）
        if start > end:
            start, end = end, start

        # 最終以 最早 最晚 順序回傳
        return (start, end)
    except ValueError as e:
        logger.error(f"Error: {e}")
        raise KeyboardInterrupt(e)
    except Exception as e:
        logger.error(f"An unknown error occurred: {e}")
        raise KeyboardInterrupt(e)

class TimeHandler:
    def __init__(self, utc_timestamp_str:str) -> str:
        self.utc_timestamp_str = utc_timestamp_str

    def convert_utc_to_offset_time(self, offset_hours: str, fmt: str) -> str:
        if isinstance(offset_hours, str):
            offset_hours = int(offset_hours)
        """
        將 ISO 8601 格式的 UTC 時間戳記轉換為指定時區偏移量的時間

        Args:
            utc_timestamp_str: 待轉換的 UTC 時間字串 (例如: '2025-09-30T07:30:00Z')
            offset_str: 目標時區的偏移量字串 (例如: '+8', '+09', '-5')

        Returns:
            轉換後的當地時間字串，格式為 'YYYY-MM-DD HH:MM:SS'，或返回錯誤訊息
        """
        # 建立 timedelta 物件，用於時間加減
        time_delta = timedelta(hours=offset_hours)
        
        # 2. 解析 UTC 時間
        try:
            # 為了讓 datetime.fromisoformat 成功解析 'Z' 結尾的字串，將 'Z' 替換為 '+00:00'
            utc_dt_aware = datetime.fromisoformat(
                self.utc_timestamp_str.replace("Z", "+00:00")
            )
            
            # 3. 執行時區轉換
            target_dt = utc_dt_aware + time_delta

            # 4. 格式化輸出
            return target_dt.strftime(get_timestamp_formact(fmt))

        except ValueError as e:
            return f"Error: Incorrect or unparseable input time string format. Please ensure it's ISO 8601 (e.g., '2025-09-30T07:30:00Z'). Details: {e}"
        except Exception as e:
            return f"An unknown error occurred: {e}"


VALID_DATETIME_CODES = {
    "%Y", "%y", "%m", "%d",  # 年月日
    "%H", "%I", "%M", "%S", "%f",  # 時分秒微秒
    "%z", "%Z",  # 時區
    "%j", "%U", "%W",  # 年內日數與週數
    "%G", "%u", "%V"   # ISO 年週
}


def get_timestamp_formact(fmt) -> str:
    """Get a compact timestamp string for filenames, e.g. '250813_14-52_16'"""
    
    if has_valid_datetime_format(fmt) is True:
        return fmt
    else:
        logger.error(f"Wrong datetime formact → {fmt}")
        logger.info("Auto choese datetime formact → %y%m%d_%H-%M")
        return '%y%m%d_%H-%M'

def has_valid_datetime_format(fmt: str) -> bool:
    matches = re.findall(r"%[a-zA-Z]", fmt)
    return any(code in VALID_DATETIME_CODES for code in matches)

def get_formatted_publish_date(published_at: str, fmt :str) -> Optional[str]:
    """回傳格式化後的發布日期字串"""
    _brisbane_offset = get_time_zone()
    try:
        if _brisbane_offset is None:
            raise ValueError("TimeZone is None")
        elif isinstance(_brisbane_offset, int):
            int_brisbane_offset = _brisbane_offset
            brisbane_offset = _brisbane_offset
        else:
            int_brisbane_offset = int(re.sub(r'(?i)|utc', '', _brisbane_offset).strip().lower())
            brisbane_offset = re.sub(r'(?i)utc', '', _brisbane_offset).strip().lower()
    except AttributeError:
        ConfigLoader.print_warning('Unsupported timezone', brisbane_offset, "UTC+9")
        brisbane_offset = 9
    if not (-12 <= int_brisbane_offset <= 14):
        ConfigLoader.print_warning('TimeZone invaild should be -12 ~ +14', int_brisbane_offset, "UTC+9")
        brisbane_offset = 9
    if published_at:
        dt:str = TimeHandler(published_at).convert_utc_to_offset_time(brisbane_offset, fmt)
        return dt
    return None