import asyncio
import os
import re
import uuid
from typing import List, FrozenSet, Union
import html
from urllib.parse import urlparse, ParseResult
from pathlib import Path

import aiofiles

from unit.http.request_berriz_api import GetRequest


# 允許的圖片副檔名集合 frozenset 確保不可變
IMAGE_EXTENSIONS: FrozenSet[str] = frozenset({
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'avif',
    'bmp', 'svg', 'heif', 'heic'
})


# 目標 URL 的固定開頭
BASE_URL_PREFIX: str = "https://statics.berriz.in/"


class Get_image_from_body:
    def __init__(self, html_content: str):
        self.html_content: str = html_content

    def is_valid_image_url(self, url: str) -> bool:
        """
        檢查 URL 是否以指定的網域開頭，且結尾副檔名符合圖片列表
        :param url: 待檢查的 URL 字串
        :return: 如果符合條件則返回 True，否則返回 False
        """
        if not isinstance(url, str) or not url:
            return False
        # 快速檢查 URL 是否以指定網域開頭
        if not url.startswith(BASE_URL_PREFIX):
            return False
        # 解析 URL 獲取路徑
        parsed_url: ParseResult = urlparse(url)
        path: str = parsed_url.path
        # 使用 os.path.splitext 獲取副檔名
        _, ext_with_dot = os.path.splitext(path)
        # 移除 '.' 並轉為小寫，檢查是否在允許列表中
        extension: str = ext_with_dot[1:].lower() if ext_with_dot else ""
        return extension in IMAGE_EXTENSIONS

    def extract_image_urls_from_html(self) -> List[str]:
        """
        從 HTML 內容中提取所有圖片 URL
        :return: 圖片 URL 列表
        """
        # 正則表達式匹配 img 標籤的 src 屬性
        img_pattern: "re.Pattern[str]" = re.compile(r'<img[^>]+src="([^">]+)"', re.IGNORECASE)

        # 匹配 srcset 中的 URL（取第一個 URL）
        srcset_pattern: "re.Pattern[str]" = re.compile(r'<img[^>]+srcset="([^">]+)"', re.IGNORECASE)

        urls: List[str] = []
        # 提取普通 src 屬性
        for match in img_pattern.findall(self.html_content):
            # 解碼 HTML 實體（如 &amp; -> &）
            decoded_url: str = html.unescape(match)
            urls.append(decoded_url)

        # 提取 srcset 屬性中的 URL
        for srcset_match in srcset_pattern.findall(self.html_content):
            # srcset 格式: "image1.jpg 1x, image2.jpg 2x"
            srcset_content: str = html.unescape(srcset_match)
            # 取每個 URL（逗號分隔的第一部分）
            for srcset_item in srcset_content.split(','):
                url_part: str = srcset_item.strip().split()[0] if srcset_item.strip() else ""
                if url_part:
                    urls.append(url_part)

        return urls

    def find_valid_image_urls_in_file(self) -> List[str]:
        """
        從 HTML 檔案中找出所有符合條件的圖片 URL
        """
        # 提取所有圖片 URL
        all_image_urls: List[str] = self.extract_image_urls_from_html()
        # 過濾有效的圖片 URL
        valid_urls: List[str] = [url for url in all_image_urls if self.is_valid_image_url(url)]
        return valid_urls


class DownloadImage(Get_image_from_body):
    def __init__(self, html_content: str, folder_path: Path):
        super().__init__(html_content)
        self.all_image_urls: List[str] = self.find_valid_image_urls_in_file()
        self.folderpath: Path = folder_path

    async def request_image(self) -> Union[str, List[Path]]:
        if not self.all_image_urls:
            return 'NO-IMAGE'

        self.folderpath.mkdir(parents=True, exist_ok=True)
        req: GetRequest = GetRequest()

        tasks: List["asyncio.Task[Path]"] = [
            asyncio.create_task(self._fetch_and_save(url, req))
            for url in self.all_image_urls
        ]
        return await asyncio.gather(*tasks)

    async def _fetch_and_save(self, url: str, req: GetRequest) -> Path:
        resp = await req.get_request(url)
        try:
            data: bytes = resp.content
        except AttributeError:
            data = await resp.read()

        # 產生檔名（URL path 裡面沒有檔名就用 uuid）
        name: str = Path(urlparse(url).path).name or f"{uuid.uuid4()}"
        filepath: Path = self.folderpath / name

        async with aiofiles.open(filepath, "wb") as f:
            await f.write(data)

        return filepath