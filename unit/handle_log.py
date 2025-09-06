import concurrent.futures
import logging
import os
import re
import threading

from logging.handlers import TimedRotatingFileHandler

from static.color import Color


class NonBlockingFileHandler(TimedRotatingFileHandler):
    """使用線程池執行器實現非阻塞寫入"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="log_writer"
        )
        self._lock = threading.Lock()

    def emit(self, record):
        """在線程池中執行文件寫入"""
        try:
            msg = self.format(record)
            # 在線程池中執行寫入操作（非阻塞）
            self._executor.submit(self._sync_write, msg)
        except Exception as e:
            print(f"Log transmission error: {e}")

    def _sync_write(self, message):
        """同步寫入方法（在線程中執行）"""
        try:
            with self._lock:
                with open(self.baseFilename, "a", encoding=self.encoding) as f:
                    f.write(message + "\n")
        except Exception as e:
            print(f"File write error: {e}")

    def close(self):
        """關閉處理器"""
        try:
            self._executor.shutdown(wait=True)
        except:
            pass
        super().close()


def setup_logging(name, log_color) -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    os.makedirs("logs", exist_ok=True)

    # 控制台格式（包含顏色）
    console_format = logging.Formatter(
        f"{Color.fg('light_gray')}%(asctime)s [%(levelname)s] [%(name)s]: %(message)s {Color.reset()}"
    )

    # 文件格式（去除所有顏色代碼）
    class NoColorFormatter(logging.Formatter):
        def format(self, record):
            message = super().format(record)
            color_pattern = r"(\033\[[0-9;]*m|Color\.\w+\([^)]*\)|Color\.reset\(\))"
            return re.sub(color_pattern, "", message)

    file_format = NoColorFormatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    logger = logging.getLogger(f"{Color.fg(f'{log_color}')}{name}{Color.reset()}")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    logger.propagate = False

    # 控制台處理器（帶顏色）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    async_file_handler = NonBlockingFileHandler(
        filename=f"logs/{name}.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    async_file_handler.setFormatter(file_format)
    logger.addHandler(async_file_handler)

    return logger
