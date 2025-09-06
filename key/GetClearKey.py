from LARLEY_PR.playready import PlayReadyDRM
from static.color import Color
from unit.handle_log import setup_logging


logger = setup_logging('GetClearKey', 'honeydew')


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
