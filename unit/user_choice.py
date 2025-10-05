import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from typing import Dict, List, Set, Tuple, Union, Optional, Any

from InquirerPy import inquirer
from InquirerPy.base.control import Choice

from static.color import Color
from unit.handle.handle_log import setup_logging
from unit.community.community import custom_dict, get_community


logger = setup_logging('user_choice', 'fresh_chartreuse')


MediaItem = Dict[str, Union[str, Dict[str, Any], bool]]
SelectedMedia = Dict[str, List[Dict[str, Any]]]
Key = Tuple[str, int]


class InquirerPySelector:
    def __init__(
        self,
        vod_list: List[Dict[str, Any]],
        photo_list: List[Dict[str, Any]],
        live_list: List[Dict[str, Any]],
        post_list: List[Dict[str, Any]],
        notice_list: List[Dict[str, Any]]
    ) -> None:
        self.vod_items: List[Dict[str, Any]] = vod_list
        self.photo_items: List[Dict[str, Any]] = photo_list
        self.live_items: List[Dict[str, Any]] = live_list
        self.post_items: List[Dict[str, Any]] = post_list
        self.notice_list: List[Dict[str, Any]] = notice_list

    async def run(self) -> Optional[SelectedMedia]:
        display_map: Dict[int, Tuple[str, int]] = {}
        item_choices: List[Choice] = []
        entries: List[Tuple[str, int, Dict[str, Any]]] = []

        try:
            # Populate entries concurrently
            await asyncio.gather(
                asyncio.to_thread(lambda: [entries.append(("vod", idx, item)) for idx, item in enumerate(self.vod_items)]),
                asyncio.to_thread(lambda: [entries.append(("photo", idx, item)) for idx, item in enumerate(self.photo_items)]),
                asyncio.to_thread(lambda: [entries.append(("live", idx, item)) for idx, item in enumerate(self.live_items)]),
                asyncio.to_thread(lambda: [entries.append(("post", idx, item)) for idx, item in enumerate(self.post_items)]),
                asyncio.to_thread(lambda: [entries.append(("notice", idx, item)) for idx, item in enumerate(self.notice_list)])
            )
        except TypeError as e:
            if str(e) == "'NoneType' object is not iterable":
                logger.info('No items')
                return
        entries.sort(key=lambda x: x[2]["publishedAt"])

        # Create quick command choices (not numbered, not in checkbox)
        quick_commands: List[Choice] = [
            Choice("all", name="(All VOD | Photos | Live | POST | NOTICE)"),
            Choice("vall", name="(All VOD)"),
            Choice("pall", name="(All Photos)"),
            Choice("lall", name="(All Live)"),
            Choice("ball", name="(All POST)"),
            Choice("nall", name="(All NOTICE)"),
            Choice("range", name="[Custom — manual select]"),
        ]

        # Create item choices with numbering
        for disp_no, (t, idx, item) in enumerate(entries, start=1):
            display_map[disp_no] = (t, idx)
            core: str = format_core(item, t)
            prefix: str = "|Fanclub| " if item.get("isFanclubOnly") else ""
            community_name = await custom_dict(await get_community(item.get('communityId')))
            if community_name is None:
                community_name: str = f"| {await get_community(item.get('communityId'))} |"
            else:
                community_name: str = f"| {community_name} |"
            ts: str = await convert_to_korea_time(item["publishedAt"])
            match core:
                case 'NOTICE-NO-INFO':
                    name = (
                        f"{disp_no:4d} {ts} {t.upper():5s} {prefix} "
                        f"{community_name} {item['title']} "
                    )
                case _:
                    name = (
                        f"{disp_no:4d} {ts} {t.upper():5s} {prefix} "
                        f"{community_name} [{core}] {item['title']} "
                    )
            item_choices.append(Choice(value=disp_no, name=name))
            
        if item_choices == []:
            logger.info(f"No items found")
            return None
        
        separator: str = '━' * 70
        # Initial selection with fuzzy search
        cmd: Union[str, int] = await inquirer.fuzzy(
            message="Select items or quick command:",
            choices=quick_commands + [separator] + item_choices,
            default="",
            cycle=False,
            border=True,
        ).execute_async()

        picks: Set[int] = set()
        if cmd == "all":
            picks = set(display_map.keys())
        elif cmd == "vall":
            picks = {n for n, (t, _) in display_map.items() if t == "vod"}
        elif cmd == "pall":
            picks = {n for n, (t, _) in display_map.items() if t == "photo"}
        elif cmd == "lall":
            picks = {n for n, (t, _) in display_map.items() if t == "live"}
        elif cmd == "ball":
            picks = {n for n, (t, _) in display_map.items() if t == "post"}
        elif cmd == "nall":
            picks = {n for n, (t, _) in display_map.items() if t == "notice"}
        else:
            # for choese only one
            picks = {cmd} if isinstance(cmd, int) else set()
        if cmd == "range":
            # Prepare choices for checkbox (only item choices, not quick commands)
            final: List[int] = await inquirer.checkbox(
                message="Finalize your selection (→ all, ← none, type to filter):",
                choices=item_choices,
                cycle=True,
                height=30,
                border=True,
                validate=lambda res: len(res) > 0 or "",
                keybindings={
                    "toggle-all-true": [{"key": "right"}],
                    "toggle-all-false": [{"key": "left"}],
                },
                instruction="→ select all, ← deselect all",
                transformer=lambda res: f"{' '.join(map(lambda x: str(x).strip(), res))}"
            ).execute_async()
            picks = set(final)

        return await self._collect(picks, display_map)

    async def _collect(self, picks: Set[int], display_map: Dict[int, Tuple[str, int]]) -> SelectedMedia:
        try:
            vods: List[Dict[str, Any]] = [
                self.vod_items[idx]
                for n in picks
                if (t := display_map[n])[0] == "vod"
                for idx in [t[1]]
            ]
            photos: List[Dict[str, Any]] = [
                self.photo_items[idx]
                for n in picks
                if (t := display_map[n])[0] == "photo"
                for idx in [t[1]]
            ]
            lives = []
            for n in picks:
                if (t := display_map[n])[0] == "live":
                    item = self.live_items[t[1]]
                    if item.get('live', {}).get('liveStatus') == 'REPLAY':
                        lives.append(item)
                    else:
                        logger.warning(
                            f"{Color.fg('turquoise')}{await custom_dict(await get_community(item.get('communityId')))} "
                            f"{Color.fg('light_magenta')}{item.get('title', 'Unknown Title')} "
                            f"{Color.fg('light_gray')}had no replay, try again later{Color.reset()}"
                            f"{Color.fg('gold')} Skip it.{Color.reset()}"
                            )
            post: List[Dict[str, Any]] = [
                self.post_items[idx]
                for n in picks
                if (t := display_map[n])[0] == "post"
                for idx in [t[1]]
            ]
            notice: List[Dict[str, Any]] = [
                self.notice_list[idx]
                for n in picks
                if (t := display_map[n])[0] == "notice"
                for idx in [t[1]]
            ]
            return {"vods": vods, "photos": photos, "lives": lives, "post": post, "notice": notice}
        except KeyError:
            return {"vods": [], "photos": [], "lives": [], "post": [], "notice": []}


async def convert_to_korea_time(iso_string_utc: str) -> str:
    dt_utc: datetime = datetime.fromisoformat(iso_string_utc.replace('Z', '+00:00'))
    dt_kst: datetime = dt_utc.astimezone(ZoneInfo("Asia/Seoul"))
    formatted_string: str = dt_kst.strftime("%y%m%d_%H:%M")
    return formatted_string


def format_core(item: Dict[str, Any], t: str) -> str:
    try:
        if t == "vod":
            return f"{item['vod']['duration'] / 60:.1f}  min"
        elif t == "photo":
            return f"{item['photo']['imageCount']}    imgs"
        elif t == "live":
            match item['live']['liveStatus']:
                case 'REPLAY':
                    return f"{item['live']['replay']['duration'] / 60:.1f}  min"
                case 'END':
                    return 'NO-Replay'

        elif t == "post" and item.get("imageInfo"):
            image_count: str = f"{len(item.get('imageInfo')[1])}"
            match image_count:
                case '0':
                    return "POST-ONLY"
                case _:
                    return f"{image_count}    imgs"
        elif t == "notice":
            return 'NOTICE-NO-INFO'
    except TypeError:
        return ''
    return "unknown"