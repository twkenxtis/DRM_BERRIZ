import sys
import argparse
import difflib
from typing import List, Union, Any, Optional

from static.color import Color
from unit.handle.handle_log import setup_logging


logger = setup_logging('args', 'mint')


known_flags: List[str] = [
    "--key", "--keys", "--help", "--h", "-H", "--dev",
    "--no_cookie", "--nocookie", "--no-cookie",
    "--join", "--join-community", "--join_community",
    "--leave", "--leave-community", "--leave_community",
    "--fanclub-only", "--fanclub", "--fc",
    "--no-fanclub", "--nfc",
    "--live", "--live-only", "-L",
    "--media", "--media-only", "-M",
    "--t", "--time", "-T",
    "--community",
    "--change-password", "--change_password",
    "--del-after-done",
    "--skip-merge",
    "--board", "-B",
    "--photo", "--photo-onl0y", "-P",
    "--notice", "--notice-onl0y", "-N",
    "--g", "--group", "-G",
    "--skip-mux"
]


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        """Override the error method to raise an exception instead of calling sys.exit."""
        raise ValueError(f"Argument parsing error: {message}")
    

def normalize_flags(argv: List[str]) -> List[str]:
    """
    嚴格標準化命令行參數：
    - 以 -- 開頭的長選項轉小寫
    - 以 - 開頭的短選項轉大寫
    - 確保單個 - 後面的字母轉大寫
    """
    normalized: List[str] = [argv[0]]
    
    for token in argv[1:]:
        if token.startswith("--"):
            # 長選項：轉小寫
            normalized.append(token.lower())
            
        elif token.startswith("-") and len(token) == 2 and token[1].isalpha():
            # 短選項（單字母）：轉大寫
            normalized.append(f"-{token[1].upper()}")
            
        elif token.startswith("-") and len(token) > 2 and token[1].isalpha():
            # 短選項（帶值或其他格式）：只轉換選項部分
            if "=" in token:
                opt, val = token.split("=", 1)
                normalized.append(f"{opt.upper()}={val}")
            else:
                normalized.append(token.upper())
        else:
            # 其他情況保持原樣
            normalized.append(token)
            
    return normalized

def str_to_bool(value: Union[str, bool]) -> bool:
    """
    將字串轉換為布林值，用於 argparse 的 type 參數
    """
    if isinstance(value, bool):
        return value
    
    value_lower: str = value.lower()
    
    if value_lower in ('true', 't', 'yes', 'y', '1', 'on'):
        return True
    elif value_lower in ('false', 'f', 'no', 'n', '0', 'off'):
        return False
    else:
        raise argparse.ArgumentTypeError(
            f"Invalid boolean value: '{value}'. Please use true/false, yes/no, 1/0, on/off"
        )

def suggest_unknown_args(unknown: List[str], known_flags: List[str]) -> None:
    """
    針對未識別的參數提供建議
    """
    for u in unknown:
        suggestion: List[str] = difflib.get_close_matches(u, known_flags, n=1, cutoff=0.5)
        if suggestion:
            logger.info(f"{Color.fg('light_gray')}You probably meant "
                        f"{Color.fg('gold')}{suggestion[0]} {Color.fg('light_gray')}instead of "
                        f"{Color.fg('light_gray')}{u}"
                        )
        else:
            logger.error(f"Unrecognized parameter:{u}")

def parse_args() -> argparse.Namespace:
    """
    解析 CLI 參數並返回一個命名空間物件
    """
    # 先把 sys.argv 轉成不區分大小寫的版本，再交給 argparse
    normalized_argv: List[str] = normalize_flags(sys.argv)
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description='Berriz DRM',
        allow_abbrev=False,
        add_help=False,
    )
    
    parser.add_argument(
        "--key", "--keys",
        dest="has_key",
        action="store_true",
        help="Show key and skip download"
    )
    parser.add_argument(
        "--HLS", "--hls",
        dest="hls_only_dl",
        action="store_true",
        help="Only use MPEG-DASH for download"
    )
    parser.add_argument(
        "--help", "--h", "-h", "-H",
        dest="show_help",
        action="store_true",
        help="Show help"
    )
    parser.add_argument(
        "--dev",
        dest="dev",
        action="store_true",
        help="DEV"
    )
    parser.add_argument(
        "--no_cookie", "--nocookie", "--no-cookie",
        dest="had_nocookie",
        action="store_true",
        help="No cookie use"
    )
    parser.add_argument(
        "--join", "--join-community", "--join_community",
        dest="join_community",
        required=False,
        help="Join a community"
    )
    parser.add_argument(
        "--leave", "--leave-community", "--leave_community",
        dest="leave_community",
        required=False,
        help="leave a community"
    )
    parser.add_argument(
        "--fanclub-only", "--fanclub", "--fc",
        dest="fanclub",
        action="store_true",
        help="Show only fanclub only content"
    )
    parser.add_argument(
        "--no-fanclub", "--nfc",
        dest="nofanclub",
        action="store_true",
        help="Show only none fanclub only content"
    )
    parser.add_argument(
        "--live", "--live-only", "-L",
        dest="liveonly",
        action="store_true",
        help="Show only none fanclub only content"
    )
    parser.add_argument(
        "--media", "--media-only", "-M",
        dest="mediaonly",
        action="store_true",
        help="Show only none fanclub only content"
    )
    parser.add_argument(
        "--t", "--time", "-T",
        dest="time_date",
        action="store_true",
        help="Filter content by date&time"
    )
    parser.add_argument(
        "--community",
        dest="community",
        action="store_true",
        help="Show only fanclub only content"
    )
    parser.add_argument(
        "--change-password", "--change_password",
        dest="change_password",
        action="store_true",
        help="Change password"
    )
    parser.add_argument(
        "--signup",
        dest="signup",
        action="store_true",
        help="Signup"
    )
    parser.add_argument(
        "--del-after-done",
        dest="clean_dl",
        type=str_to_bool,
        required=False,
        help="Whether to delete after completion (true/false)"
    )
    parser.add_argument(
        "--skip-merge",
        dest="skip_merge",
        action="store_true",
        required=False,
        help="Whether to skep merge after completion (true/false)"
    )
    parser.add_argument(
        "--skip-mux",
        dest="skip_mux",
        action="store_true",
        required=False,
        help="Whether to skep mux after merge (true/false)"
    )
    parser.add_argument(
        "--board", "-B",
        dest="board",
        action="store_true",
        help="Choese board"
    )
    parser.add_argument(
        "--photo", "--photo-onl0y", "-P",
        dest="photoonly",
        action="store_true",
        help="Choese photo"
    )
    parser.add_argument(
        "--notice", "--notice-onl0y", "-N",
        dest="noticeonly",
        action="store_true",
        help="Choese notice"
    )
    parser.add_argument(
        "--g", "--group", "-G",
        dest="group",
        required=False,
        help="group"
    )
    args: argparse.Namespace
    unknown: List[str]
    args, unknown = parser.parse_known_args(normalized_argv[1:])
    
    if unknown:
        logger.warning(f"Unknown {unknown} args in command.")
        suggest_unknown_args(unknown, known_flags)
        sys.exit(2)
        
    return args

args: argparse.Namespace = parse_args()

def had_key() -> bool:
    return args.has_key

def had_nocookie() -> bool:
    return args.had_nocookie if args.had_nocookie is not None else False

def clean_dl() -> bool:
    return args.clean_dl if args.clean_dl is not None else True

def skip_merge() -> bool:
    return args.skip_merge

def skip_mux() -> bool:
    return args.skip_mux

def fanclub() -> bool:
    return args.fanclub

def nofanclub() -> bool:
    return args.nofanclub

def community() -> bool:
    return args.community

def change_password() -> bool:
    return args.change_password

def group() -> str:
    return args.group if args.group is not None else 'ive'

def board() -> Union[bool, str]:
    return args.board if args.board is not None else 'ive'

def join_community() -> str:
    return args.join_community if args.join_community is not None else ''

def leave_community() -> str:
    return args.leave_community if args.leave_community is not None else ''

def time_date() -> bool:
    return args.time_date

def dev() -> bool:
    return args.dev

def show_help() -> bool:
    return args.show_help

def mediaonly() -> bool:
    return args.mediaonly

def liveonly() -> bool:
    return args.liveonly

def photoonly() -> bool:
    return args.photoonly

def noticeonly() -> bool:
    return args.noticeonly

def hls_only_dl() -> bool:
    return args.hls_only_dl

def signup() -> bool:
    return args.signup
