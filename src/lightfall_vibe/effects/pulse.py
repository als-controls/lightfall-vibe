"""DockPulseEffect: blip the central widget's margins on each beat.

The subtlest effect and the first one overboard if it fights the layout
system -- off by default in settings.
"""

from __future__ import annotations

from PySide6.QtCore import QVariantAnimation
from PySide6.QtWidgets import QWidget

from lightfall_vibe.audio.features import VibeFrame
from lightfall_vibe.effects.base import find_main_window

_PULSE_PX = 4
_PULSE_MS = 140
# Pulse on the "downbeat" only. There's no bar-phase tracking (onset
# detection, not beat tracking), so downbeat = every Nth detected beat.
DEFAULT_BEATS_PER_PULSE = 8


class DockPulseEffect:
    """Animates contentsMargins base -> base+_PULSE_PX -> base on downbeats."""

    name = "pulse"

    def __init__(self, target: QWidget | None = None) -> None:
        self._target = target
        self._anim: QVariantAnimation | None = None
        self._base: tuple[int, int, int, int] | None = None
        self._beat_count = 0
        # Live-tunable from the settings page (via the conductor).
        self.beats_per_pulse = DEFAULT_BEATS_PER_PULSE

    def attach(self) -> bool:
        if self._base is not None:  # already attached
            return True
        target = self._target
        if target is None:
            window = find_main_window()
            if window is not None:
                target = window.centralWidget()
        if target is None:
            return False
        self._target = target
        margins = target.contentsMargins()
        self._base = (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        )
        self._beat_count = 0
        return True

    def on_frame(self, frame: VibeFrame) -> None:
        if not frame.beat or self._target is None or self._base is None:
            return
        self._beat_count += 1
        if (self._beat_count - 1) % self.beats_per_pulse != 0:  # beats 1, N+1...
            return
        if self._anim is None:
            self._anim = self._build_anim()
        if self._anim.state() == QVariantAnimation.State.Running:
            return  # let the current pulse finish
        self._anim.start()

    def _build_anim(self) -> QVariantAnimation:
        """One reusable animation per attach.

        Per-beat instances either leak (no deleteLater) or leave
        self._anim wrapping a deleted C++ object (finished->deleteLater
        destroys it while the Python wrapper survives; the next beat's
        state() check then raises RuntimeError -- seen live 2026-06-06).
        """
        anim = QVariantAnimation(self._target)
        anim.setStartValue(0.0)
        anim.setKeyValueAt(0.3, float(_PULSE_PX))
        anim.setEndValue(0.0)
        anim.setDuration(_PULSE_MS)
        anim.valueChanged.connect(self._apply_offset)
        return anim

    def _apply_offset(self, value: float) -> None:
        if self._target is None or self._base is None:
            return
        base = self._base
        offset = int(value)
        self._target.setContentsMargins(
            base[0] + offset, base[1] + offset, base[2] + offset, base[3] + offset
        )

    def detach(self) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None
        if self._target is not None and self._base is not None:
            self._target.setContentsMargins(*self._base)
        self._base = None
