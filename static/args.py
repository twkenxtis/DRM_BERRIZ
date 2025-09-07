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

def parse_args() -> argparse.Namespace:
    # 先把 sys.argv 轉成不區分大小寫的版本，再交給 argparse
    normalized_argv = normalize_flags(sys.argv)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--key", "--keys",
        dest="has_key",
        action="store_true",
        help="Show key and skip download"
    )
    parser.add_argument(
        "--fanclub-only",
        dest="fanclub",
        action="store_true",
        help="Show only fanclub only content"
    )
    parser.add_argument(
        "--community",
        dest="community",
        action="store_true",
        help="Show only fanclub only content"
    )
    parser.add_argument(
        "--no-fanclub",
        dest="nofanclub",
        action="store_true",
        help="Show only fanclub only content"
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
        help="Whether to delete after completion (true/false)"
    )
    parser.add_argument(
        "--a", "--artis",
        dest="artis",
        required=False,
        help="Artis"
    )
    return parser.parse_args(normalized_argv[1:])

def had_key() -> bool:
    args = parse_args()
    return args.has_key

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

def _artis() -> str:
    args = parse_args()
    return args.artis if args.artis is not None else 'ive'
