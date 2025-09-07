import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from typing import Dict, List, Set, Tuple, Union, Any

from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator

MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]
Key = Tuple[str, int]


class InquirerPySelector:
    def __init__(self, vod_list: List[Dict], photo_list: List[Dict]):
        self.vod_items = vod_list
        self.photo_items = photo_list

    async def run(self) -> SelectedMedia:
        base_cmds: List[Choice] = [
            Choice("all", name="[ all — Choose all VOD and Photos ]"),
            Choice("vall", name="[ vall — Choose all VOD ]"),
            Choice("pall", name="[ pall — Choose all Photos ]"),
            Choice("range", name="[ custom — Select by range (e.g. 1-33) ]"),
        ]
        
        vod_entries = sorted(
            [(idx, item) for idx, item in enumerate(self.vod_items)],
            key=lambda pair: pair[1]["publishedAt"]
        )

        photo_entries = sorted(
            [(idx, item) for idx, item in enumerate(self.photo_items)],
            key=lambda pair: pair[1]["publishedAt"]
        )

        media_entries: List[Tuple[str, int, MediaItem]] = [
            ("vod", idx, item) for idx, item in vod_entries
        ] + [
            ("photo", idx, item) for idx, item in photo_entries
        ]


        display_map: Dict[int, Key] = {}
        item_choices: List[Choice] = []
        start_no = len(base_cmds) + 1
        for disp_no, (t, i, item) in enumerate(media_entries, start=start_no):
            display_map[disp_no] = (t, i)
            # extra 字串：duration vs imageCount
            core = (
                f"{item['vod']['duration']}s" if t == "vod"
                else f"{item['photo']['imageCount']} imgs"
            )
            prefix = "|Fanclub| " if item.get("isFanclubOnly", False) else "          "
            Type = f"[🎬 {t.upper()}]  " if t.upper() == 'VOD' else f"[📷 {t.upper()}]"
            name = f"{disp_no:2d} {Type} {await convert_to_korea_time(item['publishedAt'])} {prefix}{item['title']} ({core})"
            
            item_choices.append(Choice(value=disp_no, name=name))

        commands_and_items = [*base_cmds, *item_choices]
        selected = await inquirer.fuzzy(
            message="🔍 Type to filter or pick a command/item:",
            choices=commands_and_items,
            multiselect=True,
            cycle=False,
            height=40,
            border=True,
            instruction="Check space & Enter; or select vall/pall/range/all",
            transformer=lambda res: f"🎯 {len(res)} items chosen"
        ).execute_async()

        cmds: Set[str] = set()
        picks: Set[int] = set()
        for v in selected:
            if isinstance(v, str):
                cmds.add(v.lower())
            elif isinstance(v, int):
                picks.add(v)

        if "all" in cmds:
            picks |= set(range(start_no, start_no + len(self.vod_items) + len(self.photo_items)))
        else:
            if "vall" in cmds:
                picks |= set(range(start_no, start_no + len(self.vod_items)))
            if "pall" in cmds:
                photo_start = start_no + len(self.vod_items)
                photo_end = photo_start + len(self.photo_items)
                picks |= set(range(photo_start, photo_end))



        if "range" in cmds:
            # 列印所有可選項
            for num in range(start_no, start_no + len(media_entries)):
                t, i = display_map[num]
                item = self.vod_items[i] if t == "vod" else self.photo_items[i]
                core = (
                    f"{item['vod']['duration']}s" if t == "vod"
                    else f"{item['photo']['imageCount']} imgs"
                )
                label = "🎬 VOD" if t == "vod" else "📷 Photo"
                print(f"  {num:2d}. {label:<8}: {item['title']} ({core})")
            print()

            text = await inquirer.text(
                message="🔢 Enter number(s)/ranges (e.g. 5-10, v3-6, p12,15):"
            ).execute_async()

            for part in (p.strip().lower() for p in text.split(",") if p.strip()):
                typ = None
                if part.startswith("v"):
                    typ, part = "vod", part[1:]
                elif part.startswith("p"):
                    typ, part = "photo", part[1:]
                if "-" in part:
                    lo, hi = sorted(map(int, part.split("-", 1)))
                    for n in range(lo, hi + 1):
                        if n in display_map and (typ is None or display_map[n][0] == typ):
                            picks.add(n)
                elif part.isdigit():
                    n = int(part)
                    if n in display_map and (typ is None or display_map[n][0] == typ):
                        picks.add(n)

            # 最後讓使用者微調
            final = await inquirer.checkbox(
                message="Fine-tune selection:",
                choices=self._build_media_choices(
                    preselected={display_map[n] for n in picks}
                ),
                cycle=False, height=30, border=True,
                keybindings={
                    "toggle-all-true": [{"key": "right"}],
                    "toggle-all-false": [{"key": "left"}],
                },
                instruction="→ select all, ← deselect all",
                transformer=lambda res: f"✅ {len(res)} selected"
            ).execute_async()

            picks = {self._find_disp_no(display_map, v) for v in final}

        vods = [self.vod_items[i] for n in picks if (t := display_map[n])[0] == "vod" for i in [t[1]]]
        photos = [self.photo_items[i] for n in picks if (t := display_map[n])[0] == "photo" for i in [t[1]]]
        return {"vods": vods, "photos": photos}

    def _find_disp_no(self, disp_map: Dict[int, Key], val: Key) -> int:
        """從 (type,index) 找回 display_no"""
        for num, key in disp_map.items():
            if key == val:
                return num
        raise KeyError(val)

    def _build_media_choices(
        self, preselected: Set[Key]
    ) -> List[Choice]:
        """維持原本 VOD／Photo 分段清單"""
        choices: List[Choice] = []
        idx = 1
        choices.append(Separator("━━ 🎬 VODs ━━"))
        for i, vod in enumerate(self.vod_items):
            choices.append(
                Choice(
                    value=("vod", i),
                    name=f"{idx:2d}. {vod.get('title','Untitled')} ({vod['vod']['duration']}s)",
                    enabled=("vod", i) in preselected
                )
            )
            idx += 1
        if self.photo_items:
            choices.append(Separator(""))
            choices.append(Separator("━━ 📷 Photos ━━"))
            for i, photo in enumerate(self.photo_items):
                choices.append(
                    Choice(
                        value=("photo", i),
                        name=f"{idx:2d}. {photo.get('title','Untitled')} ({photo['photo']['imageCount']} imgs)",
                        enabled=("photo", i) in preselected
                    )
                )
                idx += 1
        return choices


async def convert_to_korea_time(iso_string_utc: str) -> str:
    dt_utc = datetime.fromisoformat(iso_string_utc.replace('Z', '+00:00'))
    dt_kst = dt_utc.astimezone(ZoneInfo("Asia/Seoul"))
    formatted_string = dt_kst.strftime("%y%m%d_%H:%M")
    return formatted_string