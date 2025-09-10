import os
import re
import urllib.parse


URI_PATTERN = re.compile(r'URI="([^"]+)"')


async def rebuild_master_playlist(m3u8_string, m3u8_uri):
    parsed_url = urllib.parse.urlparse(m3u8_uri)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{os.path.dirname(parsed_url.path)}/"
    
    lines = m3u8_string.text.strip().split('\n')
    rebuilt_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 檢查是否是URI行（不以#開頭的行）
        if not line.startswith('#'):
            # 這是URI行，需要更新URL
            new_uri = urllib.parse.urljoin(base_url, line)
            rebuilt_lines.append(new_uri)
        else:
            # 檢查是否是包含URI的EXT-X-MEDIA行
            if line.startswith('#EXT-X-MEDIA:') and 'URI=' in line:
                # 使用預編譯的正則表達式提取並更新URI
                uri_match = URI_PATTERN.search(line)
                if uri_match:
                    old_uri = uri_match.group(1)
                    new_uri = urllib.parse.urljoin(base_url, old_uri)
                    line = line.replace(f'URI="{old_uri}"', f'URI="{new_uri}"')
            rebuilt_lines.append(line)
    
    return '\n'.join(rebuilt_lines)