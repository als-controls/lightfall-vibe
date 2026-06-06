"""ThemeEffect: cumulative hue walk of accent colors on each beat.

Mutation mechanism mirrors lightfall-dev-plugins' palette_test_panel:
setattr on ThemeManager._colors fields, then emit colors_changed. Only
accents are touched -- background/surface/text stay readable.
"""

from __future__ import annotations

import time

from PySide6.QtGui import QColor

from lightfall.ui.theme.manager import ThemeManager

from lightfall_vibe.audio.features import VibeFrame

_ACCENT_FIELDS = ("primary", "secondary", "success", "warning", "error", "info")
_HUE_STEP_DEG = 47.0  # pseudo-golden step: cycles through hues non-repetitively
_MIN_EMIT_INTERVAL_S = 0.1  # app-wide restyle is the perf hazard: cap at 10 Hz


def _rotate_hue(hex_color: str, degrees: float) -> str:
    color = QColor(hex_color)
    h, s, v, a = color.getHsvF()
    if h < 0:  # achromatic (grays) have no hue to rotate
        return hex_color
    color.setHsvF((h + degrees / 360.0) % 1.0, s, v, a)
    return color.name()


class ThemeEffect:
    """Rotates accent hues by a fixed step on every (throttled) beat."""

    name = "theme"

    def __init__(self, manager: ThemeManager | None = None) -> None:
        self._manager = manager
        self._snapshot: dict[str, str] | None = None
        self._hue = 0.0
        self._last_emit = 0.0

    def attach(self) -> bool:
        if self._snapshot is not None:  # already attached
            return True
        manager = self._manager or ThemeManager.get_instance()
        self._manager = manager
        self._snapshot = dict(vars(manager._colors))
        self._hue = 0.0
        self._last_emit = 0.0
        manager.theme_changed.connect(self._on_theme_changed)
        return True

    def on_frame(self, frame: VibeFrame) -> None:
        if not frame.beat or self._manager is None or self._snapshot is None:
            return
        now = time.monotonic()
        if now - self._last_emit < _MIN_EMIT_INTERVAL_S:
            return
        self._last_emit = now
        self._hue = (self._hue + _HUE_STEP_DEG) % 360.0
        for field in _ACCENT_FIELDS:
            rotated = _rotate_hue(self._snapshot[field], self._hue)
            setattr(self._manager._colors, field, rotated)
        self._manager.colors_changed.emit()

    def _on_theme_changed(self, _theme_name: str) -> None:
        """User switched themes mid-vibe: walk from the new theme's colors."""
        if self._manager is not None:
            self._snapshot = dict(vars(self._manager._colors))
            self._hue = 0.0

    def detach(self) -> None:
        if self._manager is None or self._snapshot is None:
            return
        self._manager.theme_changed.disconnect(self._on_theme_changed)
        for field, value in self._snapshot.items():
            setattr(self._manager._colors, field, value)
        self._snapshot = None
        self._manager.colors_changed.emit()
