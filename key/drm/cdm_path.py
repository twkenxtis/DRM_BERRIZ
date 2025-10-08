from pathlib import Path

class CDM_PATH:
    def __init__(self, CFG: dict):
        self.prd_device_path: str = Path(__file__).parent.parent.joinpath("drm\\device\\" + CFG['CDM']['playready'])
        self.wv_device_path: str = Path(__file__).parent.parent.joinpath("drm\\device\\" + CFG['CDM']['widevine'])
