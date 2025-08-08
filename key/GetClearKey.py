import os
import logging
from logging.handlers import TimedRotatingFileHandler

from LARLEY_PR.playready import PlayReadyDRM


def setup_logging() -> logging.Logger:
    """Set up logging with console and rotating file handlers."""
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
    )
    log_level = logging.INFO

    app_logger = logging.getLogger("GetClearKey")
    app_logger.setLevel(log_level)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    app_file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_directory, "GetClearKey.py.log"),
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


def get_clear_key(pssh_input, acquirelicenseassertion_input):
    device_path = r"LARLEY_PR\\pyplayready\\device\\realtek_semiconductor_corp_coolnewdevice_xr-700_sl2000.prd"
    drm = None
    try:
        drm = PlayReadyDRM(device_path)
        key = drm.get_license_key(pssh_input, acquirelicenseassertion_input)
        if key:
            logger.info(f"License key: {key}")
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
