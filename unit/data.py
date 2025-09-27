import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from dateutil import parser as dateutil_parser

KST = timezone(timedelta(hours=9))

class FlexibleDateParser:
    def __init__(self, tz_offset_hours: int = 9, enable_fuzzy: bool = True):
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

    def _is_date_only_format(self, fmt: str) -> bool:
        return fmt in {"%Y%m%d", "%y%m%d", "%Y年%m月%d日"}

    def parse(self, dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None

        raw_str = dt_str.strip()
        raw_str = re.sub(r'[年月日]', '-', raw_str)
        raw_str = re.sub(r'\s+', ' ', raw_str)

        for fmt, length in self.patterns:
            try:
                if length and len(re.sub(r'\D', '', raw_str)) != length:
                    continue
                dt_obj = datetime.strptime(raw_str, fmt)
                # 不在此處補時間，由外層邏輯依 最早時間/最晚時間 決定補 00:00 或 23:59
                return dt_obj.replace(tzinfo=self.tz, microsecond=0)
            except ValueError:
                continue

        if self.enable_fuzzy:
            try:
                dt_obj = dateutil_parser.parse(raw_str)
                # 若沒有 tzinfo，補預設 KST
                if dt_obj.tzinfo is None:
                    dt_obj = dt_obj.replace(tzinfo=self.tz)
                return dt_obj.replace(microsecond=0)
            except (ValueError, TypeError):
                pass

        return None


def _coerce_now_if_none(dt: Optional[datetime]) -> datetime:
    return dt if dt is not None else datetime.now(tz=KST).replace(microsecond=0)

def _strip_to_kst(dt: datetime) -> datetime:
    # 確保有 KST，並移除微秒
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST).replace(microsecond=0)

def _date_only(dt: datetime) -> bool:
    return dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0

def process_time_inputs() -> Tuple[datetime, datetime]:
    parser = FlexibleDateParser()

    print("Please enter the first date and time string:")
    dt_str1 = input()
    print("Please enter the second date and time string (optional):")
    dt_str2 = input()

    if not dt_str1 and not dt_str2:
        raise ValueError("The two input date strings cannot be empty at the same time")

    dt1 = parser.parse(dt_str1) if dt_str1 else None
    dt2 = parser.parse(dt_str2) if dt_str2 else None

    # 若空值，以「現在(KST)」補上
    dt1 = _coerce_now_if_none(dt1)
    dt2 = _coerce_now_if_none(dt2)

    # 標準化為 KST、去微秒
    dt1 = _strip_to_kst(dt1)
    dt2 = _strip_to_kst(dt2)

    # 先暫存是否 原始輸入為單純日期 的判斷依據：
    # 規則：若原始解析沒有時間成分（或視為 00:00:00），視為 date-only
    # 此處以「時間為 00:00:00」作為近似判斷，解析階段未主動補時間
    date_only_1 = _date_only(dt1)
    date_only_2 = _date_only(dt2)

    # 先排序，確保 start <= end
    start, end = sorted([dt1, dt2])

    # 依需求補時間：
    # - 若 start 是 date-only，補 00:00
    # - 若 end 是 date-only，補 23:59
    # 注意：排序後，date-only 標記需要隨者對應到的物件重新匹配
    # 重新推導：如果排序後的 start 等於原 dt1，則沿用 date_only_1；否則用 date_only_2
    start_was_dt1 = (start == dt1)
    start_is_date_only = date_only_1 if start_was_dt1 else date_only_2
    end_is_date_only = date_only_2 if start_was_dt1 else date_only_1

    if start_is_date_only:
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if end_is_date_only:
        end = end.replace(hour=23, minute=59, second=0, microsecond=0)

    # 保證順序（理論上仍然成立）
    if start > end:
        start, end = end, start

    # 最終以 最早 最晚 順序回傳
    return (start, end)
