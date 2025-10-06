import os
from pprint import pprint
from pathlib import Path

from rich.console import Console

class Route:
    def __init__(self):
        mainpath = Path(__file__)
        self.berrizconfig: Path = mainpath.parent.parent.joinpath('config', 'berrizconfig.yaml')
        self.default_cookie: Path = mainpath.parent.parent.joinpath("cookies", "Berriz", "default.txt")
        self.temp_cookie: Path = mainpath.parent.parent.joinpath("cookies", "cookie_temp.json")
        self.DB_FILE: Path = mainpath.parent.parent.joinpath("key", "local_key_vault.db")
        self.YAML_path: Path = mainpath.parent.parent.joinpath('config', 'berrizconfig.yaml')
        self.mp4decrypt_path: Path = mainpath.parent.parent.joinpath("lib", "tools", "mp4decrypt.exe")
        self.packager_path: Path = mainpath.parent.parent.joinpath("lib", "tools","packager-win-x64.exe")
        self.mkvmerge_path: Path = mainpath.parent.parent.joinpath("lib", "tools","mkvmerge.exe")
        self.BASE_ARTIS_KEY_DICT: Path = mainpath.parent.parent.joinpath("static", "artis_keys.json")
        self.download_info_pkl: Path = mainpath.parent.parent.joinpath("lock", "download_info.pkl")
        self.BASE_COMMUNITY_KEY_DICT = mainpath.parent.parent.joinpath("static", "community_keys.json")
        self.BASE_COMMUNITY_NAME_DICT = mainpath.parent.parent.joinpath("static", "community_name.json")


if __name__ == '__main__':
    route = Route()
    console = Console()
    console.print(route.berrizconfig)
    