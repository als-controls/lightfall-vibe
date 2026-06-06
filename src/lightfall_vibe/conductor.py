"""VibeConductor: GUI-thread hub between audio capture and UI effects.

Owns the CaptureWorker and the effect instances. Effects are exception-
guarded: a crashing effect is detached and dropped; vibe mode itself can
never take the host app down.
"""

from __future__ import annotations

from typing import Callable

from loguru import logger
from PySide6.QtCore import QObject, Signal

from lightfall_vibe.audio.capture import CaptureWorker
from lightfall_vibe.audio.features import VibeFrame
from lightfall_vibe.effects.base import VibeEffect
from lightfall_vibe.effects.pulse import DEFAULT_BEATS_PER_PULSE

EFFECT_NAMES = ("spinner", "theme", "pulse")
DEFAULT_ENABLED = {"spinner": True, "theme": True, "pulse": False}


def _default_capture_factory(device_id: str | None, sensitivity: float):
    return CaptureWorker(device_id=device_id, sensitivity=sensitivity)


def _default_effect_factories() -> dict[str, Callable[[], VibeEffect]]:
    from lightfall_vibe.effects.pulse import DockPulseEffect
    from lightfall_vibe.effects.spinner import SpinnerEffect
    from lightfall_vibe.effects.theme import ThemeEffect

    return {
        "spinner": SpinnerEffect,
        "theme": ThemeEffect,
        "pulse": DockPulseEffect,
    }


class VibeConductor(QObject):
    """Singleton-ish hub (module-level get_conductor()) for vibe mode.

    Signals:
        frame_ready: Re-broadcast VibeFrames for the spectrum panel.
        beat: Convenience signal on each beat frame (settings LED).
        started / stopped: Lifecycle notifications for UI state.
    """

    frame_ready = Signal(object)  # VibeFrame
    beat = Signal()
    started = Signal()
    stopped = Signal()

    def __init__(
        self,
        capture_factory: Callable[..., QObject] | None = None,
        effect_factories: dict[str, Callable[[], VibeEffect]] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._capture_factory = capture_factory or _default_capture_factory
        self._effect_factories = (
            effect_factories
            if effect_factories is not None
            else _default_effect_factories()
        )
        self._enabled: dict[str, bool] = dict(DEFAULT_ENABLED)
        # Restrict to effects this conductor actually knows how to build.
        for name in list(self._enabled):
            if name not in self._effect_factories:
                self._enabled.pop(name)
        for name in self._effect_factories:
            self._enabled.setdefault(name, False)
        self._active: dict[str, VibeEffect] = {}
        self._capture: QObject | None = None
        self.device_id: str | None = None
        self.sensitivity: float = 1.0
        self.beats_per_pulse: int = DEFAULT_BEATS_PER_PULSE

    @property
    def is_running(self) -> bool:
        return self._capture is not None

    def effect_enabled(self, name: str) -> bool:
        return self._enabled.get(name, False)

    def set_effect_enabled(self, name: str, enabled: bool) -> None:
        if name not in self._effect_factories:
            return
        self._enabled[name] = enabled
        if not self.is_running:
            return
        if enabled and name not in self._active:
            self._attach_effect(name)
        elif not enabled and name in self._active:
            self._detach_effect(name)

    def set_sensitivity(self, value: float) -> None:
        self.sensitivity = value
        capture = self._capture
        if capture is not None and hasattr(capture, "analyzer"):
            capture.analyzer.sensitivity = value  # plain float write: thread-safe

    def set_beats_per_pulse(self, value: int) -> None:
        self.beats_per_pulse = max(1, int(value))
        active = self._active.get("pulse")
        if active is not None and hasattr(active, "beats_per_pulse"):
            active.beats_per_pulse = self.beats_per_pulse

    def start(self) -> None:
        if self.is_running:
            return
        capture = self._capture_factory(self.device_id, self.sensitivity)
        capture.frame_ready.connect(self._on_frame)
        capture.failed.connect(self._on_capture_failed)
        self._capture = capture
        # Even if every effect fails to attach, capture stays useful:
        # the spectrum panel consumes frame_ready directly.
        for name, enabled in self._enabled.items():
            if enabled:
                self._attach_effect(name)
        capture.start()
        self.started.emit()
        logger.info("Vibe mode started (effects: {})", sorted(self._active))

    def stop(self) -> None:
        if not self.is_running:
            return
        capture = self._capture
        self._capture = None
        capture.stop()
        capture.deleteLater()
        for name in list(self._active):
            self._detach_effect(name)
        self.stopped.emit()
        logger.info("Vibe mode stopped")

    def _attach_effect(self, name: str) -> None:
        try:
            effect = self._effect_factories[name]()
            if hasattr(effect, "beats_per_pulse"):  # apply the live knob
                effect.beats_per_pulse = self.beats_per_pulse
            if effect.attach():
                self._active[name] = effect
            else:
                logger.warning("Vibe effect '{}' found no target; skipped", name)
        except Exception:
            logger.exception("Vibe effect '{}' failed to attach", name)

    def _detach_effect(self, name: str) -> None:
        effect = self._active.pop(name, None)
        if effect is None:
            return
        try:
            effect.detach()
        except Exception:
            logger.exception("Vibe effect '{}' failed to detach", name)

    def _on_frame(self, frame: VibeFrame) -> None:
        if self._capture is None:  # late queued frame after stop(); drop it
            return
        for name in list(self._active):
            try:
                self._active[name].on_frame(frame)
            except Exception:
                logger.exception("Vibe effect '{}' crashed; disabling it", name)
                self._detach_effect(name)
        self.frame_ready.emit(frame)
        if frame.beat:
            self.beat.emit()

    def _on_capture_failed(self, message: str) -> None:
        logger.warning("Vibe capture failed: {}", message)
        try:
            from lightfall.ui.toast import ToastManager

            ToastManager.get_instance().warning("Vibe mode stopped", message)
        except Exception:
            pass  # headless/test environment: log only
        self.stop()


_conductor: VibeConductor | None = None


def get_conductor() -> VibeConductor:
    """Module-level conductor shared by the settings page and the panel."""
    global _conductor
    if _conductor is None:
        _conductor = VibeConductor()
    return _conductor
