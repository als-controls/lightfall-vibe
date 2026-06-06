"""VibeConductor: lifecycle, effect fan-out, and failure isolation."""

import numpy as np
from PySide6.QtCore import QObject, Signal

from lightfall_vibe.audio.features import N_BANDS, VibeFrame
from lightfall_vibe.conductor import VibeConductor


class FakeCapture(QObject):
    frame_ready = Signal(object)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False


class FakeEffect:
    def __init__(self, name="fake", attach_ok=True, explode=False):
        self.name = name
        self._attach_ok = attach_ok
        self._explode = explode
        self.attached = False
        self.frames = []

    def attach(self):
        self.attached = self._attach_ok
        return self._attach_ok

    def on_frame(self, frame):
        if self._explode:
            raise RuntimeError("effect crashed")
        self.frames.append(frame)

    def detach(self):
        self.attached = False


def _frame(beat=False) -> VibeFrame:
    return VibeFrame(
        bands=np.zeros(N_BANDS), rms=0.1, centroid=0.5, flux=0.0, beat=beat
    )


def _make(effects):
    capture = FakeCapture()
    conductor = VibeConductor(
        capture_factory=lambda device_id, sensitivity: capture,
        effect_factories={e.name: (lambda e=e: e) for e in effects},
    )
    return conductor, capture


def test_start_attaches_enabled_effects_and_starts_capture():
    effect = FakeEffect()
    conductor, capture = _make([effect])
    conductor.set_effect_enabled("fake", True)
    conductor.start()
    assert capture.started
    assert effect.attached
    conductor.stop()
    assert not capture.started
    assert not effect.attached


def test_frames_fan_out_and_rebroadcast(qtbot):
    effect = FakeEffect()
    conductor, capture = _make([effect])
    conductor.set_effect_enabled("fake", True)
    conductor.start()
    received = []
    conductor.frame_ready.connect(received.append)
    capture.frame_ready.emit(_frame())
    assert len(effect.frames) == 1
    assert len(received) == 1
    conductor.stop()


def test_crashing_effect_is_detached_others_survive():
    bomb = FakeEffect(name="bomb", explode=True)
    good = FakeEffect(name="good")
    conductor, capture = _make([bomb, good])
    conductor.set_effect_enabled("bomb", True)
    conductor.set_effect_enabled("good", True)
    conductor.start()
    capture.frame_ready.emit(_frame())
    capture.frame_ready.emit(_frame())
    assert not bomb.attached  # detached after first crash
    assert len(good.frames) == 2
    conductor.stop()


def test_effect_failing_attach_is_skipped():
    effect = FakeEffect(attach_ok=False)
    conductor, capture = _make([effect])
    conductor.set_effect_enabled("fake", True)
    conductor.start()
    capture.frame_ready.emit(_frame())
    assert effect.frames == []
    conductor.stop()


def test_toggle_effect_while_running():
    effect = FakeEffect()
    conductor, capture = _make([effect])
    conductor.start()
    assert not effect.attached
    conductor.set_effect_enabled("fake", True)
    assert effect.attached
    conductor.set_effect_enabled("fake", False)
    assert not effect.attached
    conductor.stop()


def test_capture_failure_stops_conductor(qtbot):
    effect = FakeEffect()
    conductor, capture = _make([effect])
    conductor.set_effect_enabled("fake", True)
    conductor.start()
    with qtbot.waitSignal(conductor.stopped, timeout=1000):
        capture.failed.emit("no device")
    assert not effect.attached
    assert not conductor.is_running


def test_beat_signal_emitted(qtbot):
    conductor, capture = _make([])
    conductor.start()
    with qtbot.waitSignal(conductor.beat, timeout=1000):
        capture.frame_ready.emit(_frame(beat=True))
    conductor.stop()
