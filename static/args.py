# main.py
import sys
import argparse

def normalize_flags(argv: list[str]) -> list[str]:
    """
    把所有以 -- 開頭的 flag 及其 key 轉成小寫
    """
    normalized = [argv[0]]
    for token in argv[1:]:
        if token.startswith("--"):
            if "=" in token:
                opt, val = token.split("=", 1)
                normalized.append(f"{opt.lower()}={val}")
            else:
                normalized.append(token.lower())
        else:
            normalized.append(token)
    return normalized

def str_to_bool(value: str) -> bool:
    if isinstance(value, bool):
        return value
    
    value_lower = value.lower()
    
    if value_lower in ('true', 't', 'yes', 'y', '1', 'on'):
        return True
    elif value_lower in ('false', 'f', 'no', 'n', '0', 'off'):
        return False
    else:
        raise argparse.ArgumentTypeError(
            f"Invalid boolean value: '{value}'. Please use true/false, yes/no, 1/0, on/off"
        )


class BooleanAction(argparse.Action):
    """自訂布林動作，自動處理多餘的參數"""
    def __init__(self, option_strings, dest, default=False, **kwargs):
        super().__init__(option_strings, dest, nargs='?', default=default, **kwargs)
    
    def __call__(self, parser, namespace, values, option_string=None):
        # 如果提供了值，嘗試解析為布林值
        if values is not None:
            if isinstance(values, str):
                values = values.lower()
                if values in ('true', 't', 'yes', 'y', '1', 'on'):
                    setattr(namespace, self.dest, True)
                elif values in ('false', 'f', 'no', 'n', '0', 'off'):
                    setattr(namespace, self.dest, False)
                else:
                    # 如果無法解析為布林值，忽略參數並設為 True
                    setattr(namespace, self.dest, True)
            else:
                setattr(namespace, self.dest, bool(values))
        else:
            # 沒有提供值，設為 True
            setattr(namespace, self.dest, True)

def normalize_flags(argv: list[str]) -> list[str]:
    """
    把所有以 -- 開頭的 flag 及其 key 轉成小寫，並清理布林參數
    """
    normalized = [argv[0]]
    i = 1
    
    while i < len(argv):
        token = argv[i]
        
        if token.startswith("--"):
            if "=" in token:
                # 處理 --option=value 格式
                opt, val = token.split("=", 1)
                normalized.append(f"{opt.lower()}={val}")
            else:
                # 檢查下一個 token 是否為布林值
                token_lower = token.lower()
                if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                    next_token = argv[i + 1].lower()
                    # 如果下一個 token 是布林值，跳過它
                    if next_token in ('true', 'false', 't', 'f', 'yes', 'no', 'y', 'n', '1', '0', 'on', 'off'):
                        normalized.append(token_lower)
                        i += 1  # 跳過布林值參數
                    else:
                        normalized.append(token_lower)
                else:
                    normalized.append(token_lower)
        else:
            normalized.append(token)
        
        i += 1
    
    return normalized

def parse_args() -> argparse.Namespace:
    normalized_argv = normalize_flags(sys.argv)
    
    parser = argparse.ArgumentParser(
        add_help=False,
        description='Berriz DRM',
        allow_abbrev=False  # 禁用自動縮寫匹配
    )
    
    # 使用自訂的 BooleanAction 來處理布林選項
    parser.add_argument(
        "--key", "--keys",
        dest="has_key",
        action=BooleanAction,
        help="Show key info and skip download"
    )
    
    parser.add_argument(
        "--h", "--help", "-h", "-help",
        dest="show_help",
        action=BooleanAction,
        help="Show help"
    )
    
    parser.add_argument(
        "--dev",
        dest="dev",
        action=BooleanAction,
        help="For dev"
    )
    
    parser.add_argument(
        "--no_cookie", "--nocookie", "--no-cookie",
        dest="had_nocookie",
        action=BooleanAction,
        help="No cookie use"
    )
    
    parser.add_argument(
        "--fanclub-only",
        dest="fanclub",
        action=BooleanAction,
        help="Show only fanclub only content"
    )
    
    parser.add_argument(
        "--t", "--time",
        dest="time_date",
        action=BooleanAction,
        help="Filter content by date&time"
    )
    
    parser.add_argument(
        "--community",
        dest="community",
        action=BooleanAction,
        help="Show only fanclub only content"
    )
    
    parser.add_argument(
        "--change-password", "--change_password",
        dest="change_password",
        action=BooleanAction,
        help="Change password"
    )
    
    parser.add_argument(
        "--no-fanclub",
        dest="nofanclub",
        action=BooleanAction,
        help="Show only none fanclub only content"
    )
    
    parser.add_argument(
        "--board", "-board",
        dest="board",
        action=BooleanAction,
        help="Choose board"
    )
    
    # 非布林選項保持原樣
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
        help="Leave a community"
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
        type=str_to_bool,
        required=False,
        help="Whether to skip merge after completion (true/false)"
    )
    
    parser.add_argument(
        "--g", "--group",
        dest="group",
        required=False,
        help="group"
    )
    
    return parser.parse_args(normalized_argv[1:])

def had_key() -> bool:
    args = parse_args()
    return args.has_key

def had_nocookie() -> bool:
    args = parse_args()
    return args.had_nocookie if args.had_nocookie is not None else False

def clean_dl() -> bool:
    args = parse_args()
    return args.clean_dl if args.clean_dl is not None else True

def skip_merge() -> bool:
    args = parse_args()
    return args.skip_merge if args.skip_merge is not None else False

def fanclub() -> bool:
    args = parse_args()
    return args.fanclub

def nofanclub() -> bool:
    args = parse_args()
    return args.nofanclub

def community() -> bool:
    args = parse_args()
    return args.community

def change_password() -> bool:
    args = parse_args()
    return args.change_password

def _group() -> str:
    args = parse_args()
    return args.group if args.group is not None else 'ive'

def board() -> str:
    args = parse_args()
    return args.board if args.board is not None else 'ive'

def join_community() -> str:
    args = parse_args()
    return args.join_community if args.join_community is not None else ''

def leave_community() -> str:
    args = parse_args()
    return args.leave_community if args.leave_community is not None else ''

def time_date() -> bool:
    args = parse_args()
    return args.time_date

def dev() -> bool:
    args = parse_args()
    return args.dev

def show_help() -> bool:
    args = parse_args()
    return args.show_help