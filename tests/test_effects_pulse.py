"""DockPulseEffect blips a widget's contents margins on downbeats."""

import numpy as np
from PySide6.QtCore import QVariantAnimation
from PySide6.QtWidgets import QWidget

from lightfall_vibe.audio.features import N_BANDS, VibeFrame
from lightfall_vibe.effects.pulse import DockPulseEffect


def _beat() -> VibeFrame:
    return VibeFrame(
        bands=np.zeros(N_BANDS), rms=0.2, centroid=0.5, flux=0.5, beat=True
    )


def test_beat_pulses_margins_then_returns_to_original(qtbot):
    target = QWidget()
    qtbot.addWidget(target)
    target.setContentsMargins(0, 0, 0, 0)
    effect = DockPulseEffect(target=target)
    assert effect.attach() is True

    effect.on_frame(_beat())
    # Mid-animation the margins grow...
    qtbot.waitUntil(lambda: target.contentsMargins().left() > 0, timeout=500)
    # ...and settle back to the original.
    qtbot.waitUntil(lambda: target.contentsMargins().left() == 0, timeout=1000)
    effect.detach()


def test_detach_mid_pulse_restores_margins(qtbot):
    target = QWidget()
    qtbot.addWidget(target)
    target.setContentsMargins(2, 2, 2, 2)
    effect = DockPulseEffect(target=target)
    effect.attach()
    effect.on_frame(_beat())
    effect.detach()  # immediately, while animation may be running
    margins = target.contentsMargins()
    assert (margins.left(), margins.top()) == (2, 2)


def test_attach_returns_false_without_target(qtbot):
    effect = DockPulseEffect(target=None)
    assert effect.attach() is False


def test_second_beat_after_completed_pulse_does_not_crash(qtbot):
    """Regression: per-beat animations with finished->deleteLater left
    self._anim as a wrapper around a deleted C++ object; the next beat's
    state() check raised RuntimeError (seen live 2026-06-06)."""
    target = QWidget()
    qtbot.addWidget(target)
    effect = DockPulseEffect(target=target)
    effect.attach()

    effect.on_frame(_beat())
    qtbot.waitUntil(lambda: target.contentsMargins().left() > 0, timeout=500)
    qtbot.waitUntil(lambda: target.contentsMargins().left() == 0, timeout=1000)
    qtbot.wait(50)  # extra event-loop turns: any deleteLater executes here

    for _ in range(4):  # beats 2-5; the 5th is the next downbeat
        effect.on_frame(_beat())  # crashed with RuntimeError before the fix
    qtbot.waitUntil(lambda: target.contentsMargins().left() > 0, timeout=500)
    effect.detach()
    margins = target.contentsMargins()
    assert margins.left() == 0


def test_pulses_only_every_fourth_beat(qtbot):
    """No bar-phase tracking, so 'downbeat' = every 4th detected onset."""
    target = QWidget()
    qtbot.addWidget(target)
    effect = DockPulseEffect(target=target)
    effect.attach()

    def _running() -> bool:
        return (
            effect._anim is not None
            and effect._anim.state() == QVariantAnimation.State.Running
        )

    pulses = 0
    for _ in range(8):
        was_running = _running()
        effect.on_frame(_beat())
        if _running() and not was_running:  # this beat STARTED a pulse
            pulses += 1
            # Let the pulse visibly run and fully finish, so the next
            # started-pulse detection can't be masked by this one.
            qtbot.waitUntil(lambda: target.contentsMargins().left() > 0, timeout=500)
            qtbot.waitUntil(lambda: not _running(), timeout=1000)
            qtbot.wait(20)
    assert pulses == 2  # beats 1 and 5
    effect.detach()
