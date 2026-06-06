"""Audio capture worker: soundcard -> SpectrumAnalyzer -> Qt signal.

The capture loop runs on a plain threading.Thread. Signals emitted from
that thread are auto-queued by Qt into the receiver's (GUI) thread, so no
extra marshaling is needed.
"""

from __future__ import annotations

import threading
from typing import Callable

from loguru import logger

from PySide6.QtCore import QObject, Signal

from lightfall_vibe.audio.features import SpectrumAnalyzer

_SAMPLERATE = 48000
_BLOCK_SIZE = 1024

# A source factory takes (samplerate, block_size) and returns a context
# manager whose value has .record(numframes) -> ndarray (frames, channels).
SourceFactory = Callable[[int, int], object]


def list_devices() -> list[tuple[str, str]]:
    """List capture devices as (device_id, display_label) pairs.

    Loopback devices (system audio) are listed first and labeled.
    Returns [] if the audio backend is unavailable.
    """
    try:
        import soundcard as sc

        devices = []
        for mic in sc.all_microphones(include_loopback=True):
            label = f"{mic.name} (system audio)" if mic.isloopback else mic.name
            devices.append((str(mic.id), label, mic.isloopback))
        devices.sort(key=lambda d: not d[2])  # loopback first
        return [(d[0], d[1]) for d in devices]
    except Exception:
        return []


def default_device_id() -> str | None:
    """Device id of the default speaker's loopback, or None."""
    try:
        import soundcard as sc

        speaker = sc.default_speaker()
        for mic in sc.all_microphones(include_loopback=True):
            if mic.isloopback and mic.name == speaker.name:
                return str(mic.id)
    except Exception:
        pass
    return None


def _soundcard_factory(device_id: str | None) -> SourceFactory:
    def factory(samplerate: int, block_size: int):
        import soundcard as sc

        dev = device_id or default_device_id()
        if dev is None:
            raise RuntimeError("No loopback device found; pick one in settings")
        mic = sc.get_microphone(dev, include_loopback=True)
        return mic.recorder(samplerate=samplerate, blocksize=block_size)

    return factory


class CaptureWorker(QObject):
    """Captures audio on a background thread and emits VibeFrames.

    Signals:
        frame_ready: VibeFrame for each captured block (~47 Hz).
        failed: Error message when the capture loop dies unexpectedly.
    """

    frame_ready = Signal(object)  # VibeFrame
    failed = Signal(str)

    def __init__(
        self,
        device_id: str | None = None,
        sensitivity: float = 1.0,
        source_factory: SourceFactory | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_factory = source_factory or _soundcard_factory(device_id)
        self.analyzer = SpectrumAnalyzer(
            samplerate=_SAMPLERATE, block_size=_BLOCK_SIZE, sensitivity=sensitivity
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="vibe-capture", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("vibe-capture thread did not stop within 2 s; leaking it")
            self._thread = None

    def _run(self) -> None:
        try:
            with self._source_factory(_SAMPLERATE, _BLOCK_SIZE) as rec:
                while not self._stop_event.is_set():
                    data = rec.record(numframes=_BLOCK_SIZE)
                    mono = data.mean(axis=1) if data.ndim == 2 else data
                    self.frame_ready.emit(self.analyzer.process(mono))
        except Exception as exc:  # noqa: BLE001 - report any capture death
            if not self._stop_event.is_set():
                self.failed.emit(str(exc))
