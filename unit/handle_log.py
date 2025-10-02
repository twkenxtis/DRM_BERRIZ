import concurrent.futures
import logging
import os
import re
import threading
from logging.handlers import TimedRotatingFileHandler
from logging import LogRecord, Formatter, Logger, StreamHandler
from typing import Any, Pattern


from static.color import Color


class NonBlockingFileHandler(TimedRotatingFileHandler):
    """使用線程池執行器實現非阻塞寫入"""

    _executor: concurrent.futures.ThreadPoolExecutor
    _lock: threading.Lock

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # TimedRotatingFileHandler.__init__ 的參數較多且常透過 kwargs 傳入
        super().__init__(*args, **kwargs)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="log_writer"
        )
        self._lock = threading.Lock()

    def emit(self, record: LogRecord) -> None:
        """在線程池中執行文件寫入"""
        try:
            # self.format(record) 返回 str
            msg: str = self.format(record)
            # 在線程池中執行寫入操作（非阻塞）
            self._executor.submit(self._sync_write, msg)
        except Exception as e:
            # 這裡的 print 語句是為了在傳輸失敗時提供反饋
            print(f"Log transmission error: {e}")

    def _sync_write(self, message: str) -> None:
        """同步寫入方法（在線程中執行）"""
        try:
            with self._lock:
                # self.baseFilename, self.encoding 來自 TimedRotatingFileHandler
                with open(self.baseFilename, "a", encoding=self.encoding) as f:
                    f.write(message + "\n")
        except Exception as e:
            print(f"File write error: {e}")

    def close(self) -> None:
        """關閉處理器"""
        try:
            self._executor.shutdown(wait=True)
        except:
            # 捕獲並忽略 shutdown 期間的潛在錯誤
            pass
        super().close()


# 自定義控製臺格式化器，根據等級使用不同顏色
class ColoredConsoleFormatter(Formatter):
    # format 接受 LogRecord 物件，返回格式化後的字串
    def format(self, record: LogRecord) -> str:
        # 根據等級選擇顏色
        level_color: str
        message_color: str
        
        if record.levelname == "INFO":
            level_color = Color.fg('light_gray')
            message_color = Color.fg('light_gray')
        elif record.levelname == "WARNING":
            level_color = Color.fg('gold')
            message_color = Color.fg('gold')
        elif record.levelname in ["ERROR", "CRITICAL"]:
            level_color = Color.bg('coral')
            message_color = Color.fg('black')
        else:  # DEBUG 和其他等級
            level_color = ""
            message_color = ""

        # 構建格式化字符串
        formatted: str = (f"{Color.fg('light_gray')}%(asctime)s "
                          f"{level_color}[%(levelname)s] "
                          f"{Color.fg('light_gray')}[%(name)s]: "
                          f"{message_color}%(message)s"
                          f"{Color.reset()}")

        # 臨時設置格式並呼叫父類方法
        # 這裡訪問 self._style._fmt 是 logging.Formatter 的內部細節，使用 type: ignore 避免靜態檢查錯誤
        original_fmt: str = self._style._fmt # type: ignore [attr-defined]
        self._style._fmt = formatted # type: ignore [attr-defined]
        result: str = super().format(record)
        self._style._fmt = original_fmt # type: ignore [attr-defined]
        
        return result


# setup_logging 接受兩個 str 參數，返回 logging.Logger 實例
def setup_logging(name: str, log_color: str) -> Logger:
    """Set up logging with console and rotating file handlers."""
    # 確保 logs 目錄存在
    os.makedirs("logs", exist_ok=True)

    # 控製臺格式（根據等級使用不同顏色）
    console_format: ColoredConsoleFormatter = ColoredConsoleFormatter()

    # 文件格式化器（去除所有顏色代碼）
    class NoColorFormatter(Formatter):
        # format 接受 LogRecord 物件，返回格式化後的字串
        def format(self, record: LogRecord) -> str:
            message: str = super().format(record)
            # 使用 re.compile 讓 Pattern 更有彈性
            color_pattern: Pattern[str] = re.compile(r"(\033\[[0-9;]*m|Color\.\w+\([^)]*\)|Color\.reset\(\))")
            return color_pattern.sub("", message)

    file_format: NoColorFormatter = NoColorFormatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    logger: Logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 確保不重複添加 Handler
    if logger.handlers:
        logger.handlers.clear()

    # 避免日誌傳播到 root logger
    logger.propagate = False

    # 控製臺 Handler
    console_handler: StreamHandler = logging.StreamHandler()
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # 非阻塞檔案 Handler
    async_file_handler: NonBlockingFileHandler = NonBlockingFileHandler(
        filename=f"logs/{name}.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    async_file_handler.setFormatter(file_format)
    logger.addHandler(async_file_handler)

    return logger