import asyncio
from pathlib import Path

import aiofiles
from bs4 import BeautifulSoup

from static.color import Color
from unit.handle.handle_board_from import FilenameSanitizer
from unit.handle.handle_log import setup_logging


logger = setup_logging('save_html', 'flamingo_pink')


class SaveHTML:
    def __init__(self, title: str, time: str, body: str, folder_path: Path, file_name:str) -> None:
        self.title: str = title
        self.time: str = time
        self.body: str = body
        self.safe_title: str = FilenameSanitizer.sanitize_filename(title)
        self.folder: Path = folder_path
        self.soap: BeautifulSoup | None = None
        self.file_name = file_name

    async def open_template(self) -> str:
            try:
                htmlpath: Path = Path(Path.cwd() / "unit" / "notice" / "template.html")
                async with aiofiles.open(htmlpath, mode='r', encoding='utf-8') as file:
                    return await file.read() 
            except FileNotFoundError:
                logger.error("Error: template.html file not found")
                raise FileNotFoundError

    async def div_content(self) -> None:
        # 尋找目標 div (主要內容)
        target_div_content: BeautifulSoup | None = self.soup.find('div', class_='whitespace-pre-wrap break-words')
        # 更新主要內容
        if target_div_content:
            target_div_content.clear()
            target_div_content.append(BeautifulSoup(self.body, 'html.parser'))
        else:
            logger.error("Cant find <div class='whitespace-pre-wrap break-words'>")
            return

    async def time_div(self) -> None:
        # 尋找時間標籤
        time_div: BeautifulSoup | None = self.soup.find('div', class_='f-body-s-regular text-GRAY400 flex')
        # 更新時間標籤
        if time_div:
            time_div.clear()
            # 格式化時間顯示 (2025.09.24)
            formatted_time: str = f"{self.time[:4]}.{self.time[5:7]}.{self.time[8:10]}"
            time_tag: BeautifulSoup = self.soup.new_tag('time', datetime=self.time)
            time_tag.string = formatted_time
            time_div.append(time_tag)
        else:
            logger.error("Cant find <div class='f-body-s-regular text-GRAY400 flex'>")

    async def title_p(self) -> None:
        # 尋找標題標籤
        title_p: BeautifulSoup | None = self.soup.find('p', class_='text-GRAY002 break-all f-body-xxl-semibold line-clamp-3')
        # 更新標題標籤
        if title_p:
            title_p.clear()
            title_p.string = self.title
        else:
            logger.error("Cant find <p class='text-GRAY002 break-all f-body-xxl-semibold line-clamp-3'>")

    async def write_html_file(self) -> None:
        path: Path = Path(self.folder / f"{self.file_name}.html")
        # 寫回檔案
        async with aiofiles.open(path, 'w', encoding='utf-8') as file:
            await file.write(str(self.soup))
            logger.info(f"{Color.fg('blush')}Notice "
                        f"{Color.fg('orchid')}HTML file saved to "
                        f"{Color.fg('periwinkle')}{path}{Color.reset()}"
                        )
            return True

    async def update_template_file(self) -> None:
        """
        讀取 template.html，更新指定標籤的內容，並使用 TaskGroup 寫回檔案
        """
        try:
            content: str = await self.open_template()
            self.soup: BeautifulSoup = BeautifulSoup(content, 'html.parser')
            await asyncio.gather(
                self.title_p(),
                self.time_div(),
                self.div_content()
            )
            return await self.write_html_file()
        except Exception as e:
            logger.error(f"{e}")
            return False