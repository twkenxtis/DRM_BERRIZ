import gzip
import shutil
import logging
import os
import re
import yaml
import threading
import concurrent.futures
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from logging import LogRecord, Formatter, Logger, StreamHandler
from typing import Any, Optional


from static.color import Color



YAML_PATH: Path = Path('config') / 'berrizconfig.yaml'
try:
    with open(YAML_PATH, 'r', encoding='utf-8') as f:
        CFG: dict[str, Any] = yaml.safe_load(f)
except FileNotFoundError:
    # 若檔案遺失，回落到最小設定
    CFG = {'logging': {'level': 'INFO', 'format': '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'}}
    print(f"警告：設定檔案未在 {YAML_PATH} 找到，使用預設值", file=__import__('sys').stderr)


LOGGING_LEVEL = CFG['logging']['level']
LOGGING_FORMAT = CFG['logging']['format']



class NonBlockingFileHandler(TimedRotatingFileHandler):
    """使用執行緒池的非阻塞輪轉檔案處理器，支援備份壓縮"""

    _executor: concurrent.futures.ThreadPoolExecutor
    _lock: threading.Lock

    def __init__(self, *args: Any, compress: bool = True, **kwargs: Any) -> None:
        self.compress = compress
        super().__init__(*args, **kwargs)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="log_writer")
        self._lock = threading.Lock()

    def emit(self, record: LogRecord) -> None:
        """在主執行緒中格式化並非同步提交寫入"""
        try:
            # 在主執行緒中格式化
            msg = self.format(record)
            self._executor.submit(self._sync_write, record, msg)
        except Exception as e:
            # 回落到 stderr
            import sys
            print(f"日誌 emit 錯誤：{e}", file=sys.stderr)

    def _sync_write(self, record: LogRecord, message: str) -> None:
        """若需要則執行輪轉，然後寫入"""
        try:
            with self._lock:
                # 檢查並輪轉若必要（使用父類邏輯）
                if self.shouldRollover(record):
                    self.doRollover()

                # 寫入當前流（處理輪轉檔案名稱）
                self.stream.write(message + '\n')
                self.stream.flush()
        except Exception as e:
            import sys
            print(f"日誌寫入錯誤：{e}", file=sys.stderr)

    def doRollover(self) -> None:
        """覆寫以支援壓縮：輪轉後壓縮舊檔案"""
        super().doRollover()  # 先執行標準輪轉

        if not self.compress:
            return

        # 找到最新輪轉的舊檔案（通常是 baseFilename + .YYYY-MM-DD）
        base_path = Path(self.baseFilename)
        suffix_pattern = re.compile(r'\.(\d{4}-\d{2}-\d{2})$')
        old_files = [f for f in base_path.parent.glob(f"{base_path.stem}.log.*") if suffix_pattern.search(f.name)]
        
        if old_files:
            # 取最新一個
            latest_old = max(old_files, key=os.path.getmtime)
            gz_path = latest_old.with_suffix(latest_old.suffix + '.gz')
            
            try:
                # 使用 gzip 壓縮
                with open(latest_old, 'rb') as f_in:
                    with gzip.open(gz_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                # 刪除原始未壓縮檔案
                latest_old.unlink()
            except Exception as e:
                import sys
                print(f"壓縮備份錯誤：{e}", file=sys.stderr)

    def close(self) -> None:
        try:
            self._executor.shutdown(wait=True)
            if hasattr(self, 'stream') and self.stream:
                self.stream.close()
        except Exception:
            pass
        super().close()



class ColoredConsoleFormatter(Formatter):
    """自訂格式化器，根據等級套用顏色，無內部駭客；log_color 用於模組名稱顏色"""

    def __init__(self, fmt: str | None = None, log_color: Optional[str] = None, *args: Any, **kwargs: Any) -> None:
        if fmt is None:
            fmt = LOGGING_FORMAT  # 使用設定格式作為基礎
        super().__init__(fmt, *args, **kwargs)
        self.log_color = log_color

    def format(self, record: LogRecord) -> str:
        # 取得無顏色的基礎格式化訊息
        plain_msg = super().format(record)

        level = record.levelname
        name = record.name
        message = record.getMessage()

        # 根據等級決定顏色
        if level == "INFO":
            level_color = Color.fg('light_gray')
            msg_color = Color.fg('light_gray')
        elif level == "WARNING":
            level_color = Color.fg('gold')
            msg_color = Color.fg('gold')
        elif level in ["ERROR", "CRITICAL"]:
            level_color = Color.bg('dark_honey')
            msg_color = Color.fg('ruby')
        else:  # DEBUG 等
            level_color = ""
            msg_color = ""

        # 模組名稱顏色：僅用 log_color
        name_color = Color.fg(self.log_color) if self.log_color and self.log_color != "auto" else ""

        # 手動建構帶顏色的格式：[LEVEL] [name] message
        time_color = Color.fg('light_gray')
        asctime = getattr(record, 'asctime', '')
        time_part = f"{time_color}{asctime} " if asctime else ""

        formatted = (
            f"{time_part}"
            f"{msg_color}[{level_color}{level}{Color.reset()}{msg_color}] "
            f"{name_color}[{name}]{Color.reset()} "
            f"{msg_color}{message}{Color.reset()}"
        )

        return formatted



class NoColorFormatter(Formatter):
    """為檔案輸出移除 ANSI 顏色"""

    ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def format(self, record: LogRecord) -> str:
        message = super().format(record)
        return self.ANSI_RE.sub('', message)



def setup_logging(name: str, log_color: str = None) -> Logger:
    """設定日誌記錄器與處理器；log_color 用於模組名稱顏色（例如 'gold'）"""
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOGGING_LEVEL.upper(), logging.INFO))

    if logger.handlers:
        logger.handlers.clear()
    logger.propagate = False

    # 主控臺處理器帶顏色，傳遞 log_color
    console_handler = StreamHandler()
    console_handler.setFormatter(ColoredConsoleFormatter(log_color=log_color))
    logger.addHandler(console_handler)

    # 非阻塞檔案處理器，啟用壓縮
    file_handler = NonBlockingFileHandler(
        filename=Path("logs") / f"{name}.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        compress=True,
    )
    file_handler.setFormatter(NoColorFormatter(LOGGING_FORMAT))
    logger.addHandler(file_handler)

    return logger
