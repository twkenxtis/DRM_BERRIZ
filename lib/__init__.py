import re
import string
from typing import List, Dict, Optional

from static.color import Color
from lib.load_yaml_config import CFG, ConfigLoader
from unit.handle.handle_log import setup_logging


logger = setup_logging('lib.__init__', 'fern')


class FilenameSanitizer:
    """Handles sanitization of filenames to remove invalid characters."""

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Sanitize filename by removing invalid Windows characters and replacing problematic symbols."""
        # 替換全形引號為半形 '
        name = name.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
        # 移除非法字元（包含控制字元）
        name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', name)
        # 移除尾部空白與句點
        name = name.rstrip(' .')
        # 移除開頭空白
        name = name.lstrip()
        # 避免保留名稱（不分大小寫）
        reserved = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
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


class OutputFormatter:
    def __init__(self, template: str):
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
    
    
def get_artis_list(artis_list: List[Dict[str, Optional[str]]]):
    all_artos_list = set()
    for i in artis_list:
        if i.get('name'):
            all_artos_list.add(i['name'])
    all_artis_str: str  = " ".join(sorted(all_artos_list))
    return all_artis_str