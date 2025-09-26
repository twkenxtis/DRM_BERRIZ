import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from typing import Any, Dict, List, Set, Tuple, Union

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator

from unit.handle_log import setup_logging
from unit.community import custom_dict, get_community


logger = setup_logging('user_choice', 'fresh_chartreuse')


MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]
Key = Tuple[str, int]


class InquirerPySelector:
    def __init__(self, vod_list: List[dict], photo_list: List[dict], live_list: List[dict], post_list: List[dict]):
        self.vod_items = vod_list
        self.photo_items = photo_list
        self.live_items = live_list
        self.post_items = post_list

    async def run(self) -> dict:
        display_map: Dict[int, Tuple[str, int]] = {}
        item_choices: List[Choice] = []
        entries: List[Tuple[str, int, dict]] = []

        # Populate entries concurrently
        await asyncio.gather(
            asyncio.to_thread(lambda: [entries.append(("vod", idx, item)) for idx, item in enumerate(self.vod_items)]),
            asyncio.to_thread(lambda: [entries.append(("photo", idx, item)) for idx, item in enumerate(self.photo_items)]),
            asyncio.to_thread(lambda: [entries.append(("live", idx, item)) for idx, item in enumerate(self.live_items)]),
            asyncio.to_thread(lambda: [entries.append(("post", idx, item)) for idx, item in enumerate(self.post_items)])
        )
        entries.sort(key=lambda x: x[2]["publishedAt"])

        # Create quick command choices (not numbered, not in checkbox)
        quick_commands = [
            Choice("all", name="(All VOD | Photos | Live)"),
            Choice("vall", name="(All VOD)"),
            Choice("pall", name="(All Photos)"),
            Choice("lall", name="(All Live)"),
            Choice("ball", name="(All POST)"),
            Choice("range", name="[Custom — manual select]"),
        ]

        # Create item choices with numbering
        for disp_no, (t, idx, item) in enumerate(entries, start=1):
            display_map[disp_no] = (t, idx)
            core = format_core(item, t)
            prefix = "|Fanclub| " if item.get("isFanclubOnly") else ""
            community_name = f"| {custom_dict(await get_community(item.get('communityId')))} |"
            ts = await convert_to_korea_time(item["publishedAt"])
            name = (
                f"{disp_no:4d} {ts} {t.upper():5s} {prefix} "
                f"{community_name} [{core}] {item['title']} "
            )
            item_choices.append(Choice(value=disp_no, name=name))
            
        if item_choices == []:
            logger.info(f"No items found")
            return
        
        separator = '━' * 70
        # Initial selection with fuzzy search
        cmd = await inquirer.fuzzy(
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
        else:
            # for choese only one
            picks = {cmd}
        if cmd == "range":
            # Prepare choices for checkbox (only item choices, not quick commands)
            final = await inquirer.checkbox(
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
                transformer=lambda res: f"{len(res)} ✅ selected"
            ).execute_async()
            picks = set(final)

        return self._collect(picks, display_map)

    def _collect(self, picks: Set[int], display_map: Dict[int, Tuple[str, int]]) -> dict:
        try:
            vods = [
                self.vod_items[idx]
                for n in picks
                if (t := display_map[n])[0] == "vod"
                for idx in [t[1]]
            ]
            photos = [
                self.photo_items[idx]
                for n in picks
                if (t := display_map[n])[0] == "photo"
                for idx in [t[1]]
            ]
            lives = [
                self.live_items[idx]
                for n in picks
                if (t := display_map[n])[0] == "live"
                for idx in [t[1]]
            ]
            post = [
                self.post_items[idx]
                for n in picks
                if (t := display_map[n])[0] == "post"
                for idx in [t[1]]
            ]
            return {"vods": vods, "photos": photos, "lives": lives, "post": post}
        except KeyError:
            pass

async def convert_to_korea_time(iso_string_utc: str) -> str:
    dt_utc = datetime.fromisoformat(iso_string_utc.replace('Z', '+00:00'))
    dt_kst = dt_utc.astimezone(ZoneInfo("Asia/Seoul"))
    formatted_string = dt_kst.strftime("%y%m%d_%H:%M")
    return formatted_string

def format_core(item: dict, t: str) -> str:
    try:
        if t == "vod":
            return f"{item['vod']['duration'] / 60:.1f}  min"
        elif t == "photo":
            return f"{item['photo']['imageCount']}    imgs"
        elif t == "live":
            return f"{item['live']['replay']['duration'] / 60:.1f}  min"
        elif t == "post" and item.get("imageInfo"):
            image_count = f"{len(item.get("imageInfo")[1])}"
            match image_count:
                case '0':
                    return "POST-ONLY"
                case _:
                    return f"{image_count}    imgs"
    except TypeError:
        return 'Live-noreplay'
    return "unknown"