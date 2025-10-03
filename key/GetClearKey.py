from static.color import Color
from unit.handle_log import setup_logging
from pathlib import Path
from typing import Optional, List, Union, Any

# DRM modules
from key.cdrm import CDRM
from key.watora import Watora_wv
from LARLEY_PR.playready import PlayReadyDRM
from WVD.widevine import WidevineDRM
from lib.load_yaml_config import CFG
from key.drm.cdm_path import CDM_PATH

logger = setup_logging('GetClearKey', 'honeydew')


# 定義一個聯合型別，代表所有可能的 DRM 類別實例
DRM_Client = Union[PlayReadyDRM, WidevineDRM, Watora_wv, CDRM]

# 設置日誌記錄器
logger = setup_logging('GetClearKey', 'honeydew')

# 定義設備路徑變數的型別
cdm_path = CDM_PATH(CFG)
prd_device_path: str = cdm_path.prd_device_path
wv_device_path: str = cdm_path.wv_device_path

# get_clear_key 是一個異步函式，回傳值為 List[str]（Clear Key 列表）或 None
async def get_clear_key(pssh_input: str, acquirelicenseassertion_input: str, drm_type: str) -> Optional[List[str]]:
    
    # drm_choese 返回 Union[DRM_Client]
    drm: DRM_Client = drm_choese(drm_type)
    
    logger.info(
        f"{Color.fg('light_gray')}use {Color.fg('plum')}{drm_type}{Color.reset()} "
        f"{Color.fg('light_gray')}to get clear key{Color.reset()} "
        f"{Color.fg('light_gray')}assertion:{Color.reset()} "
        f"{Color.fg('periwinkle')}{acquirelicenseassertion_input}{Color.reset()}"
        )
    try:
        # 假設 get_license_key 返回 Optional[List[str]]
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
                # 假設所有 DRM 實例都有 close() 方法
                drm.close() # type: ignore [attr-defined] # 忽略 MyPy 對 close() 方法存在的檢查
            except:
                pass

# drm_choese 函式回傳 DRM_Client 的實例
def drm_choese(drm_type: str) -> DRM_Client:
    # 局部變數 drm 的型別
    drm: DRM_Client
    
    if drm_type == 'mspr':
        drm = PlayReadyDRM(prd_device_path)
    elif drm_type == 'wv':
        drm = WidevineDRM(wv_device_path)
    elif drm_type == 'watora_wv':
        # 假設 Watora_wv() 不需要參數
        drm = Watora_wv()
    elif drm_type == 'cdrm_wv':
        # 假設 CDRM() 不需要參數
        drm = CDRM()
    elif drm_type == 'cdrm_mspr':
        drm = CDRM()
    else:
        drm = WidevineDRM(wv_device_path)
        
    return drm