"""SpinnerEffect drives a real SpinnerIndicator's rotation from RMS."""

import numpy as np

from lightfall.ui.widgets.runengine_control import SpinnerIndicator
from lightfall_vibe.audio.features import N_BANDS, VibeFrame
from lightfall_vibe.effects.spinner import SpinnerEffect


def _frame(rms: float, beat: bool = False) -> VibeFrame:
    return VibeFrame(
        bands=np.zeros(N_BANDS), rms=rms, centroid=0.5, flux=0.0, beat=beat
    )


def test_attach_takes_over_and_detach_restores(qtbot):
    spinner = SpinnerIndicator()
    qtbot.addWidget(spinner)
    spinner.set_status("idle")
    effect = SpinnerEffect(spinner=spinner)

    assert effect.attach() is True
    assert spinner._status == "running"  # color pixmap
    assert not spinner._spin_timer.isActive()  # we drive rotation ourselves

    effect.detach()
    assert spinner._status == "idle"
    assert not spinner._spin_timer.isActive()


def test_rotation_scales_with_rms(qtbot):
    spinner = SpinnerIndicator()
    qtbot.addWidget(spinner)
    effect = SpinnerEffect(spinner=spinner)
    effect.attach()

    start = spinner._rotation
    effect.on_frame(_frame(rms=0.0))
    no_motion = abs(spinner._rotation - start)

    effect.on_frame(_frame(rms=0.5))
    loud_delta = abs(spinner._rotation - start)

    assert no_motion == 0.0
    assert loud_delta > 0.0
    effect.detach()


def test_detach_restores_running_status_with_timer(qtbot):
    spinner = SpinnerIndicator()
    qtbot.addWidget(spinner)
    spinner.set_status("running")
    effect = SpinnerEffect(spinner=spinner)
    effect.attach()
    effect.detach()
    # set_status path restores spin-timer management for "running".
    assert spinner._status == "running"
    assert spinner._spin_timer.isActive()


def test_attach_returns_false_when_no_spinner_found(qtbot):
    effect = SpinnerEffect(spinner=None)
    # No main window with a SpinnerIndicator exists in the test app.
    assert effect.attach() is False
