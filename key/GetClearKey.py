from static.color import Color
from unit.handle_log import setup_logging
from LARLEY_PR.playready import PlayReadyDRM
from WVD.widevine import WidevineDRM
from key.watora import Watora_wv
from key.cdrm import CDRM


logger = setup_logging('GetClearKey', 'honeydew')


prd_device_path = r"LARLEY_PR\\pyplayready\\device\\realtek_semiconductor_corp_coolnewdevice_xr-700_sl2000.prd"
wv_device_path = r"WVD\\device\\google_aosp_on_ia_emulator_14.0.0_13cea62a_4464_l3.wvd"

async def get_clear_key(pssh_input, acquirelicenseassertion_input, drm_type):
    
    drm = drm_choese(drm_type)
    logger.info(
        f"{Color.fg('light_gray')}use {Color.fg('plum')}{drm_type}{Color.reset()} "
        f"{Color.fg('light_gray')}to get clear key{Color.reset()} "
        f"{Color.fg('light_gray')}assertion:{Color.reset()} "
        f"{Color.fg('periwinkle')}{acquirelicenseassertion_input}{Color.reset()}"
        )
    try:
        key = await drm.get_license_key(pssh_input, acquirelicenseassertion_input)
        if key:
            logger.info(f"Request new key: {Color.fg('gold')}{key}{Color.reset()}")
            return key
        logger.error("Failed to retrieve license key")
        return None
    except Exception as e:
        logger.error(f"Exception while retrieving license key: {e}")
        raise
    finally:
        if drm:
            try:
                drm.close()
            except:
                pass

def drm_choese(drm_type):
    if drm_type == 'mspr':
        drm = PlayReadyDRM(prd_device_path)
    elif drm_type == 'wv':
        drm = WidevineDRM(wv_device_path)
    elif drm_type == 'watora_wv':
        drm = Watora_wv()
    elif drm_type == 'cdrm_wv':
        drm = CDRM()
    elif drm_type == 'cdrm_mspr':
        drm = CDRM()
    else:
        drm = WidevineDRM(wv_device_path)
    return drm