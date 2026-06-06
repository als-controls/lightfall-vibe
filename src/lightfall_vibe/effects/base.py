"""Effect protocol and shared widget-finding helpers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from PySide6.QtWidgets import QApplication, QMainWindow

from lightfall_vibe.audio.features import VibeFrame


@runtime_checkable
class VibeEffect(Protocol):
    """One independently-toggleable UI effect.

    Lifecycle: attach() -> on_frame() xN -> detach(). attach() returns
    False if the effect's target widget can't be found (effect is then
    skipped). detach() must restore all host state it touched.
    """

    name: str

    def attach(self) -> bool: ...

    def on_frame(self, frame: VibeFrame) -> None: ...

    def detach(self) -> None: ...


def find_main_window() -> QMainWindow | None:
    """Locate the Lightfall main window among top-level widgets."""
    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        if isinstance(widget, QMainWindow):
            return widget
    return None
