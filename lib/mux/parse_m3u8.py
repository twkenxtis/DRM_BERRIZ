import os
import re
import urllib.parse
from typing import List, Any, Pattern, Awaitable, Union, Dict


URI_PATTERN: Pattern[str] = re.compile(r'URI="([^"]+)"')


async def rebuild_master_playlist(m3u8_string: Any, m3u8_uri: str) -> str:
    # m3u8_string 是一個包含 .text 屬性的物件
    
    # 類型註釋：解析 URL 的結果
    parsed_url: urllib.parse.ParseResult = urllib.parse.urlparse(m3u8_uri)
    # 類型註釋：基底 URL 始終是字串
    base_url: str = f"{parsed_url.scheme}://{parsed_url.netloc}{os.path.dirname(parsed_url.path)}/"
    
    # 類型註釋：將輸入內容分割成字串列表
    lines: List[str] = m3u8_string.text.strip().split('\n')
    # 類型註釋：重建後的行列表
    rebuilt_lines: List[str] = []
    
    for line_raw in lines:
        # 類型註釋：每行經過 strip() 處理後仍是字串
        line: str = line_raw.strip()
        if not line:
            continue
            
        # 檢查是否是 URI 行（不以 # 開頭的行）
        if not line.startswith('#'):
            # 這是 URI 行，需要更新 URL
            # 類型註釋：urljoin 的結果是字串
            new_uri: str = urllib.parse.urljoin(base_url, line)
            rebuilt_lines.append(new_uri)
        else:
            # 檢查是否是包含 URI 的 EXT-X-MEDIA 行
            if line.startswith('#EXT-X-MEDIA:') and 'URI=' in line:
                # 使用預編譯的正則表達式提取並更新 URI
                # 類型註釋：正則匹配的結果是可選的 Match 物件
                uri_match: Union[re.Match[str], None] = URI_PATTERN.search(line)
                if uri_match:
                    # 類型註釋：group(1) 提取出的舊 URI 是字串
                    old_uri: str = uri_match.group(1)
                    # 類型註釋：urljoin 的結果是字串
                    new_uri: str = urllib.parse.urljoin(base_url, old_uri)
                    # 類型註釋：替換後的行仍是字串
                    line = line.replace(f'URI="{old_uri}"', f'URI="{new_uri}"')
            rebuilt_lines.append(line)
    
    # 類型註釋：回傳字串列表用 \n 連接後的最終字串
    return '\n'.join(rebuilt_lines)