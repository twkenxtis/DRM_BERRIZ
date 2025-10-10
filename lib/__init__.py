import re
import unicodedata
import string
import shutil
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional

from lib.load_yaml_config import CFG, ConfigLoader
from lib.path import Path
from static.color import Color
from unit.handle.handle_log import setup_logging


logger = setup_logging('lib.__init__', 'fern')
executor = ThreadPoolExecutor()

class FilenameSanitizer:
    """Handles sanitization of filenames to remove invalid characters."""
    @staticmethod
    def sanitize_filename(name: str) -> str:
        # Unicode 標準化 (NFC 形式)
        name = unicodedata.normalize('NFC', name)
        
        # 移除非法字元（包含控製字元）
        name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', name)
        
        # 避免保留名稱（不分大小寫）
        reserved = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        if not name:
            return "_empty_file"
        base = name.split('.')[0].upper()
        if base in reserved:
            name = f"_{name}"
        return name
    

def get_container(yaml_container = CFG['Container']['video']) -> str:
    try:
        container = yaml_container.strip().lower().replace(".", "")
    except AttributeError:
        ConfigLoader.print_warning('Container', yaml_container, 'MKV')
        return 'mkv'

    if not container in ('ts, mp4, mov, m4v, mkv, avi'):
        logger.warning(f'invaild container {container}, auto choese mkv to communite!')
        return 'mkv'
    match CFG['Container']['mux']:
        case 'mkvtoolnix':
            return 'mkv'
        case _:
            return container
container = get_container()


def get_download_folder_name(yaml_container = CFG['Donwload_Dir_Name']['download_dir']) -> str:
    folder_name = FilenameSanitizer.sanitize_filename(yaml_container)
    return folder_name
dl_folder_name = get_download_folder_name()


def use_proxy_list(yaml_container = CFG['Proxy']['Proxy_Enable']) -> bool:
    return bool(yaml_container)
use_proxy = use_proxy_list()


class OutputFormatter:
    def __init__(self, template: str) -> None:
        self.template = template
        self.fields = self.extract_fields(template)

    def format(self, metadata: Dict[str, str]) -> str:
        safe_meta = {field: metadata.get(field, "") for field in self.fields}

        for field in [f for f in self.fields if f != "title"]:
            if field in self.fields and safe_meta.get(field, "") == "":
                self.template = self._remove_field_segment(self.template, field)

        result = self.template.format(**safe_meta)
        result = re.sub(r'\s+', ' ', result)
        return result

    def extract_fields(self, template: str) -> List[str]:
        formatter = string.Formatter()
        return [field_name for _, field_name, _, _ in formatter.parse(template) if field_name]

    def _remove_field_segment(self, template: str, field: str) -> str:
        # 移除連接符與欄位，包含前後空格
        pattern = rf"[\s\-._]*{{{field}}}[\s\-._]*"
        return re.sub(pattern, " ", template)


class File_date_time_formact:
    def __init__(self, folder_name: str, video_meta: dict) -> str:
        self.video_meta = video_meta
        self.folder_name = folder_name
        self.drn = CFG['Donwload_Dir_Name']['dir_name']
        self.oldfmt = CFG['Donwload_Dir_Name']['date_formact']
        self.newfmt = CFG['output_template']['date_formact']
        self.dt_str = self.video_meta.get("date", "")
        
    def new_dt(self) -> str:
        dt: datetime = datetime.strptime(self.dt_str, self.oldfmt)
        d:str = dt.strftime(self.newfmt)
        return d
    
    def new_file_name(self) -> str:
        new_dt = self.new_dt()
        video_meta: Dict[str, str] = {
            "date": new_dt,
            "title": self.video_meta.get("title", ""),
            "community_name": self.video_meta.get("community_name", ""),
            "artis": self.video_meta.get("artis", ""),
            "source": "Berriz",
            "tag": CFG['output_template']['tag']
        }
        folder_name: str = OutputFormatter(f"{CFG['Donwload_Dir_Name']['dir_name']}").format(video_meta)
        return folder_name
    

def get_artis_list(artis_list: List[Dict[str, Optional[str]]]) -> str:
    all_artos_list = set()
    for i in artis_list:
        if i.get('name'):
            all_artos_list.add(i['name'])
    all_artis_str: str  = " ".join(sorted(all_artos_list))
    return all_artis_str

def sync_move(src: Path, dst: Path) -> str:
    shutil.move(str(src), str(dst))
    return dst.name

async def move(src: Path, stem: str, suffix: str, dst: Path, parent: Path) -> str:
    idx = 1
    while dst.exists():
        dst = parent / f"{stem} ({idx}){suffix}"
        idx += 1

    loop = asyncio.get_running_loop()
    moved_name = await loop.run_in_executor(executor, sync_move, src, dst)
    printer_video_folder_path_info(parent, moved_name)
    return moved_name

async def move_contents_to_parent(path: Path, file_name: str) -> None:
    """將 path 中所有檔案（含子資料夾）展平 async 搬到上一層 完成後刪除原始資料夾"""
    if not path.is_dir():
        raise ValueError(f"{path} is not a directory")

    parent = path.parent
    tasks = []

    for item in path.rglob("*"):
        if item.is_file():
            stem, suffix = item.stem, item.suffix
            target = parent / item.name
            tasks.append(move(item, stem, suffix, target, parent))

    await asyncio.gather(*tasks)

    try:
        shutil.rmtree(path)
        file_name += (
            f"\n{Color.fg('flamingo_pink')}No subfolders. "
            f"All files are located in the top-level directory.{Color.reset()}"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to remove original folder {path}: {e}")
                
def printer_video_folder_path_info(new_path: Path, video_file_name: str) -> None:
    if "Keep all segments in temp folder" in video_file_name:
        video_file_name = f"{video_file_name} → {new_path}\\temp"
    logger.info(
        f"{Color.fg('yellow')}Final output file: {Color.reset()}"
        f"{Color.fg('aquamarine')}{Path(new_path)}\n　➥ {video_file_name}{Color.reset()}"
    )
