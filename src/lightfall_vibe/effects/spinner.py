"""SpinnerEffect: drive the RunEngine spinner's rotation from audio energy.

Deliberately pokes SpinnerIndicator privates (_spin_timer, _rotation,
_status) -- accepted brittleness for a demo toy, per the design spec. If
lightfall ever grows a public set_spin_rate(), switch to it.
"""

from __future__ import annotations

from lightfall.ui.widgets.runengine_control import SpinnerIndicator

from lightfall_vibe.audio.features import VibeFrame
from lightfall_vibe.effects.base import find_main_window

# rms ~0.12 (typical music) saturates rotation at this many deg per frame.
_MAX_DEG_PER_FRAME = 30.0
_RMS_FULL_SCALE = 0.125


class SpinnerEffect:
    """Spins the RunEngine spinner proportionally to audio RMS."""

    name = "spinner"

    def __init__(self, spinner: SpinnerIndicator | None = None) -> None:
        self._spinner = spinner
        self._saved_status: str | None = None

    def attach(self) -> bool:
        if self._saved_status is not None:  # already attached
            return True
        spinner = self._spinner
        if spinner is None:
            window = find_main_window()
            if window is not None:
                spinner = window.findChild(SpinnerIndicator)
        if spinner is None:
            return False
        self._spinner = spinner
        self._saved_status = spinner._status
        spinner._spin_timer.stop()  # we drive rotation per-frame instead
        spinner._status = "running"  # color pixmap without starting the timer
        spinner.update()
        return True

    def on_frame(self, frame: VibeFrame) -> None:
        spinner = self._spinner
        if spinner is None or self._saved_status is None:  # None = not attached
            return
        rate = _MAX_DEG_PER_FRAME * min(frame.rms / _RMS_FULL_SCALE, 1.0)
        if rate <= 0.0:
            return
        # Negative = same direction as the stock spinner.
        spinner._rotation = (spinner._rotation - rate) % 360
        spinner.update()

    def detach(self) -> None:
        spinner = self._spinner
        if spinner is None or self._saved_status is None:
            return
        status = self._saved_status
        self._saved_status = None
        # Route through set_status so timer management is restored.
        spinner._status = ""  # force set_status to re-evaluate
        spinner.set_status(status)
