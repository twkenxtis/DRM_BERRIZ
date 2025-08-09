import asyncio
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from unit.handle_choice import handle_choice


def setup_logging() -> logging.Logger:
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("main")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "main.py.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)

    app_logger.addHandler(console_handler)
    app_logger.addHandler(app_file_handler)
    return app_logger


logger = setup_logging()


try:
    final_selection = asyncio.run(handle_choice())
except KeyboardInterrupt:
    pass
except Exception as e:
    logger.critical(f"Main program execution error: {e}", exc_info=True)
