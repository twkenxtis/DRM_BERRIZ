from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

def print_help():
    console = Console()

    # 創建兩列內容
    left_column = Text()
    right_column = Text()
    
    # 左列（選項）
    options = [
        "-h, --help", "--dev", "--no_cookie, --nocookie, --no-cookie", "",
        "--community", "--join 'COMMUNITY_NAME'", "--leave 'COMMUNITY_NAME'", 
        "--group 'ive'(default)", "--board", "--fanclub-only", "--no-fanclub", "",
        "--t, --time", "--change-password", "",
        "--del-after-done 'True'(default)", "--skip-merge 'False'(default)", "--key, --keys"
    ]
    
    # 右列（描述）
    descriptions = [
        "顯示此說明訊息並結束 / show this help message and exit",
        "開發模式 / DEV",
        "不使用 cookie / No cookie use", "",
        "列出Berriz當前所有Community / List all current communities in Berriz",
        "加入社群 / Join a community",
        "離開社群 / Leave a community",
        "哪位藝人的社區 'ive' or 7 / Which artist's community 'ive' or 7",
        "選擇看板內容 only / Choose board content only",
        "僅顯示粉絲俱樂部內容 / Show only fanclub only content",
        "僅顯示非Fanclub內容 / Show only none fanclub only content", "",
        "依時間篩選內容 / Filter content by date & time",
        "更改當前帳戶密碼 / Change current account password", "",
        "完成後是否刪除 (true/false) / Whether to delete after completion (true/false)",
        "完成後是否跳過合併 (true/false) / Whether to skip merge after completion (true/false)",
        "顯示金鑰並跳過下載 / Show key and skip download"
    ]
    
    for option in options:
        left_column.append(option + "\n", style="bold cyan" if option else "white")
    
    for desc in descriptions:
        right_column.append(desc + "\n")
    
    # 創建兩列布局
    columns = Columns([left_column, right_column], padding=2, equal=False)
    
    console.print(Panel(columns, title="使用說明 / Help", border_style="green"))