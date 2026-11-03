"""Vibe page on the scope-aware form, with live preview of the running conductor.

The old hand-built page (characterized in the commit before the rewrite) wrote every
key unscoped on every save, even untouched, and drove the conductor directly from its
widgets with no way to undo that on Cancel. The form page writes only what the user
edited, at the scope shown (``vibe.device_id`` at This console, the rest at User);
``preview()`` pushes pending values into the conductor and ``revert_preview()`` puts
the conductor back as it was before the dialog, running or stopped.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import SIGNAL, QObject, Signal
from PySide6.QtWidgets import QComboBox, QLineEdit, QMessageBox, QPushButton

import lightfall_vibe.conductor as conductor_mod
from lightfall_vibe.conductor import VibeConductor
from lightfall_vibe.settings import VibeSettingsPlugin

USER, LOCAL, BRANCH, BEAMLINE = "user:u1", "local", "branch:7.0.1.1", "beamline:7.0.1"
WRITABLE = (USER, LOCAL, BRANCH)
ORDER = (BEAMLINE, BRANCH, LOCAL, USER)  # broadest first
ENABLED, DEVICE, SENS = "vibe.enabled", "vibe.device_id", "vibe.sensitivity"
BEATS, PX = "vibe.pulse_beats", "vibe.pulse_px"
EFFECTS = ("vibe.effect.spinner", "vibe.effect.theme", "vibe.effect.pulse")
USER_KEYS = (ENABLED, SENS, BEATS, PX, *EFFECTS)
DEVICES = [("dev1", "Speakers (system audio)"), ("dev2", "Mic")]


@pytest.fixture(autouse=True)
def _fresh_spec_registry():
    """Pages register specs and console keys process-wide; start each test clean."""
    from lightfall.scopes.keys import _reset_client_registry

    _reset_client_registry()
    yield
    _reset_client_registry()


@pytest.fixture()
def conductor(qtbot, monkeypatch):
    """Install a conductor with no real audio or effects as the singleton."""

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
    cond.events = []
    cond.started.connect(lambda: cond.events.append("start"))
    cond.stopped.connect(lambda: cond.events.append("stop"))
    yield cond
    if cond.is_running:
        cond.stop()


def _state(cond):
    return (
        cond.is_running,
        cond.device_id,
        cond.sensitivity,
        cond.beats_per_pulse,
        cond.pulse_px,
        tuple(cond.effect_enabled(n) for n in ("spinner", "theme", "pulse")),
    )


# ---------------------------------------------------------------------------
# Form harness (modelled on lightfall's tests/ui/preferences/test_devices_form.py)
# ---------------------------------------------------------------------------


class ScopedPrefs(QObject):
    """One layer per scope; a key's value is its narrowest layer."""

    scopes_changed = Signal(object)
    scope_info = SimpleNamespace(mode="server")

    def __init__(self):
        super().__init__()
        self.layers: dict = {}
        self.calls: list[tuple] = []

    def scope_choices(self):
        from lightfall.ui.preferences.scope_api import ScopeChoice

        return [
            ScopeChoice(USER, "user", "User", None, ""),
            ScopeChoice(LOCAL, "local", "This console", None, ""),
            ScopeChoice(BRANCH, "branch", "Branch", "maintainer", ""),
            ScopeChoice(BEAMLINE, "beamline", "Beamline", "viewer", "Read-only"),
        ]

    def default_scope(self):
        return USER

    def allowed_at(self, key, scope):
        from lightfall.ui.preferences.scope_api import allowed_at

        return allowed_at(self, key, scope)

    def writable_at(self, key, scope):
        return scope in WRITABLE and self.allowed_at(key, scope)

    def lock_at(self, key, scope):
        return None

    def layer_value(self, key, scope):
        return self.layers.get((scope, key))

    def inherited_items(self, key, scope):
        return {}

    def resolved_items(self, key):
        return {}

    def get(self, key, default=None):
        for s in reversed(ORDER):
            if (s, key) in self.layers:
                return self.layers[(s, key)]
        return default

    def set(self, key, value, *, scope=None):
        self.calls.append((key, value, scope))
        self.layers[(scope, key)] = value

    def remove(self, key, *, scope=None):
        self.calls.append((key, None, scope))
        self.layers.pop((scope, key), None)

    def subscribe(self, key, slot):
        pass

    def unsubscribe(self, key, slot):
        pass


@pytest.fixture
def env(monkeypatch, conductor):
    devices = list(DEVICES)
    listed: list[int] = []

    def list_devices():
        listed.append(1)
        return list(devices)

    monkeypatch.setattr("lightfall_vibe.audio.capture.list_devices", list_devices)
    pages = [VibeSettingsPlugin()]
    prefs = ScopedPrefs()
    plugins = SimpleNamespace(
        get_ready_by_type=lambda _t: [SimpleNamespace(instance=p) for p in pages],
        get_all=lambda: [],
    )
    services = SimpleNamespace(get=lambda _cls: plugins)
    monkeypatch.setattr(
        "lightfall.core.services.ServiceRegistry.get_instance", classmethod(lambda cls: services)
    )
    monkeypatch.setattr(
        "lightfall.ui.preferences.manager.PreferencesManager.get_instance", classmethod(lambda cls: prefs)
    )
    boxes: list[str] = []
    for name in ("warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, lambda _p, _t, text, *a, **k: boxes.append(text))
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
    yield SimpleNamespace(
        prefs=prefs, page=pages[0], boxes=boxes, conductor=conductor, devices=devices, listed=listed
    )


def _dialog(qtbot, scope=USER):
    from lightfall.ui.preferences.dialog import PreferencesDialog

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.prompts = []
    dialog._prompt_restart = lambda: dialog.prompts.append(list(dialog._restart_reasons))
    if scope is not None:
        dialog.select_scope(scope)
    return dialog


def _form(dialog):
    from lightfall.ui.preferences.form.view import SettingsForm

    return next(f for f in dialog.findChildren(SettingsForm) if f._plugin.name == "vibe")


def _row_of(dialog, key):
    from lightfall.ui.preferences.form.row import SettingRow

    return next(r for r in _form(dialog).findChildren(SettingRow) if r.key == key)


def _pick(dialog, key, text):
    box = _row_of(dialog, key).editor.findChild(QComboBox)
    index = box.findText(text)
    assert index >= 0, (key, text, [box.itemText(i) for i in range(box.count())])
    box.setCurrentIndex(index)


def _type(dialog, key, text):
    edit = _row_of(dialog, key).editor.findChild(QLineEdit)
    edit.setText(text)
    edit.textEdited.emit(text)


def _beat_receivers(cond) -> int:
    return cond.receivers(SIGNAL("beat()"))


# ---------------------------------------------------------------------------
# Page structure
# ---------------------------------------------------------------------------


def test_specs_and_device_console_only(qapp):
    from lightfall.ui.preferences.form.schema import Embed, section_fields

    page = VibeSettingsPlugin()
    assert (page.name, page.display_name, page.category) == ("vibe", "Vibe", "plugins")
    assert page.is_form_page()
    assert tuple(page.console_keys()) == (DEVICE,)
    specs = {s.key: s for s in page.specs()}
    assert set(specs) == set(USER_KEYS)
    assert specs[ENABLED].type is bool
    assert specs[SENS].type is float
    assert specs[BEATS].type is int and specs[PX].type is int
    assert all(specs[k].type is bool for k in EFFECTS)
    assert all(s.scopes == frozenset({"user"}) for s in specs.values())

    prefs = ScopedPrefs()
    assert prefs.allowed_at(DEVICE, LOCAL)
    for scope in (USER, BRANCH, BEAMLINE, "facility"):
        assert not prefs.allowed_at(DEVICE, scope), scope
    for key in USER_KEYS:
        assert prefs.allowed_at(key, USER), key
        for scope in (LOCAL, BRANCH, BEAMLINE, "facility"):
            assert not prefs.allowed_at(key, scope), (key, scope)

    vibe, audio, pulse, effects = page.sections()
    assert [s.title for s in (vibe, audio, pulse, effects)] == ["Vibe", "Audio source", "Pulse", "Effects"]
    enabled, sens = section_fields(vibe)
    assert (enabled.key, enabled.label, enabled.editor.kind) == (ENABLED, "Enable Vibe mode", "toggle")
    assert (sens.key, sens.label, sens.placeholder) == (SENS, "Beat sensitivity", "1.5")
    assert (sens.editor.kind, sens.editor.minimum, sens.editor.maximum, sens.editor.step) == (
        "number", 0.5, 3.0, 0.1)
    assert [type(i) for i in vibe.items].count(Embed) == 1
    [device] = section_fields(audio)
    assert (device.key, device.editor.kind) == (DEVICE, "choice")
    assert callable(device.editor.options)
    beats, px = section_fields(pulse)
    assert (beats.key, beats.editor.kind, beats.editor.minimum, beats.editor.maximum) == (BEATS, "integer", 1, 16)
    assert (beats.unit, beats.placeholder) == ("beats", "8")
    assert (px.key, px.editor.kind, px.editor.minimum, px.editor.maximum) == (PX, "integer", 1, 12)
    assert (px.unit, px.placeholder) == ("px", "4")
    assert [(f.key, f.label, f.description, f.editor.kind) for f in section_fields(effects)] == [
        ("vibe.effect.spinner", "Spin the RunEngine spinner", "Default: on", "toggle"),
        ("vibe.effect.theme", "Shift theme colors on beats", "Default: on", "toggle"),
        ("vibe.effect.pulse", "Pulse the layout on downbeats", "Default: off", "toggle"),
    ]


def test_old_page_methods_removed():
    for name in ("create_widget", "load_settings", "save_settings"):
        assert name not in vars(VibeSettingsPlugin), name


def test_page_shows_device_at_this_console_and_the_rest_at_user(qtbot, env):
    dialog = _dialog(qtbot)
    form = _form(dialog)
    assert set(form._rows) == set(USER_KEYS)
    dialog.select_scope(LOCAL)
    assert set(form._rows) == {DEVICE}


def test_device_choices_relisted_on_every_show(qtbot, env):
    dialog = _dialog(qtbot, scope=LOCAL)
    box = _row_of(dialog, DEVICE).editor.findChild(QComboBox)
    assert [box.itemText(i) for i in range(box.count())] == ["Not set", "Speakers (system audio)", "Mic"]
    env.devices.append(("dev3", "USB interface"))
    dialog.select_scope(USER)
    dialog.select_scope(LOCAL)
    box = _row_of(dialog, DEVICE).editor.findChild(QComboBox)
    assert box.findText("USB interface") >= 0
    assert not [b for b in _form(dialog).findChildren(QPushButton) if b.text() == "Refresh"]


# ---------------------------------------------------------------------------
# Live preview, Cancel and Save
# ---------------------------------------------------------------------------


def test_preview_drives_conductor(qtbot, env):
    cond = env.conductor
    dialog = _dialog(qtbot)
    assert cond.events == []  # opening the page touches nothing

    _type(dialog, SENS, "2.5")
    assert cond.sensitivity == pytest.approx(2.5)
    _type(dialog, BEATS, "3")
    assert cond.beats_per_pulse == 3
    _type(dialog, PX, "9")
    assert cond.pulse_px == 9
    _pick(dialog, "vibe.effect.pulse", "On")
    assert cond.effect_enabled("pulse")
    _pick(dialog, "vibe.effect.theme", "Off")
    assert not cond.effect_enabled("theme")
    assert cond.events == []  # nothing so far restarts or starts capture

    _pick(dialog, ENABLED, "On")
    assert cond.is_running and cond.events == ["start"]
    _type(dialog, SENS, "2.0")  # a knob edit while running does not restart capture
    assert cond.sensitivity == pytest.approx(2.0)
    assert cond.events == ["start"]

    dialog.select_scope(LOCAL)
    _pick(dialog, DEVICE, "Mic")
    assert cond.device_id == "dev2"
    assert cond.events == ["start", "stop", "start"]  # restarted onto the new device
    assert cond.sensitivity == pytest.approx(2.0)  # edits at User are still previewed

    dialog.select_scope(USER)
    _type(dialog, PX, "5")  # the device edit at This console is still previewed
    assert cond.device_id == "dev2" and cond.pulse_px == 5
    assert cond.events == ["start", "stop", "start"]

    _pick(dialog, ENABLED, "Off")
    assert not cond.is_running
    assert env.prefs.calls == []  # preview writes nothing


@pytest.mark.parametrize("running", [True, False])
def test_cancel_restores_conductor_and_running_state(qtbot, env, running):
    cond = env.conductor
    cond.device_id = "dev1"
    cond.set_sensitivity(1.2)
    cond.set_effect_enabled("pulse", True)
    if running:
        cond.start()
    before = _state(cond)
    cond.events.clear()

    env.page.revert_preview()  # without a preview: a no-op
    assert _state(cond) == before and cond.events == []

    dialog = _dialog(qtbot)
    _type(dialog, SENS, "2.8")
    _type(dialog, BEATS, "2")
    _type(dialog, PX, "11")
    _pick(dialog, "vibe.effect.pulse", "Off")
    _pick(dialog, "vibe.effect.spinner", "Off")
    _pick(dialog, ENABLED, "Off" if running else "On")
    dialog.select_scope(LOCAL)
    _pick(dialog, DEVICE, "Mic")
    assert _state(cond) != before

    dialog.reject()
    assert _state(cond) == before
    assert env.prefs.calls == []
    events = list(cond.events)
    env.page.revert_preview()  # a second revert does nothing more
    assert _state(cond) == before and cond.events == events


def test_reverting_every_edit_puts_conductor_back(qtbot, env):
    cond = env.conductor
    cond.start()
    before = _state(cond)
    cond.events.clear()
    dialog = _dialog(qtbot)
    _type(dialog, SENS, "2.8")
    _pick(dialog, ENABLED, "Off")
    assert not cond.is_running
    _type(dialog, SENS, "")  # back to Not set
    _pick(dialog, ENABLED, "Not set")
    assert _state(cond) == before
    assert dialog._apply() is True
    assert env.prefs.calls == []


def test_save_applies_and_clears_preview_state(qtbot, env):
    cond = env.conductor
    dialog = _dialog(qtbot)
    _type(dialog, SENS, "2.5")
    _pick(dialog, ENABLED, "On")
    _pick(dialog, "vibe.effect.pulse", "On")
    dialog.select_scope(LOCAL)
    _pick(dialog, DEVICE, "Mic")
    assert dialog._apply() is True
    assert sorted(env.prefs.calls) == sorted([
        (SENS, 2.5, USER),
        (ENABLED, True, USER),
        ("vibe.effect.pulse", True, USER),
        (DEVICE, "dev2", LOCAL),
    ])
    saved = _state(cond)
    assert saved == (True, "dev2", 2.5, 8, 4, (True, True, True))
    assert dialog.prompts == [] and env.boxes == []

    events = list(cond.events)
    env.page.revert_preview()  # after a save, with no pending edits: a no-op
    dialog.reject()
    assert _state(cond) == saved and cond.events == events

    # A later Cancel goes back to the saved state, not to the state before the first dialog.
    dialog2 = _dialog(qtbot)
    _type(dialog2, SENS, "0.7")
    _pick(dialog2, ENABLED, "Off")
    dialog2.reject()
    assert _state(cond) == saved


def test_after_save_pushes_saved_values_like_on_loaded(qtbot, env):
    cond = env.conductor
    env.prefs.layers[(USER, BEATS)] = 5
    env.prefs.layers[(USER, ENABLED)] = True
    env.page.after_save(USER, {BEATS: 5, ENABLED: True})
    assert cond.beats_per_pulse == 5
    assert cond.is_running
    env.prefs.layers[(USER, ENABLED)] = False
    env.page.after_save(USER, {ENABLED: False})
    assert not cond.is_running


def test_untouched_page_writes_nothing(qtbot, env):
    cond = env.conductor
    env.prefs.layers[(USER, ENABLED)] = True
    env.prefs.layers[(USER, SENS)] = 2.0
    env.prefs.layers[(LOCAL, DEVICE)] = "dev2"
    cond.device_id = "dev2"
    cond.start()
    before = _state(cond)
    cond.events.clear()

    dialog = _dialog(qtbot, scope=None)
    assert dialog._apply() is True
    dialog.select_scope(LOCAL)
    assert dialog._apply() is True
    dialog.select_scope(USER)  # reopening the page mid-vibe
    assert dialog._apply() is True
    dialog.reject()
    assert env.prefs.calls == []
    assert dialog.prompts == [] and env.boxes == []
    assert _state(cond) == before
    assert cond.events == []  # capture never restarted


# ---------------------------------------------------------------------------
# Beat LED
# ---------------------------------------------------------------------------


def test_beat_led_flashes_and_disconnects_on_destroy(qtbot, conductor):
    from lightfall_vibe import beat_led

    base = _beat_receivers(conductor)
    led = beat_led.beat_led_factory(None)  # destroyed below; not registered with qtbot
    assert "Beat detector (play music to test)" in [
        w.text() for w in led.findChildren(beat_led.QLabel)]
    assert _beat_receivers(conductor) == base + 1
    assert not led.is_lit()
    conductor.beat.emit()
    assert led.is_lit()
    assert beat_led.LED_FLASH_MS == 120
    qtbot.waitUntil(lambda: not led.is_lit(), timeout=1000)

    gone = []
    led.destroyed.connect(lambda *_: gone.append(1))
    led.deleteLater()
    qtbot.waitUntil(lambda: bool(gone), timeout=1000)
    assert _beat_receivers(conductor) == base
    conductor.beat.emit()  # must not raise against the deleted LED


def test_reshown_page_does_not_accumulate_led_connections(qtbot, env):
    base = _beat_receivers(env.conductor)
    dialog = _dialog(qtbot)
    assert _beat_receivers(env.conductor) == base + 1
    for scope in (LOCAL, USER, LOCAL, USER):
        dialog.select_scope(scope)
    qtbot.waitUntil(lambda: _beat_receivers(env.conductor) == base + 1, timeout=1000)
    env.conductor.beat.emit()


# ---------------------------------------------------------------------------
# Startup (on_loaded), unchanged from the old page
# ---------------------------------------------------------------------------


class FakePrefs:
    """Dict-backed PreferencesManager stand-in (one shared store per use)."""

    def __init__(self, stored):
        self._stored = stored

    def get(self, key, default=None):
        return self._stored.get(key, default)

    def set(self, key, value):
        self._stored[key] = value


def _install_prefs(monkeypatch, stored):
    import lightfall_vibe.settings as settings_mod

    monkeypatch.setattr(
        settings_mod.PreferencesManager,
        "get_instance",
        staticmethod(lambda: FakePrefs(stored)),
    )


def test_on_loaded_restores_prefs_and_starts_when_enabled(
    qtbot, conductor, monkeypatch
):
    stored = {
        "vibe.enabled": True,
        "vibe.sensitivity": 2.5,
        "vibe.pulse_beats": 4,
        "vibe.pulse_px": 9,
        "vibe.effect.pulse": True,
        "vibe.device_id": "dev42",
    }
    _install_prefs(monkeypatch, stored)

    plugin = VibeSettingsPlugin()
    plugin.on_loaded()
    assert conductor.sensitivity == pytest.approx(2.5)
    assert conductor.beats_per_pulse == 4
    assert conductor.pulse_px == 9
    assert conductor.effect_enabled("pulse")
    assert conductor.device_id == "dev42"
    # Start is deferred one event-loop turn (main window exists by then).
    assert not conductor.is_running
    qtbot.waitUntil(lambda: conductor.is_running, timeout=1000)


def test_on_loaded_does_not_start_when_disabled(qtbot, conductor, monkeypatch):
    _install_prefs(monkeypatch, {})

    plugin = VibeSettingsPlugin()
    plugin.on_loaded()
    qtbot.wait(50)  # give a wrongly-scheduled start a chance to fire
    assert not conductor.is_running
