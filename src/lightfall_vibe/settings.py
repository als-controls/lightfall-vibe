"""Vibe mode settings page (a scope-aware form page).

``vibe.device_id`` belongs to this console (shown and saved at This console);
every other ``vibe.*`` key is a per-user setting. on_loaded() (preload) pushes
saved prefs into the conductor at startup and, if vibe mode was enabled,
starts it once the event loop is running (the main window exists by then, so
effects find their targets).

While the page is edited, preview() drives the running conductor with the
pending values (so music reacts at once); revert_preview() (Cancel) puts the
conductor back as it was before the dialog, running or stopped, and
after_save() applies the saved values.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QTimer

from lightfall.plugins.settings_plugin import SettingsPlugin
from lightfall.ui.preferences.form.schema import (
    Choice,
    Embed,
    Integer,
    Number,
    Section,
    SettingField,
    Toggle,
)
from lightfall.ui.preferences.manager import PreferencesManager

from lightfall_vibe.audio import capture
from lightfall_vibe.beat_led import beat_led_factory
from lightfall_vibe.conductor import (
    DEFAULT_ENABLED,
    DEFAULT_SENSITIVITY,
    EFFECT_NAMES,
    VibeConductor,
    get_conductor,
)
from lightfall_vibe.effects.pulse import DEFAULT_BEATS_PER_PULSE, DEFAULT_PULSE_PX

if TYPE_CHECKING:
    from lightfall_settings import SettingSpec

    from lightfall.ui.preferences.form.schema import FormValues

PREF_ENABLED = "vibe.enabled"
PREF_DEVICE = "vibe.device_id"
PREF_SENSITIVITY = "vibe.sensitivity"
PREF_PULSE_BEATS = "vibe.pulse_beats"
PREF_PULSE_PX = "vibe.pulse_px"
PREF_EFFECT = "vibe.effect.{}"  # .format(effect_name)

_EFFECT_LABELS = {
    "spinner": "Spin the RunEngine spinner",
    "theme": "Shift theme colors on beats",
    "pulse": "Pulse the layout on downbeats",
}

_KEYS = (
    PREF_ENABLED,
    PREF_DEVICE,
    PREF_SENSITIVITY,
    PREF_PULSE_BEATS,
    PREF_PULSE_PX,
    *(PREF_EFFECT.format(n) for n in EFFECT_NAMES),
)

Read = Callable[[str, Any], Any]  # (key, default) -> value


def _device_options() -> list[tuple[str, str]]:
    """Capture devices, listed afresh each time the page is shown."""
    return list(capture.list_devices())


def _state_from(read: Read) -> dict[str, Any]:
    """The conductor state the values given by ``read`` ask for (startup defaults for unset keys)."""
    return {
        "running": bool(read(PREF_ENABLED, False)),
        "device_id": read(PREF_DEVICE, None),
        "sensitivity": float(read(PREF_SENSITIVITY, DEFAULT_SENSITIVITY)),
        "beats_per_pulse": int(read(PREF_PULSE_BEATS, DEFAULT_BEATS_PER_PULSE)),
        "pulse_px": int(read(PREF_PULSE_PX, DEFAULT_PULSE_PX)),
        "effects": {
            n: bool(read(PREF_EFFECT.format(n), DEFAULT_ENABLED.get(n, False)))
            for n in EFFECT_NAMES
        },
    }


def _snapshot(conductor: VibeConductor) -> dict[str, Any]:
    return {
        "running": conductor.is_running,
        "device_id": conductor.device_id,
        "sensitivity": conductor.sensitivity,
        "beats_per_pulse": conductor.beats_per_pulse,
        "pulse_px": conductor.pulse_px,
        "effects": {n: conductor.effect_enabled(n) for n in EFFECT_NAMES},
    }


def _drive(conductor: VibeConductor, state: Mapping[str, Any]) -> None:
    """Bring ``conductor`` to ``state``; capture restarts only for a new device."""
    if not state["running"]:
        conductor.stop()  # no-op when stopped; first, so a device change won't restart
    conductor.set_sensitivity(state["sensitivity"])
    conductor.set_beats_per_pulse(state["beats_per_pulse"])
    conductor.set_pulse_px(state["pulse_px"])
    for name, on in state["effects"].items():
        if conductor.effect_enabled(name) != on:
            conductor.set_effect_enabled(name, on)
    if state["device_id"] != conductor.device_id:
        conductor.device_id = state["device_id"]
        if conductor.is_running:  # restart capture on the new device
            conductor.stop()
            conductor.start()
    if state["running"]:
        conductor.start()  # no-op when already running


class VibeSettingsPlugin(SettingsPlugin):
    """Preferences page controlling Vibe mode."""

    def __init__(self) -> None:
        super().__init__()
        # Conductor state from before the dialog's first preview; None = no preview.
        self._before: dict[str, Any] | None = None
        # key -> (scope, value) of the last unsaved edit seen, so an edit at one
        # scope (device at This console) stays previewed while another is shown.
        self._edits: dict[str, tuple[str, Any]] = {}

    @property
    def name(self) -> str:
        return "vibe"

    @property
    def display_name(self) -> str:
        return "Vibe"

    @property
    def category(self) -> str:
        return "plugins"

    @property
    def description(self) -> str:
        return "Music-reactive UI effects (demo)"

    # --- schema ----------------------------------------------------------

    def console_keys(self) -> Sequence[str]:
        """The audio device is this console's; everything else is per user."""
        return (PREF_DEVICE,)

    def specs(self) -> Sequence[SettingSpec]:
        from lightfall_settings import SettingSpec

        user = {"user"}
        return (
            SettingSpec(key=PREF_ENABLED, type=bool, scopes=user, label="Enable Vibe mode"),
            SettingSpec(key=PREF_SENSITIVITY, type=float, scopes=user, label="Beat sensitivity"),
            SettingSpec(key=PREF_PULSE_BEATS, type=int, scopes=user, label="Pulse every"),
            SettingSpec(key=PREF_PULSE_PX, type=int, scopes=user, label="Pulse magnitude"),
            *(
                SettingSpec(
                    key=PREF_EFFECT.format(n), type=bool, scopes=user, label=_EFFECT_LABELS[n]
                )
                for n in EFFECT_NAMES
            ),
        )

    def sections(self) -> Sequence[Section]:
        return (
            Section("Vibe", (
                SettingField(PREF_ENABLED, Toggle(), label="Enable Vibe mode"),
                SettingField(
                    PREF_SENSITIVITY,
                    Number(0.5, 3.0, 0.1),
                    label="Beat sensitivity",
                    placeholder=str(DEFAULT_SENSITIVITY),
                ),
                Embed(beat_led_factory),
            )),
            Section("Audio source", (
                SettingField(PREF_DEVICE, Choice(_device_options), label="Audio source"),
            )),
            Section("Pulse", (
                SettingField(
                    PREF_PULSE_BEATS,
                    Integer(1, 16),
                    label="Pulse every",
                    unit="beats",
                    placeholder=str(DEFAULT_BEATS_PER_PULSE),
                ),
                SettingField(
                    PREF_PULSE_PX,
                    Integer(1, 12),
                    label="Pulse magnitude",
                    unit="px",
                    placeholder=str(DEFAULT_PULSE_PX),
                ),
            )),
            Section("Effects", tuple(
                SettingField(
                    PREF_EFFECT.format(n),
                    Toggle(),
                    label=_EFFECT_LABELS[n],
                    description="Default: on" if DEFAULT_ENABLED.get(n, False) else "Default: off",
                )
                for n in EFFECT_NAMES
            )),
        )

    # --- live preview ------------------------------------------------------

    def preview(self, values: FormValues) -> None:
        """Drive the conductor with the pending values (every Vibe key, any scope)."""
        conductor = get_conductor()
        if self._before is None:
            self._before = _snapshot(conductor)
        scope = values.scope
        for key in _KEYS:
            if values.is_dirty(key):
                self._edits[key] = (scope, values.effective(key))
            elif key in self._edits and self._edits[key][0] == scope:
                del self._edits[key]  # edited back to the stored value
        if not self._edits:
            self.revert_preview()  # nothing pending: as before the dialog
            return

        def read(key: str, default: Any) -> Any:
            value = self._edits[key][1] if key in self._edits else values.effective(key)
            return default if value is None else value

        _drive(conductor, _state_from(read))

    def revert_preview(self) -> None:
        """Put the conductor back as it was before the first preview (no-op without one)."""
        before = self._before
        self._before = None
        self._edits.clear()
        if before is not None:
            _drive(get_conductor(), before)

    def after_save(self, scope: str, changed: Mapping[str, Any]) -> None:
        """Apply the saved values (as on_loaded does) and forget the preview state."""
        self._before = None
        self._edits.clear()
        prefs = PreferencesManager.get_instance()
        _drive(get_conductor(), _state_from(prefs.get))

    # --- startup -------------------------------------------------------------

    def on_loaded(self) -> None:
        """Restore persisted vibe settings at startup (preload hook).

        Runs before the main window exists, so everything here only
        configures the conductor; the actual start is deferred one event-
        loop turn, by which point the window (and effect targets) exist.
        """
        prefs = PreferencesManager.get_instance()
        conductor = get_conductor()
        conductor.set_sensitivity(
            float(prefs.get(PREF_SENSITIVITY, DEFAULT_SENSITIVITY))
        )
        conductor.set_beats_per_pulse(
            int(prefs.get(PREF_PULSE_BEATS, DEFAULT_BEATS_PER_PULSE))
        )
        conductor.set_pulse_px(int(prefs.get(PREF_PULSE_PX, DEFAULT_PULSE_PX)))
        for effect_name in EFFECT_NAMES:
            stored = prefs.get(PREF_EFFECT.format(effect_name), None)
            if stored is not None:
                conductor.set_effect_enabled(effect_name, bool(stored))
        stored_device = prefs.get(PREF_DEVICE, None)
        if stored_device is not None:
            conductor.device_id = stored_device
        if bool(prefs.get(PREF_ENABLED, False)):
            QTimer.singleShot(0, conductor.start)
