import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from typing import Dict, List, Set, Tuple, Union, Any

from unit.community import get_community, custom_dict

MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]
Key = Tuple[str, int]


class InquirerPySelector:
    def __init__(self, vod_list: List[dict], photo_list: List[dict], live_list: List[dict]):
        self.vod_items = vod_list
        self.photo_items = photo_list
        self.live_items = live_list

    async def run(self) -> dict:
        display_map: Dict[int, Tuple[str,int]] = {}
        item_choices: List[Choice] = []
        entries: List[Tuple[str,int,dict]] = []

        await asyncio.gather(
            asyncio.to_thread(lambda: [entries.append(("vod", idx, item)) for idx, item in enumerate(self.vod_items)]),
            asyncio.to_thread(lambda: [entries.append(("photo", idx, item)) for idx, item in enumerate(self.photo_items)]),
            asyncio.to_thread(lambda: [entries.append(("live", idx, item)) for idx, item in enumerate(self.live_items)])
        )
        entries.sort(key=lambda x: x[2]["publishedAt"])

        # Create quick command choices (not numbered, not in checkbox)
        quick_commands = [
            Choice("all", name="all VOD & Photos "),
            Choice("vall", name="all VOD          "),
            Choice("pall", name="all Photos       "),
            Choice("range", name="range — custom ranges/manual"),
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

        # Combine quick commands and item choices
        all_choices = quick_commands + item_choices

        # Initial selection with fuzzy search
        cmd = await inquirer.fuzzy(
            message="Select items or quick command:",
            choices=all_choices,
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
        elif cmd == "range":
            # Print all numbered items for reference
            print()
            for n, (t, i) in display_map.items():
                itm = self.vod_items[i] if t == "vod" else self.photo_items[i]
                core = format_core(item, t)
                label = "🎬 VOD" if t == "vod" else "📷 Photo"
                print(f"  {n:2d}. {label:<6}: {itm['title']} ({core})")
            print()

            text = await inquirer.text(
                message="Enter numbers/ranges (e.g. 1-5,11_15,16 20):"
            ).execute_async()
            picks = parse_range_input(text, display_map)

        if cmd == "range":
            # Prepare choices for checkbox (only item choices, not quick commands)
            adjust_choices: List[Choice] = []
            for c in item_choices:
                adjust_choices.append(
                    Choice(
                        value=c.value,
                        name=c.name,
                        enabled=(c.value in picks)
                    )
                )

            final = await inquirer.fuzzy(  # Use fuzzy prompt for checkbox
                message="Finalize your selection (→ all, ← none, type to filter):",
                choices=adjust_choices,
                cycle=False,
                height=30,
                border=True,
                multiselect=True,  # Enable multiple selections
                validate=lambda res: len(res) > 0 or "",
                keybindings={
                    "toggle-all-true": [{"key": "right"}],
                    "toggle-all-false": [{"key": "left"}],
                },
                instruction="→ select all, ← deselect all",
                transformer=lambda res: f"✅ {len(res)} selected"
            ).execute_async()
            picks = set(final)

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
        return {"vods": vods, "photos": photos}
    
    def _collect(self, picks: Set[int], display_map: Dict[int, Tuple[str,int]]) -> dict:
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
        return {"vods": vods, "photos": photos}
    def _build_media_choices(
        self,
        preselected: Set[int],
        display_map: Dict[int, Tuple[str,int]]
    ) -> List[Choice]:
        choices: List[Choice] = []
        # VOD 區塊
        choices.append(Separator("━━ 🎬 VODs ━━"))
        for disp_no, (t, idx) in display_map.items():
            if t != "vod":
                continue
            item = self.vod_items[idx]
            name = f"<{disp_no:2d}> {item['title']}"
            choices.append(
                Choice(value=disp_no, name=name, enabled=(disp_no in preselected))
            )
        # Photo 區塊
        choices.append(Separator(" "))
        choices.append(Separator("━━ 📷 Photos ━━"))
        for disp_no, (t, idx) in display_map.items():
            if t != "photo":
                continue
            item = self.photo_items[idx]
            name = f"<{disp_no:2d}> {item['title']}"
            choices.append(
                Choice(value=disp_no, name=name, enabled=(disp_no in preselected))
            )
        return choices

def parse_selection_input(text: str, display_map: dict[int, tuple[str, int]]) -> set[int]:
    picks = set()
    tokens = re.split(r"[,\s]+", text.strip().lower())

    for token in tokens:
        if not token:
            continue

        typ = None
        raw = token

        # 類型前綴處理
        if token.startswith("v"):
            typ, token = "vod", token[1:]
        elif token.startswith("p"):
            typ, token = "photo", token[1:]

        try:
            if "-" in token:
                lo, hi = sorted(map(int, token.split("-", 1)))
                for n in range(lo, hi + 1):
                    if n in display_map and (typ is None or display_map[n][0] == typ):
                        picks.add(n)
            elif token.isdigit():
                n = int(token)
                if n in display_map and (typ is None or display_map[n][0] == typ):
                    picks.add(n)
        except ValueError:
            print(f"Ignore invalid input: {raw}")
            continue

    return picks

async def convert_to_korea_time(iso_string_utc: str) -> str:
    dt_utc = datetime.fromisoformat(iso_string_utc.replace('Z', '+00:00'))
    dt_kst = dt_utc.astimezone(ZoneInfo("Asia/Seoul"))
    formatted_string = dt_kst.strftime("%y%m%d_%H:%M")
    return formatted_string

def parse_range_input(
    text: str,
    display_map: Dict[int, Tuple[str,int]]
) -> Set[int]:
    picks: Set[int] = set()
    tokens = re.split(r"[,\s]+", text.strip().lower())
    for raw in tokens:
        token = raw.strip()
        if not token:
            continue
        typ = None
        if token.startswith("v"):
            typ, token = "vod", token[1:]
        elif token.startswith("p"):
            typ, token = "photo", token[1:]
        m = re.match(r"^(\d+)[\-\_,](\d+)$", token)
        if m:
            lo, hi = sorted((int(m.group(1)), int(m.group(2))))
            for n in range(lo, hi+1):
                if n in display_map and (typ is None or display_map[n][0]==typ):
                    picks.add(n)
            continue
        if token.isdigit():
            n = int(token)
            if n in display_map and (typ is None or display_map[n][0]==typ):
                picks.add(n)
    return picks

def format_core(item: dict, t: str) -> str:
    if t == "vod":
        return f"{item['vod']['duration'] / 60:.1f} min"
    elif t == "photo":
        return f"{item['photo']['imageCount']} imgs"
    elif t == "live":
        return f"{item['live']['replay']['duration'] / 60:.1f} min"
    return "unknown"