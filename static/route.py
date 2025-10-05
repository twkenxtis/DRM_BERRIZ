import os
from pprint import pprint
from pathlib import Path

from rich.console import Console

class Route:
    def __init__(self):
        mainpath = Path(__file__)
        self.berrizconfig = mainpath.parent.parent.joinpath('config', 'berrizconfig.yaml')
        self.default_cookie = mainpath.parent.parent.joinpath("cookies", "Berriz", "default.txt")
        self.temp_cookie = mainpath.parent.parent.joinpath("cookies", "cookie_temp.json")

if __name__ == '__main__':
    route = Route()
    console = Console()
    console.print(route.berrizconfig)
    