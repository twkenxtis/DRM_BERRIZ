import asyncio
from typing import Dict, List, Set, Tuple, Union
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator


MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]
Key = Tuple[str, int]


class InquirerPySelector:
    def __init__(self,
                 vod_list: List[Dict],
                 photo_list: List[Dict]):
        self.vod_items = vod_list
        self.photo_items = photo_list
        self.number_to_item: Dict[int, Key] = {}
        self._build_number_map()

    def _build_number_map(self) -> None:
        """1-based index → 媒體(type,index)"""
        self.number_to_item.clear()
        idx = 1
        for i in range(len(self.vod_items)):
            self.number_to_item[idx] = ("vod", i)
            idx += 1
        for i in range(len(self.photo_items)):
            self.number_to_item[idx] = ("photo", i)
            idx += 1

    def _build_media_choices(
        self, preselected: Set[Key]
    ) -> List[Choice]:
        """
        純媒體 Choice 清單，分段加上 fancy separator，
        並在 VOD / Photo 之間留白一行
        """
        choices: List[Choice] = []
        idx = 1

        # VODs 段落
        choices.append(Separator("━━ 🎬 VODs ━━"))
        for i, vod in enumerate(self.vod_items):
            title = vod.get("title", "Untitled")
            dur = vod.get("vod", {}).get("duration", "N/A")
            choices.append(
                Choice(
                    value=("vod", i),
                    name=f"{idx:2d}. {title} ({dur}s)",
                    enabled=("vod", i) in preselected
                )
            )
            idx += 1

        # 空一行讓版面更清爽
        if self.photo_items:
            choices.append(Separator(""))

        # Photos 段落
        if self.photo_items:
            choices.append(Separator("━━ 📷 Photos ━━"))
            for i, photo in enumerate(self.photo_items):
                title = photo.get("title", "Untitled")
                cnt = photo.get("photo", {}).get("imageCount", "N/A")
                choices.append(
                    Choice(
                        value=("photo", i),
                        name=f"{idx:2d}. {title} ({cnt} imgs)",
                        enabled=("photo", i) in preselected
                    )
                )
                idx += 1

        return choices

    async def run(self) -> SelectedMedia:
        # 1) fuzzy multiselect：可打字過濾命令或直接勾選
        commands_and_items: List[Choice] = [
            Choice("vall", name="vall — Choose all VOD"),
            Choice("pall", name="pall — Choose all Photos"),
            Choice("range", name="range — Select by range [e.g. 1-11]"),
            Choice("all", name="all — Choose all VOD and Photos"),
        ]
        for idx, (t, i) in self.number_to_item.items():
            item = self.vod_items[i] if t == "vod" else self.photo_items[i]
            extra = (
                f"{item['vod']['duration']}s"
                if t == "vod" else
                f"{item['photo']['imageCount']} imgs"
            )
            commands_and_items.append(
                Choice(
                    value=(t, i),
                    name=f"{idx:2d}. [{t.upper()}] {item['title']} ({extra})"
                )
            )

        selected = await inquirer.fuzzy(
            message="💡 Type to filter or pick a command/item:",
            choices=commands_and_items,
            multiselect=True,
            cycle=False,
            height=30,
            border=True,
            instruction="Check the space and press Enter to confirm; you can directly select vall/pall/range/all",
            transformer=lambda res: f"🎯 {len(res)} items chosen"
        ).execute_async()

        # 2) 拆出命令 & 預選清單
        cmds: Set[str] = set()
        picked: Set[Key] = set()
        for v in selected:
            if isinstance(v, str):
                cmds.add(v.lower())
            else:
                picked.add(v)

        # 3) vall/pall/all 處理
        if "vall" in cmds:
            picked |= {("vod", i) for i in range(len(self.vod_items))}
        if "pall" in cmds:
            picked |= {("photo", i) for i in range(len(self.photo_items))}
        if "all" in cmds:
            picked |= {("vod", i) for i in range(len(self.vod_items))}
            picked |= {("photo", i) for i in range(len(self.photo_items))}

        # 4) range 處理：印 fancy 清單 + 輸入解析
        if "range" in cmds:
            # fancy 列印可選列表，並在兩段之間空行
            vcount = len(self.vod_items)
            for idx, (t, i) in self.number_to_item.items():
                if idx == vcount + 1:
                    print()
                item = self.vod_items[i] if t == "vod" else self.photo_items[i]
                extra = (
                    f"{item['vod']['duration']}s"
                    if t == "vod" else
                    f"{item['photo']['imageCount']} imgs"
                )
                label = "🎬 VOD" if t == "vod" else "📷 Photo"
                print(f"  {idx:>2}. {label:<8}: {item['title']} ({extra})")
            print()

            text = await inquirer.text(
                message="🔢 Please enter a number or range (e.g. 5-10, v3-6, p12,15):"
            ).execute_async()

            for part in (p.strip().lower() for p in text.split(",") if p.strip()):
                typ = None
                if part.startswith("v"):
                    typ, part = "vod", part[1:]
                elif part.startswith("p"):
                    typ, part = "photo", part[1:]
                
                if "-" in part:
                    a, b = part.split("-", 1)
                    if a.isdigit() and b.isdigit():
                        lo, hi = sorted((int(a), int(b)))
                        for n in range(lo, hi + 1):
                            item = self.number_to_item.get(n)
                            if item and (typ is None or item[0] == typ):
                                picked.add(item)
                elif part.isdigit():
                    n = int(part)
                    item = self.number_to_item.get(n)
                    if item and (typ is None or item[0] == typ):
                        picked.add(item)

            # 5) 只有在 range 模式下才給微調 checkbox
            final = await inquirer.checkbox(
                message="Fine-tune final selection (check/uncheck the spacebar):",
                choices=self._build_media_choices(preselected=picked),
                cycle=False,
                height=30,
                border=True,
                keybindings={
                    "toggle-all-true": [{"key": "right"}],
                    "toggle-all-false": [{"key": "left"}],
                },
                instruction="→ Select all, ← Deselect all",
                transformer=lambda res: f"✅ {len(res)} selected"
            ).execute_async()

            picked = set(final)

        # 6) 非 range 模式直接回傳 picked
        vods = [self.vod_items[i] for t, i in picked if t == "vod"]
        photos = [self.photo_items[i] for t, i in picked if t == "photo"]
        return {"vods": vods, "photos": photos}