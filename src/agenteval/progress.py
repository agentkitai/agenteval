"""Progress reporting for eval runs — rich progress bar with print fallback."""

from __future__ import annotations

from typing import Optional


class ProgressReporter:
    """Reports eval progress via rich or simple print fallback."""

    def __init__(self) -> None:
        self._total = 0
        self._completed = 0
        self._rich_progress: Optional[object] = None
        self._rich_task: Optional[object] = None

    def start(self, total: int) -> None:
        self._total = total
        self._completed = 0
        try:
            from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn
            self._rich_progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
            )
            self._rich_task = self._rich_progress.add_task("Evaluating", total=total)  # type: ignore[union-attr]
            self._rich_progress.start()  # type: ignore[union-attr]
        except ImportError:
            self._rich_progress = None

    def update(self, case_name: str, passed: bool) -> None:
        self._completed += 1
        if self._rich_progress is not None:
            self._rich_progress.update(self._rich_task, advance=1, description=case_name)  # type: ignore[union-attr]
        else:
            icon = "✓" if passed else "✗"
            print(f"[{self._completed}/{self._total}] {case_name}: {icon}")

    def finish(self) -> None:
        if self._rich_progress is not None:
            self._rich_progress.stop()  # type: ignore[union-attr]
            self._rich_progress = None
