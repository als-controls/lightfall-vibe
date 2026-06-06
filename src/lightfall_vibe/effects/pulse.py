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


class DockPulseEffect:
    """Animates contentsMargins base -> base+_PULSE_PX -> base on each beat."""

    name = "pulse"

    def __init__(self, target: QWidget | None = None) -> None:
        self._target = target
        self._anim: QVariantAnimation | None = None
        self._base: tuple[int, int, int, int] | None = None

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
        return True

    def on_frame(self, frame: VibeFrame) -> None:
        if not frame.beat or self._target is None or self._base is None:
            return
        if (
            self._anim is not None
            and self._anim.state() == QVariantAnimation.State.Running
        ):
            return  # let the current pulse finish
        anim = QVariantAnimation(self._target)
        anim.setStartValue(0.0)
        anim.setKeyValueAt(0.3, float(_PULSE_PX))
        anim.setEndValue(0.0)
        anim.setDuration(_PULSE_MS)
        base = self._base
        target = self._target

        def apply(value: float) -> None:
            offset = int(value)
            target.setContentsMargins(
                base[0] + offset, base[1] + offset, base[2] + offset, base[3] + offset
            )

        anim.valueChanged.connect(apply)
        anim.finished.connect(anim.deleteLater)
        self._anim = anim
        anim.start()

    def detach(self) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        if self._target is not None and self._base is not None:
            self._target.setContentsMargins(*self._base)
        self._base = None
