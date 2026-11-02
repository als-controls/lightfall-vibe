"""Characterization of the hand-built Vibe page (removed by the form rewrite)."""
from __future__ import annotations

import pytest

import lightfall_vibe.conductor as conductor_mod
import lightfall_vibe.settings as settings_mod
from lightfall_vibe.conductor import VibeConductor
from lightfall_vibe.settings import VibeSettingsPlugin


@pytest.fixture()
def conductor(qtbot, monkeypatch):
    from PySide6.QtCore import QObject, Signal

    class _Capture(QObject):
        frame_ready = Signal(object)
        failed = Signal(str)

        def start(self):
            pass

        def stop(self):
            pass

    cond = VibeConductor(capture_factory=lambda device_id, sensitivity: _Capture(), effect_factories={
        n: (lambda: None) for n in ("spinner", "theme", "pulse")})
    monkeypatch.setattr(conductor_mod, "_conductor", cond)
    yield cond
    if cond.is_running:
        cond.stop()


def test_old_page_writes_keys_unscoped(qtbot, conductor, monkeypatch):
    """The untouched old page writes every key, unscoped, on save (device: the first listed)."""
    devices = [("dev1", "Speakers (system audio)"), ("dev2", "Mic")]
    monkeypatch.setattr(settings_mod, "list_devices", lambda: devices)
    monkeypatch.setattr("lightfall_vibe.audio.capture.list_devices", lambda: devices)
    calls = []

    class FakePrefs:
        def get(self, key, default=None):
            return default

        def set(self, key, value, **kwargs):
            calls.append((key, value, kwargs))

    monkeypatch.setattr(settings_mod.PreferencesManager, "get_instance", staticmethod(FakePrefs))
    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    plugin.load_settings()
    plugin.save_settings()
    assert calls == [
        ("vibe.enabled", False, {}),
        ("vibe.sensitivity", 1.5, {}),
        ("vibe.pulse_beats", 8, {}),
        ("vibe.pulse_px", 4, {}),
        ("vibe.effect.spinner", True, {}),
        ("vibe.effect.theme", True, {}),
        ("vibe.effect.pulse", False, {}),
        ("vibe.device_id", "dev1", {}),  # never chosen: the first enumerated device
    ]
    assert conductor.device_id == "dev1"  # opening the page pinned the conductor's device
