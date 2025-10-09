from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text


def print_help() -> None:
    console: Console = Console()

    # 創建兩列內容
    left_column: Text = Text()
    right_column: Text = Text()

    # 左列（選項）
    options: List[str] = [
        "-h, --help", "-H" "--dev", "--no_cookie, --nocookie, --no-cookie", "",
        "--community", "--join 'COMMUNITY_NAME'", "--leave 'COMMUNITY_NAME'",
        "--group 'ive'(default)",
        "--board -B", "--live --live-only -L", "--media --media-only -M",
        "--photo --photo-only -P", "--notice --notice-only -N", "",
        "--fanclub-only --fanclub --fc", "--no-fanclub --nfc", "",
        "--t, --time, -T", "--signup", "--change-password", "",
        "--hls", "--del-after-done 'True'(default)", "--skip-merge 'False'(default)",
        "--skip-mux 'False'(default)", "--key, --keys", "--skip-dl --skip-download"
    ]

    # 右列（描述）
    descriptions: List[str] = [
        "顯示此說明訊息並結束 / show this help message and exit",
        "開發模式 / DEV",
        "不使用 cookie / No cookie use", "",
        "列出Berriz當前所有Community / List all current communities in Berriz",
        "加入社羣 / Join a community",
        "離開社羣 / Leave a community",
        "哪位藝人的社區 'ive' or 7 / Which artist's community 'ive' or 7",
        "選擇看板內容 / Choose board content",
        "選擇Live內容 / Choose live content",
        "選擇Media區影片內容 / Choose media chunk video content",
        "選擇Media區相片內容 / Choose media chunk photo content",
        "選擇Notice區內容 / Choose notice chunk content", "",
        "僅顯示粉絲俱樂部內容 / Show only fanclub only content",
        "僅顯示非Fanclub內容 / Show only none fanclub only content", "",
        "依時間篩選內容 / Filter content by date & time",
        "註冊Berriz帳戶 / Berriz account registration",
        "更改當前帳戶密碼 / Change current account password", "",
        "僅使用HLS下載 / Download with HLS only",
        "完成後是否刪除 (true/false) / Whether to delete after completion (true/false)",
        "完成後是否跳過合併 (true/false) / Whether to skip merge after completion (true/false)",
        "合併後是否跳過混流 (true/false) / Whether to skip mux after merge (true/false)",
        "顯示金鑰並跳過下載 / Show key and skip download"
        "不要下載 / NO DL"
    ]

    for option in options:
        left_column.append(option + "\n", style="bold cyan" if option else "white")

    for desc in descriptions:
        right_column.append(desc + "\n")

    # 創建兩列佈局
    columns: Columns = Columns([left_column, right_column], padding=2, equal=False)

    console.print(Panel(columns, title="使用說明 / Help", border_style="green"))