import os
import logging
from logging.handlers import TimedRotatingFileHandler

from LARLEY_PR.playready import PlayReadyDRM
from static.color import Color


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    os.makedirs("logs", exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )

    logger = logging.getLogger("GetClearKey")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    logger.propagate = False

    # console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    # rotating file handler
    app_file_handler = TimedRotatingFileHandler(
        filename="logs/GetClearKey.py.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    app_file_handler.setFormatter(log_format)
    logger.addHandler(app_file_handler)

    return logger


logger = setup_logging()


def get_clear_key(pssh_input, acquirelicenseassertion_input):
    device_path = r"LARLEY_PR\\pyplayready\\device\\realtek_semiconductor_corp_coolnewdevice_xr-700_sl2000.prd"
    drm = None
    try:
        drm = PlayReadyDRM(device_path)
        key = drm.get_license_key(pssh_input, acquirelicenseassertion_input)
        if key:
            logger.info(f"Request new key: {Color.fg('gold')}{key}{Color.reset()}")
            return key
        logger.error("Failed to retrieve license key")
        return None
    except Exception as e:
        logger.error(f"Exception while retrieving license key: {e}")
        return None
    finally:
        if drm:
            try:
                drm.close()
            except:
                pass
