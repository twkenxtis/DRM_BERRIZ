import os
from typing import Dict, List, Union

MediaItem = Dict[str, Union[str, Dict, bool]]
SelectedMedia = Dict[str, List[Dict]]

class InputHandler:
    def __init__(self, all_items, vod_items, photo_items, page_size):
        self.all_items = all_items
        self.vod_items = vod_items
        self.photo_items = photo_items
        self.page_size = page_size

    def process_tokens(self, tokens: List[str], current_page: int) -> int:
        for token in tokens:
            current_page = self._process_token(token, current_page)
        return current_page

    def _process_token(self, token: str, current_page: int) -> int:
        def select_all(items): [item.update({'selected': True}) for item in items]
        def page_up(): return max(0, current_page - 1)
        def page_down(): return min((len(self.all_items) - 1) // self.page_size, current_page + 1)
        def toggle_index(idx):
            if 0 <= idx < len(self.all_items):
                self.all_items[idx]['selected'] = not self.all_items[idx]['selected']
            else:
                print(f"[!] Index {idx + 1} is out of range.")

        command_map = {
            'vall': lambda: select_all(self.vod_items),
            'pall': lambda: select_all(self.photo_items),
            'k': page_up,
            'l': page_down,
        }

        if '-' in token and all(p.isdigit() for p in token.split('-')):
            try:
                start, end = map(int, token.split('-'))
                for i in range(start - 1, end):
                    if 0 <= i < len(self.all_items):
                        self.all_items[i]['selected'] = True
            except Exception:
                print(f"[!] Invalid range: {token}")
            return current_page

        if token in command_map:
            result = command_map[token]()
            return result if isinstance(result, int) else current_page

        if token.isdigit():
            toggle_index(int(token) - 1)
        else:
            print(f"[!] Unrecognized input: '{token}'")

        return current_page


class NumericSelector:
    def __init__(self, vod_list: List[Dict], photo_list: List[Dict], page_size: int = 60):
        self.vod_items = [{'type': 'vod', 'data': v, 'selected': False} for v in vod_list]
        self.photo_items = [{'type': 'photo', 'data': p, 'selected': False} for p in photo_list]
        self.all_items = self.vod_items + self.photo_items
        self.page_size = page_size
        self.current_page = 0
        self.input_handler = InputHandler(self.all_items, self.vod_items, self.photo_items, self.page_size)

    def _clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def _get_page_items(self) -> List[Dict]:
        start = self.current_page * self.page_size
        end = start + self.page_size
        return self.all_items[start:end]

    def _format_item(self, index: int, item: Dict) -> str:
        marker = "[*]" if item['selected'] else "[ ]"
        title = item['data'].get('title', 'Untitled')
        info = ""
        if item['type'] == 'vod':
            info = f"(Duration: {item['data']['vod'].get('duration', 'N/A')}s)"
        elif item['type'] == 'photo':
            info = f"({item['data']['photo'].get('imageCount', 'N/A')} images)"
        return f"{marker} {index + 1:>3}: {title} {info}"

    def _render_page(self):
        self._clear_screen()
        print(f"""
        📄 Page {self.current_page + 1}
        ─────────────────────────────────────────────
        Enter numbers to select media (space-separated):
        - Single index: 3
        - Range select: 5-7
        - 'vall' → select all videos
        - 'pall' → select all photos
        - 'k' / 'l' → previous / next page
        - Press Enter to confirm selection
        """)

        for i, item in enumerate(self._get_page_items(), start=self.current_page * self.page_size):
            print(self._format_item(i, item))
        print()
        

    def run(self) -> SelectedMedia:
        while True:
            self._render_page()
            user_input = input("Enter your selection: ").strip().lower()
            if not user_input:
                break
            tokens = user_input.split()
            self.current_page = self.input_handler.process_tokens(tokens, self.current_page)

        return {
            'vods': [i['data'] for i in self.vod_items if i['selected']],
            'photos': [i['data'] for i in self.photo_items if i['selected']]
        }
