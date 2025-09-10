import re
from datetime import datetime, timedelta, timezone

from typing import List, Optional, Tuple

from dateutil import parser as dateutil_parser


class FlexibleDateParser:
    def __init__(self, default_hour: int = 23, default_minute: int = 59, default_second: int = 0,
                 tz_offset_hours: int = 9, enable_fuzzy: bool = True):
        self.default_time = (default_hour, default_minute, default_second)
        self.tz = timezone(timedelta(hours=tz_offset_hours))
        self.enable_fuzzy = enable_fuzzy
        self.patterns: List[Tuple[str, Optional[int]]] = [
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

    def parse(self, dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None

        raw_str = dt_str.strip()
        raw_str = re.sub(r'[年月日]', '-', raw_str)
        raw_str = re.sub(r'\s+', ' ', raw_str)

        # 嘗試所有格式
        for fmt, length in self.patterns:
            try:
                if length and len(re.sub(r'\D', '', raw_str)) != length:
                    continue
                dt_obj = datetime.strptime(raw_str, fmt)
                if fmt in ["%Y%m%d", "%y%m%d", "%Y年%m月%d日"]:
                    dt_obj = dt_obj.replace(hour=self.default_time[0],
                                            minute=self.default_time[1],
                                            second=self.default_time[2])
                return dt_obj.replace(tzinfo=self.tz, microsecond=0)
            except ValueError:
                continue

        # 最後嘗試模糊解析
        if self.enable_fuzzy:
            try:
                dt_obj = dateutil_parser.parse(raw_str)
                return dt_obj.replace(tzinfo=self.tz, microsecond=0)
            except (ValueError, TypeError):
                pass

        return None

def process_time_inputs() -> Tuple[datetime, datetime]:
    parser = FlexibleDateParser()
    """接收兩組使用者輸入的日期時間字串，並處理成 datetime 物件"""
    print("請輸入第一組日期時間字串：")
    dt_str1 = input()
    print("請輸入第二組日期時間字串 (可選)：")
    dt_str2 = input()
    
    if not dt_str1 and not dt_str2:
        raise ValueError("兩個輸入日期字串不能同時為空")

    dt_obj1 = parser.parse(dt_str1)
    dt_obj2 = parser.parse(dt_str2)

    # 如果其中一個輸入為空，則用當前時間補上
    if not dt_str1:
        dt_obj1 = datetime.now()
    if not dt_str2:
        dt_obj2 = datetime.now()

    # 統一處理：在返回前移除所有 datetime 物件的微秒
    if dt_obj1:
        dt_obj1 = dt_obj1.replace(microsecond=0)
    if dt_obj2:
        dt_obj2 = dt_obj2.replace(microsecond=0)
        
    kst = timezone(timedelta(hours=9))

    if dt_obj1:
        dt_obj1 = dt_obj1.replace(microsecond=0, tzinfo=kst)
    if dt_obj2:
        dt_obj2 = dt_obj2.replace(microsecond=0, tzinfo=kst)

    return (dt_obj1, dt_obj2)