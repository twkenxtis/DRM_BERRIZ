import sys
import asyncio
import difflib
import click
from typing import List, Optional, Dict, Any, Tuple


from static.color import Color
from lib.account.signup import run_signup
from lib.account.change_pawword import Change_Password
from lib.account.berriz_create_community import BerrizCreateCommunity
from unit.community.community import cm
from unit.handle.handle_log import setup_logging


logger = setup_logging('args', 'mint')


# 全域儲存參數
_global_args: Dict[str, Any] = {}


# 已知旗標列表
known_flags: List[str] = [
    "--key", "--keys", "--help", "--h", "-h", "-H", "--dev",
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
    "--photo", "--photo-only", "-P",
    "--notice", "--notice-only", "-N",
    "--g", "--group", "-G",
    "--skip-mux",
    "--signup", "--HLS", "--hls",
    "--skip-dl", "--skip-download",
    "--skip-json",
    "--skip-thumbnails", "--skip-thb",
    "--skip-playlist", "--skip-pl",
    "--skip-html",
]


def suggest_unknown_args(unknown: List[str], known_flags: List[str]) -> None:
    """提示未識別參數的可能拼寫建議"""
    for u in unknown:
        suggestion = difflib.get_close_matches(u, known_flags, n=1, cutoff=0.5)
        if suggestion:
            logger.info(
                f"{Color.fg('light_gray')}You probably meant "
                f"{Color.fg('gold')}{suggestion[0]} {Color.reset()}instead of "
                f"{Color.fg('light_gray')}{u}{Color.reset()}"
            )
        else:
            logger.error(f"Unrecognized parameter: {u}")


def _get_arg(key: str, default: Any = None) -> Any:
    """獲取參數值的輔助函數"""
    if _global_args:
        return _global_args.get(key, default)
    
    try:
        ctx = click.get_current_context(silent=True)
        if ctx and ctx.obj:
            return ctx.obj.get(key, default)
    except RuntimeError:
        pass
    
    return default

@click.command(
    add_help_option=False,  # 關鍵：禁用 Click 的預設 help
    context_settings=dict(
        ignore_unknown_options=True,
        allow_interspersed_args=True
    )
)
@click.option('--key', '--keys', 'has_key', is_flag=True, help='Show key and skip download')
@click.option('--hls', '--HLS', 'hls_only_dl', is_flag=True, help='Only use HLS for download')
@click.option(
    '--help', '--h', '-h', '-H',
    'show_help',
    is_flag=True,
    help='Show help'
)
@click.option('--dev', is_flag=True, help='DEV mode')
@click.option('--no-cookie', '--no_cookie', '--nocookie', 'had_nocookie', is_flag=True, help='No cookie use')
@click.option('--join', '--join-community', '--join_community', 'join_community', default='', help='Join a community')
@click.option('--leave', '--leave-community', '--leave_community', 'leave_community', default='', help='Leave a community')
@click.option('--fanclub-only', '--fanclub', '--fc', 'fanclub', is_flag=True, help='Show only fanclub-only content')
@click.option('--no-fanclub', '--nfc', 'nofanclub', is_flag=True, help='Show only non-fanclub-only content')
@click.option('--live', '--live-only', '-L', 'liveonly', is_flag=True, help='Show only live content')
@click.option('--media', '--media-only', '-M', 'mediaonly', is_flag=True, help='Show only media content')
@click.option(
    '--t', '--time', '-T',
    'time_date',
    type=str,
    nargs=1,
    help='Filter content by date/time (use 1-2 times)'
)
@click.option('--community', is_flag=True, help='Show community content')
@click.option('--change-password', '--change_password', 'change_password', is_flag=True, help='Change password')
@click.option('--signup', is_flag=True, help='Signup')
@click.option('--del-after-done', 'clean_dl', type=click.BOOL, default=None, help='Delete after completion (true/false, default: true)')
@click.option('--skip-merge', 'skip_merge', is_flag=True, help='Skip merge after completion (default: Disable)')
@click.option('--skip-mux', 'skip_mux', is_flag=True, help='Skip mux after merge (default: Disable)')
@click.option('--board', '-B', is_flag=True, help='Choose board')
@click.option('--photo', '--photo-only', '-P', 'photoonly', is_flag=True, help='Choose photo')
@click.option('--notice', '--notice-only', '-N', 'noticeonly', is_flag=True, help='Choose notice')
@click.option('--g', '--group', '-G', 'group', default='ive', help='Group name (default: ive)')
@click.option('--skip-dl', '--skip-download', 'nodl', is_flag=True , help='No download (default: Disable)')
@click.option('--skip-json', '--skip-Json', '--skip-JSON', 'nojson', is_flag=True , help='No Json download (default: Disable)')
@click.option('--skip-thumbnails', '--skip-thb', 'nothumbnails', is_flag=True, help='No thumbnails download (default: Disable)')
@click.option('--skip-playlist', '--skip-pl', '--skip-Playlist', 'notplaylist', is_flag=True, help='No playlist download (default: Disable)')
@click.option('--skip-html', '--skip-Html', '--skip-HTML','nohtml', is_flag=True, help='No html download (default: Disable)')
@click.argument('unknown', nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def main(
    ctx: click.Context,
    has_key: bool,
    hls_only_dl: bool,
    show_help: bool,
    dev: bool,
    had_nocookie: bool,
    join_community: str,
    leave_community: str,
    fanclub: bool,
    nofanclub: bool,
    liveonly: bool,
    mediaonly: bool,
    time_date: bool,
    community: bool,
    change_password: bool,
    signup: bool,
    clean_dl: Optional[bool],
    skip_merge: bool,
    skip_mux: bool,
    board: bool,
    photoonly: bool,
    noticeonly: bool,
    group: str,
    nodl: bool,
    nojson: bool,
    nothumbnails: bool,
    notplaylist: bool,
    nohtml: bool,
    unknown: tuple
) -> None:
    """
    Berriz DRM - Download and manage DRM content
    
    A comprehensive CLI tool for managing content with various filtering options.
    """
    global _global_args
    
    # 儲存所有參數
    args_dict = {
        'has_key': has_key,
        'hls_only_dl': hls_only_dl,
        'show_help': show_help,
        'dev': dev,
        'had_nocookie': had_nocookie,
        'join_community': join_community,
        'leave_community': leave_community,
        'fanclub': fanclub,
        'nofanclub': nofanclub,
        'liveonly': liveonly,
        'mediaonly': mediaonly,
        'time_date': time_date,
        'community': community,
        'change_password': change_password,
        'signup': signup,
        'clean_dl': clean_dl,
        'skip_merge': skip_merge,
        'skip_mux': skip_mux,
        'board': board,
        'photoonly': photoonly,
        'noticeonly': noticeonly,
        'group': group,
        'nodl': nodl,
        'nojson': nojson,
        'notplaylist': notplaylist,
        'nothumbnails': nothumbnails,
        'nohtml': nohtml,
    }
    
    ctx.obj = args_dict
    _global_args = args_dict
    
    # 檢查未知參數
    if unknown:
        logger.warning(f"Unknown args: {list(unknown)}")
        suggest_unknown_args(list(unknown), known_flags)
        sys.exit(2)
    
    logger.info(f"{Color.fg('mint')}Arguments parsed successfully{Color.reset()}")
    
    from static.parameter import paramstore
    
    if has_key:
        paramstore._store["key"] = True
    
    if dev:
        paramstore._store["notify_mod"] = True
        logger.debug(f"{Color.fg('gold')}Running in DEV mode...{Color.reset()}")
    
    if had_nocookie:
        paramstore._store["no_cookie"] = True
    
    if clean_dl is False:
        paramstore._store["clean_dl"] = False
    elif clean_dl is None:
        paramstore._store["clean_dl"] = True
    else:
        paramstore._store["clean_dl"] = clean_dl
    
    if skip_merge:
        paramstore._store["skip_merge"] = True
    
    if skip_mux:
        paramstore._store["skip_mux"] = True
    
    if fanclub:
        paramstore._store["fanclub"] = True
    
    if nofanclub:
        paramstore._store["fanclub"] = False
        
    if nofanclub:
        paramstore._store["fanclub"] = False
        
    if nodl:
        paramstore._store["nodl"] = True
        
    if nojson:
        paramstore._store["nojson"] = True
        
    if nothumbnails:
        paramstore._store["nothumbnails"] = True
        
    if notplaylist:
        paramstore._store["notplaylist"] = True
        
    if nohtml:
        paramstore._store["nohtml"] = True
    
    # 這些需要顯式設置 True/False
    paramstore._store["mediaonly"] = mediaonly
    paramstore._store["liveonly"] = liveonly
    paramstore._store["photoonly"] = photoonly
    paramstore._store["noticeonly"] = noticeonly
    paramstore._store["board"] = board
    paramstore._store["hls_only_dl"] = hls_only_dl
    
    # 處理特殊命令
    if signup:
        try:
            asyncio.run(run_signup())
        except KeyboardInterrupt:
            logger.info(f"Program interrupted: {Color.fg('light_gray')}User canceled{Color.reset()}")
            sys.exit(0)
        return
    
    if change_password:
        if asyncio.run(Change_Password().change_password()) is True:
            pass
        else:
            raise RuntimeError('Something fail')

    if join_community:
        asyncio.run(join_cm())
        return
    
    if leave_community:
        asyncio.run(leave_cm())
        return

def had_key() -> bool:
    """是否顯示金鑰並跳過下載"""
    return _get_arg('has_key', False)


def had_nocookie() -> bool:
    """是否禁用 Cookie"""
    return _get_arg('had_nocookie', False)


def clean_dl() -> bool:
    """是否在完成後刪除檔案（預設 True）"""
    value = _get_arg('clean_dl')
    return True if value is None else value


def skip_merge() -> bool:
    """是否跳過合併"""
    return _get_arg('skip_merge', False)


def skip_mux() -> bool:
    """是否跳過封裝"""
    return _get_arg('skip_mux', False)


def fanclub() -> bool:
    """是否僅顯示粉絲俱樂部內容"""
    return _get_arg('fanclub', False)


def nofanclub() -> bool:
    """是否僅顯示非粉絲俱樂部內容"""
    return _get_arg('nofanclub', False)


def community() -> bool:
    """是否顯示社群內容"""
    return _get_arg('community', False)


def change_password() -> bool:
    """是否變更密碼"""
    return _get_arg('change_password', False)


def group() -> str:
    """取得群組名稱（預設 'ive'）"""
    return _get_arg('group', 'ive')


def board() -> bool:
    """是否選擇看板"""
    return _get_arg('board', False)


def join_community() -> str:
    """取得要加入的社群名稱"""
    return _get_arg('join_community', '')


def leave_community() -> str:
    """取得要離開的社群名稱"""
    return _get_arg('leave_community', '')


def time_date() -> Optional[Tuple[str, str]]:
    """取得日期範圍 兩個日期"""
    return _get_arg('time_date', None)


def dev() -> bool:
    """是否為開發模式"""
    return _get_arg('dev', False)


def show_help() -> bool:
    """是否顯示幫助"""
    return _get_arg('show_help', False)


def mediaonly() -> bool:
    """是否僅顯示媒體內容"""
    return _get_arg('mediaonly', False)


def liveonly() -> bool:
    """是否僅顯示直播內容"""
    return _get_arg('liveonly', False)


def photoonly() -> bool:
    """是否僅顯示照片內容"""
    return _get_arg('photoonly', False)


def noticeonly() -> bool:
    """是否僅顯示公告內容"""
    return _get_arg('noticeonly', False)


def hls_only_dl() -> bool:
    """是否僅使用 HLS 下載"""
    return _get_arg('hls_only_dl', False)


def signup() -> bool:
    """是否註冊"""
    return _get_arg('signup', False)

def nodl() -> bool:
    """是否跳過下載"""
    return _get_arg('nodl', False)

def nojson() -> bool:
    """是否跳過下載JSON"""
    return _get_arg('nojson', False)

def nothumbnails() -> bool:
    """是否跳過下載封面縮圖"""
    return _get_arg('nothumbnails', False)

def notplaylist() -> bool:
    """是否跳過下載播放清單"""
    return _get_arg('notplaylist', False)

def nohtml() -> bool:
    """是否跳過保存成HTML"""
    return _get_arg('nohtml', False)

async def join_cm():
    await BerrizCreateCommunity(await cm(join_community()), join_community()).community_join()

async def leave_cm():
    await BerrizCreateCommunity(await cm(leave_community()), leave_community()).leave_community_main()


if __name__ == '__main__':
    try:
        main(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        logger.info(f"Program interrupted: {Color.fg('light_gray')}User canceled{Color.reset()}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if dev():
            import traceback
            traceback.print_exc()
        sys.exit(1)
else:
    # 模組導入時自動解析（保持兼容性）
    try:
        main(standalone_mode=False)
    except (click.ClickException, SystemExit, RuntimeError):
        pass
