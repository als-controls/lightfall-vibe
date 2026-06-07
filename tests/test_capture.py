"""Tests for CaptureWorker using a fake audio source (no hardware)."""

import warnings

import numpy as np
import pytest

from lightfall_vibe.audio.capture import (
    CaptureWorker,
    _silence_discontinuity_warnings,
)
from lightfall_vibe.audio.features import VibeFrame


class FakeRecorder:
    """Stands in for a soundcard recorder context manager."""

    def __init__(self, fail_after: int | None = None):
        self._fail_after = fail_after
        self._count = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def record(self, numframes):
        self._count += 1
        if self._fail_after is not None and self._count > self._fail_after:
            raise RuntimeError("device vanished")
        return np.zeros((numframes, 2), dtype=np.float32)


def test_worker_emits_frames(qtbot):
    worker = CaptureWorker(source_factory=lambda sr, bs: FakeRecorder())
    frames = []
    worker.frame_ready.connect(frames.append)
    with qtbot.waitSignal(worker.frame_ready, timeout=2000):
        worker.start()
    worker.stop()
    assert frames
    assert isinstance(frames[0], VibeFrame)


def test_worker_emits_failed_on_source_error(qtbot):
    worker = CaptureWorker(source_factory=lambda sr, bs: FakeRecorder(fail_after=2))
    with qtbot.waitSignal(worker.failed, timeout=2000) as blocker:
        worker.start()
    worker.stop()
    assert "device vanished" in blocker.args[0]


def test_stop_is_idempotent_and_joins(qtbot):
    worker = CaptureWorker(source_factory=lambda sr, bs: FakeRecorder())
    worker.start()
    worker.stop()
    worker.stop()  # second stop must not raise
    assert not worker.is_running


def test_stop_before_start_is_noop(qtbot):
    worker = CaptureWorker(source_factory=lambda sr, bs: FakeRecorder())
    worker.stop()
    assert not worker.is_running


def test_silence_discontinuity_warnings_filters_just_that_message(monkeypatch):
    sc = pytest.importorskip("soundcard")
    # Reset the install guard so the filter is (re)added for this test.
    import lightfall_vibe.audio.capture as capture_mod

    monkeypatch.setattr(capture_mod, "_warnings_silenced", False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.resetwarnings()
        _silence_discontinuity_warnings()
        warnings.warn("data discontinuity in recording", sc.SoundcardRuntimeWarning)
        warnings.warn("something else entirely", sc.SoundcardRuntimeWarning)
    messages = [str(w.message) for w in caught]
    assert "data discontinuity in recording" not in messages
    assert "something else entirely" in messages
