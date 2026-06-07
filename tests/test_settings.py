"""VibeSettingsPlugin wires UI controls to the conductor and prefs."""

import pytest

import lightfall_vibe.conductor as conductor_mod
from lightfall_vibe.conductor import VibeConductor
from lightfall_vibe.settings import VibeSettingsPlugin


@pytest.fixture()
def conductor(qtbot, monkeypatch):
    """Install a conductor with no real audio or effects as the singleton."""
    from PySide6.QtCore import QObject, Signal

    class _Capture(QObject):
        frame_ready = Signal(object)
        failed = Signal(str)

        def start(self):
            pass

        def stop(self):
            pass

    class _InertEffect:
        def __init__(self, name):
            self.name = name

        def attach(self):
            return True

        def on_frame(self, frame):
            pass

        def detach(self):
            pass

    cond = VibeConductor(
        capture_factory=lambda device_id, sensitivity: _Capture(),
        effect_factories={
            n: (lambda n=n: _InertEffect(n)) for n in ("spinner", "theme", "pulse")
        },
    )
    monkeypatch.setattr(conductor_mod, "_conductor", cond)
    yield cond
    if cond.is_running:
        cond.stop()


def test_widget_builds_with_expected_controls(qtbot, conductor):
    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    assert plugin._enable_check is not None
    assert plugin._device_combo is not None
    assert plugin._sensitivity_slider is not None
    assert set(plugin._effect_checks) == {"spinner", "theme", "pulse"}


def test_enable_checkbox_starts_and_stops_conductor(qtbot, conductor):
    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    plugin._enable_check.setChecked(True)
    assert conductor.is_running
    plugin._enable_check.setChecked(False)
    assert not conductor.is_running


def test_sensitivity_slider_updates_conductor(qtbot, conductor):
    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    plugin._sensitivity_slider.setValue(20)  # slider 5..30 -> 0.5..3.0
    assert conductor.sensitivity == pytest.approx(2.0)


def test_effect_checkbox_toggles_conductor(qtbot, conductor):
    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    plugin._effect_checks["pulse"].setChecked(True)
    assert conductor.effect_enabled("pulse")
    plugin._effect_checks["pulse"].setChecked(False)
    assert not conductor.effect_enabled("pulse")


def test_save_and_load_settings_roundtrip(qtbot, conductor, monkeypatch):
    stored = {}

    class FakePrefs:
        def get(self, key, default=None):
            return stored.get(key, default)

        def set(self, key, value):
            stored[key] = value

    import lightfall_vibe.settings as settings_mod

    monkeypatch.setattr(
        settings_mod.PreferencesManager, "get_instance", staticmethod(FakePrefs)
    )

    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    plugin._sensitivity_slider.setValue(25)
    plugin._effect_checks["theme"].setChecked(False)
    plugin.save_settings()

    plugin2 = VibeSettingsPlugin()
    widget2 = plugin2.create_widget()
    qtbot.addWidget(widget2)
    plugin2.load_settings()
    assert plugin2._sensitivity_slider.value() == 25
    assert not plugin2._effect_checks["theme"].isChecked()


def test_pulse_beats_spinbox_updates_conductor(qtbot, conductor):
    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    assert plugin._pulse_beats_spin.value() == 8  # seeded from conductor default
    plugin._pulse_beats_spin.setValue(2)
    assert conductor.beats_per_pulse == 2


def test_pulse_beats_persist_roundtrip(qtbot, conductor, monkeypatch):
    stored = {}

    class FakePrefs:
        def get(self, key, default=None):
            return stored.get(key, default)

        def set(self, key, value):
            stored[key] = value

    import lightfall_vibe.settings as settings_mod

    monkeypatch.setattr(
        settings_mod.PreferencesManager, "get_instance", staticmethod(FakePrefs)
    )

    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    plugin._pulse_beats_spin.setValue(12)
    plugin.save_settings()

    plugin2 = VibeSettingsPlugin()
    widget2 = plugin2.create_widget()
    qtbot.addWidget(widget2)
    plugin2.load_settings()
    assert plugin2._pulse_beats_spin.value() == 12


def test_destroyed_widget_then_beat_does_not_crash(qtbot, conductor):
    plugin = VibeSettingsPlugin()
    # Deliberately NOT qtbot.addWidget(): the test destroys the widget
    # itself, and pytest-qt teardown would close a deleted C++ object.
    widget = plugin.create_widget()
    widget.deleteLater()
    qtbot.waitUntil(lambda: plugin._beat_led is None, timeout=1000)
    conductor.beat.emit()  # must not raise against deleted widgets


def test_reopen_does_not_accumulate_connections(qtbot, conductor):
    plugin = VibeSettingsPlugin()
    w1 = plugin.create_widget()  # destroyed below; not registered with qtbot
    w1.deleteLater()
    qtbot.waitUntil(lambda: plugin._beat_led is None, timeout=1000)
    w2 = plugin.create_widget()
    qtbot.addWidget(w2)
    conductor.beat.emit()  # one live connection, against w2's LED
    assert plugin._led_timer.isActive()


def test_self_stop_unchecks_enable(qtbot, conductor):
    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()
    qtbot.addWidget(widget)
    plugin._enable_check.setChecked(True)
    assert conductor.is_running
    conductor.stop()  # e.g. capture failure path
    assert not plugin._enable_check.isChecked()


def test_reopening_settings_does_not_restart_running_capture(qtbot, conductor):
    stored = {}

    class FakePrefs:
        def get(self, key, default=None):
            return stored.get(key, default)

        def set(self, key, value):
            stored[key] = value

    import lightfall_vibe.settings as settings_mod

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    monkeypatch.setattr(
        settings_mod.PreferencesManager, "get_instance", staticmethod(FakePrefs)
    )

    plugin = VibeSettingsPlugin()
    widget = plugin.create_widget()  # destroyed below; not registered with qtbot
    plugin._enable_check.setChecked(True)
    assert conductor.is_running
    stops = []
    conductor.stopped.connect(lambda: stops.append(1))
    # Simulate the dialog being closed and reopened mid-vibe.
    widget.deleteLater()
    qtbot.waitUntil(lambda: plugin._beat_led is None, timeout=1000)
    widget2 = plugin.create_widget()
    qtbot.addWidget(widget2)
    plugin.load_settings()
    assert conductor.is_running
    assert stops == []  # capture never restarted

    monkeypatch.undo()
