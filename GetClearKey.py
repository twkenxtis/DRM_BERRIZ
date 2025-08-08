import logging
import os
from LARLEY_PR.playready import PlayReadyDRM

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def get_clear_key(pssh_input, acquirelicenseassertion_input):
    device_path = r"LARLEY_PR\\pyplayready\\device\\realtek_semiconductor_corp_coolnewdevice_xr-700_sl2000.prd"
    drm = None
    try:
        drm = PlayReadyDRM(device_path)
        key = drm.get_license_key(pssh_input, acquirelicenseassertion_input)
        if key:
            logging.info(f"License key: {key}")
            return key
        logging.error("Failed to retrieve license key")
        return None
    except Exception as e:
        logging.error(f"Exception while retrieving license key: {e}")
        return None
    finally:
        if drm:
            try:
                drm.close()
            except:
                pass 