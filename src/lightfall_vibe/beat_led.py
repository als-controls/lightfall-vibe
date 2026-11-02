"""Beat indicator for the Vibe preferences page (an ``Embed`` item).

A small round LED that flashes on every ``conductor.beat``, next to the text
"Beat detector (play music to test)". Colours come from the running theme
(``success`` lit, ``text_secondary`` unlit), falling back to palette roles.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from lightfall_vibe.conductor import get_conductor

LED_FLASH_MS = 120
_LED_SIZE = 16


def _color(name: str, fallback: QPalette.ColorRole, widget: QWidget) -> str:
    try:
        from lightfall.ui.theme import ThemeManager

        color = QColor(getattr(ThemeManager.get_instance().colors, name))
        if color.isValid():
            return color.name()
    except Exception:  # noqa: BLE001 - no theme (early init, tests)
        pass
    return widget.palette().color(fallback).name()


def _disconnect(signal, slot) -> None:
    try:
        signal.disconnect(slot)
    except (RuntimeError, TypeError):
        pass  # already disconnected


class BeatLed(QWidget):
    """LED plus caption; connected to the conductor until the widget is destroyed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._dot = QLabel(self)
        self._dot.setFixedSize(_LED_SIZE, _LED_SIZE)
        layout.addWidget(self._dot)
        layout.addWidget(QLabel("Beat detector (play music to test)", self))
        layout.addStretch(1)
        self._lit = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(LED_FLASH_MS)
        self._timer.timeout.connect(lambda: self._set_lit(False))
        self._set_lit(False)
        # The page rebuilds this widget on every show_scope and the conductor
        # outlives it: drop the connection by hand when the widget goes, so a
        # later beat never pokes a deleted label. The slot is a plain function:
        # disconnecting a bound method of a deleted widget fails in PySide6.
        beat = get_conductor().beat

        def on_beat() -> None:
            self._on_beat()

        beat.connect(on_beat)
        self.destroyed.connect(lambda *_: _disconnect(beat, on_beat))

    def is_lit(self) -> bool:
        return self._lit

    def _on_beat(self) -> None:
        self._set_lit(True)
        self._timer.start()

    def _set_lit(self, on: bool) -> None:
        self._lit = on
        color = (
            _color("success", QPalette.ColorRole.Highlight, self)
            if on
            else _color("text_secondary", QPalette.ColorRole.Mid, self)
        )
        self._dot.setStyleSheet(
            f"background-color: {color}; border-radius: {_LED_SIZE // 2}px;"
        )


def beat_led_factory(parent: QWidget | None = None) -> QWidget:
    """``Embed`` factory: a fresh beat LED, connected to the conductor."""
    return BeatLed(parent)
