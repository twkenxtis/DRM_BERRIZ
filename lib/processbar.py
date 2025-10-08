from time import time

from rich.console import Console

class ProgressBar:
    def __init__(self, total: int, prefix: str = "", length: int = 65):
        self.total = total
        self.prefix = prefix
        self.length = length
        self.current = 0
        self.console = Console()
        self.start_time = time()

    def _format_time(self, seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    def update(self, progress: int = None):
        if progress is not None:
            self.current = progress
        else:
            self.current += 1

        percent = self.current / self.total
        filled_length = int(self.length * percent)
        bar = (
            "[magenta]" + "_" * filled_length + "[/magenta]"
            + "[grey37]" + "/" * (self.length - filled_length) + "[/grey37]"
        )
        elapsed = time() - self.start_time
        elapsed_str = self._format_time(elapsed)

        text = (
            f"[cyan]{self.prefix:6}[/]: {bar} "
            f"{percent*100:6.2f} % | {self.current}/{self.total} "
            f" [red]{elapsed_str}[/red]"
        )

        self.console.print(text, end="\r")

    def finish(self):
        self.update(self.total)
        self.console.print("")
