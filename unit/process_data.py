import re
from datetime import date, datetime
from typing import Optional, Tuple, Union


class DateTimeProcessor:
    def __init__(self, dt_str1: Optional[str], dt_str2: Optional[str]):
        self.dt_str1 = dt_str1
        self.dt_str2 = dt_str2
        self.dt_obj1 = None
        self.dt_obj2 = None

    def process_dates(self) -> Tuple[datetime, datetime]:
        """處理兩個日期字串，並返回兩個 datetime 物件"""
        if not self.dt_str1 and not self.dt_str2:
            raise ValueError("Both input strings cannot be empty at the same time")

        self.dt_obj1 = self._parse_date(self.dt_str1)
        self.dt_obj2 = self._parse_date(self.dt_str2)

        # 如果其中一個輸入為空，則用當前時間補上
        if not self.dt_str1:
            self.dt_obj1 = datetime.now()
        if not self.dt_str2:
            self.dt_obj2 = datetime.now()

        if self.dt_obj1:
            self.dt_obj1 = self.dt_obj1.replace(microsecond=0)
        if self.dt_obj2:
            self.dt_obj2 = self.dt_obj2.replace(microsecond=0)

        return (self.dt_obj1, self.dt_obj2)

    def _parse_date(self, dt_str: Optional[str]) -> Optional[datetime]:
        """解析並轉換單個日期時間字串"""
        if not dt_str:
            return None

        # 嘗試直接解析 ISO 8601 格式
        try:
            return datetime.fromisoformat(dt_str)
        except (ValueError, TypeError):
            pass

        # 移除常見的分隔符號，**包含空格**
        clean_str = re.sub(r'[-_/. :]', '', dt_str)

        # 嘗試解析 yy/yymmdd 格式並補齊
        patterns = [
            ("%Y%m%d%H%M%S", 14),  # YYYYMMDDhhmmss
            ("%Y%m%d%H%M", 12),    # YYYYMMDDhhmm
            ("%y%m%d%H%M", 10),    # YYMMDDhhmm
            ("%Y%m%d", 8),         # YYYYMMDD
            ("%y%m%d", 6)          # YYMMDD
        ]

        for fmt, length in patterns:
            if len(clean_str) == length:
                try:
                    dt_obj = datetime.strptime(clean_str, fmt)
                    # 如果只有日期，補上時間 23:59:00
                    if length in [6, 8]:
                        return dt_obj.replace(hour=23, minute=59, second=0)
                    return dt_obj
                except ValueError:
                    pass

        return None