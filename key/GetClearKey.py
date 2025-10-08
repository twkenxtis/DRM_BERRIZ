from static.color import Color
from unit.handle.handle_log import setup_logging
from typing import Optional, List, Union

# DRM modules
from key.cdrm import CDRM
from key.watora import Watora_wv
from LARLEY_PR.playready import PlayReadyDRM
from WVD.widevine import WidevineDRM
from lib.load_yaml_config import CFG
from key.drm.cdm_path import CDM_PATH

logger = setup_logging('GetClearKey', 'honeydew')


DRM_Client = Union[PlayReadyDRM, WidevineDRM, Watora_wv, CDRM]


logger = setup_logging('GetClearKey', 'honeydew')


cdm_path = CDM_PATH(CFG)
prd_device_path: str = cdm_path.prd_device_path
wv_device_path: str = cdm_path.wv_device_path


async def get_clear_key(pssh_input: str, acquirelicenseassertion_input: str, drm_type: str) -> Optional[List[str]]:
    drm: DRM_Client = drm_choese(drm_type)
    
    logger.info(
        f"{Color.fg('light_gray')}use {Color.fg('plum')}{drm_type}{Color.reset()} "
        f"{Color.fg('light_gray')}to get clear key{Color.reset()} "
        f"{Color.fg('light_gray')}assertion:{Color.reset()} "
        f"{Color.fg('periwinkle')}{acquirelicenseassertion_input}{Color.reset()}"
        )
    try:
        key: Optional[List[str]] = await drm.get_license_key(pssh_input, acquirelicenseassertion_input)
        if key:
            # key 是 List[str]，將其連接成字串用於日誌輸出
            logger.info(f"Request new key: {Color.fg('gold')}{', '.join(key)}{Color.reset()}")
            return key
        logger.error("Failed to retrieve license key")
        return None
    except Exception as e:
        logger.error(f"Exception while retrieving license key: {e}")
        raise # 重新拋出異常
    finally:
        if drm:
            try:
                drm.close()
            except:
                pass

def drm_choese(drm_type: str) -> DRM_Client:
    drm: DRM_Client
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