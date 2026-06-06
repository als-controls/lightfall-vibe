"""Vibe mode settings page.

The Enable toggle is deliberately session-only: vibe mode never starts
capturing audio at app launch. Everything else (device, sensitivity,
effect toggles) persists via PreferencesManager.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lightfall.plugins.settings_plugin import SettingsPlugin
from lightfall.ui.preferences.manager import PreferencesManager

from lightfall_vibe.audio.capture import list_devices
from lightfall_vibe.conductor import EFFECT_NAMES, get_conductor
from lightfall_vibe.effects.pulse import DEFAULT_BEATS_PER_PULSE

PREF_DEVICE = "vibe.device_id"
PREF_SENSITIVITY = "vibe.sensitivity"
PREF_PULSE_BEATS = "vibe.pulse_beats"
PREF_EFFECT = "vibe.effect.{}"  # .format(effect_name)

_EFFECT_LABELS = {
    "spinner": "Spin the RunEngine spinner",
    "theme": "Shift theme colors on beats",
    "pulse": "Pulse the layout on downbeats",
}
_LED_FLASH_MS = 120


class VibeSettingsPlugin(SettingsPlugin):
    """Preferences page controlling Vibe mode."""

    def __init__(self) -> None:
        self._enable_check: QCheckBox | None = None
        self._device_combo: QComboBox | None = None
        self._sensitivity_slider: QSlider | None = None
        self._pulse_beats_spin: QSpinBox | None = None
        self._effect_checks: dict[str, QCheckBox] = {}
        self._beat_led: QLabel | None = None
        self._led_timer: QTimer | None = None

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

    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        conductor = get_conductor()
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        self._enable_check = QCheckBox("Enable Vibe mode", widget)
        self._enable_check.setChecked(conductor.is_running)
        self._enable_check.toggled.connect(self._on_enable_toggled)
        layout.addWidget(self._enable_check)

        form = QFormLayout()

        device_row = QHBoxLayout()
        self._device_combo = QComboBox(widget)
        self._device_combo.currentIndexChanged.connect(self._on_device_changed)
        refresh = QPushButton("Refresh", widget)
        refresh.clicked.connect(self._refresh_devices)
        device_row.addWidget(self._device_combo, stretch=1)
        device_row.addWidget(refresh)
        form.addRow("Audio source:", device_row)

        self._sensitivity_slider = QSlider(Qt.Orientation.Horizontal, widget)
        self._sensitivity_slider.setRange(5, 30)  # 0.5x .. 3.0x
        self._sensitivity_slider.setValue(10)
        self._sensitivity_slider.valueChanged.connect(self._on_sensitivity_changed)
        form.addRow("Beat sensitivity:", self._sensitivity_slider)

        self._pulse_beats_spin = QSpinBox(widget)
        self._pulse_beats_spin.setRange(1, 16)
        self._pulse_beats_spin.setValue(conductor.beats_per_pulse)
        self._pulse_beats_spin.setSuffix(" beats")
        self._pulse_beats_spin.valueChanged.connect(self._on_pulse_beats_changed)
        form.addRow("Pulse every:", self._pulse_beats_spin)

        led_row = QHBoxLayout()
        self._beat_led = QLabel(widget)
        self._beat_led.setFixedSize(16, 16)
        self._set_led(False)
        led_row.addWidget(self._beat_led)
        led_row.addWidget(QLabel("Beat detector (play music to test)", widget))
        led_row.addStretch(1)
        form.addRow("", led_row)
        layout.addLayout(form)

        effects_box = QGroupBox("Effects", widget)
        effects_layout = QVBoxLayout(effects_box)
        for effect_name in EFFECT_NAMES:
            check = QCheckBox(_EFFECT_LABELS[effect_name], effects_box)
            check.setChecked(conductor.effect_enabled(effect_name))
            check.toggled.connect(
                lambda on, n=effect_name: get_conductor().set_effect_enabled(n, on)
            )
            self._effect_checks[effect_name] = check
            effects_layout.addWidget(check)
        layout.addWidget(effects_box)
        layout.addStretch(1)

        self._led_timer = QTimer(widget)
        self._led_timer.setSingleShot(True)
        self._led_timer.setInterval(_LED_FLASH_MS)
        self._led_timer.timeout.connect(lambda: self._set_led(False))
        conductor.beat.connect(self._on_beat)
        conductor.started.connect(self._on_conductor_started)
        conductor.stopped.connect(self._on_conductor_stopped)
        widget.destroyed.connect(self._on_widget_destroyed)

        self._refresh_devices()
        return widget

    # --- live handlers -------------------------------------------------

    def _on_enable_toggled(self, checked: bool) -> None:
        conductor = get_conductor()
        if checked:
            conductor.start()
        else:
            conductor.stop()

    def _on_device_changed(self, index: int) -> None:
        if self._device_combo is None or index < 0:
            return
        conductor = get_conductor()
        new_id = self._device_combo.itemData(index)
        if new_id == conductor.device_id:
            return  # no actual change: don't restart capture
        conductor.device_id = new_id
        if conductor.is_running:  # restart capture on the new device
            conductor.stop()
            conductor.start()

    def _on_sensitivity_changed(self, value: int) -> None:
        get_conductor().set_sensitivity(value / 10.0)

    def _on_pulse_beats_changed(self, value: int) -> None:
        get_conductor().set_beats_per_pulse(value)

    def _on_conductor_started(self) -> None:
        self._sync_enable_check(True)

    def _on_conductor_stopped(self) -> None:
        self._sync_enable_check(False)

    def _sync_enable_check(self, running: bool) -> None:
        """Reflect conductor state without re-triggering start/stop."""
        if self._enable_check is None:
            return
        self._enable_check.blockSignals(True)
        self._enable_check.setChecked(running)
        self._enable_check.blockSignals(False)

    def _on_widget_destroyed(self) -> None:
        """The Preferences dialog destroys its widgets on close.

        The plugin (a non-QObject singleton) outlives them, so conductor
        connections must be dropped by hand and all widget refs nulled --
        otherwise the next beat pokes a deleted QLabel.
        """
        conductor = get_conductor()
        for signal, slot in (
            (conductor.beat, self._on_beat),
            (conductor.started, self._on_conductor_started),
            (conductor.stopped, self._on_conductor_stopped),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass  # already disconnected
        self._enable_check = None
        self._device_combo = None
        self._sensitivity_slider = None
        self._pulse_beats_spin = None
        self._effect_checks = {}
        self._beat_led = None
        self._led_timer = None

    def _on_beat(self) -> None:
        self._set_led(True)
        if self._led_timer is not None:
            self._led_timer.start()

    def _set_led(self, on: bool) -> None:
        if self._beat_led is None:
            return
        color = "#22c55e" if on else "#3e3e3e"
        self._beat_led.setStyleSheet(
            f"background-color: {color}; border-radius: 8px;"
        )

    def _refresh_devices(self) -> None:
        if self._device_combo is None:
            return
        current = self._device_combo.currentData()
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        devices = list_devices()
        for device_id, label in devices:
            self._device_combo.addItem(label, device_id)
        if not devices:
            self._device_combo.addItem("(no audio devices found)", None)
        if current is not None:
            index = self._device_combo.findData(current)
            if index >= 0:
                self._device_combo.setCurrentIndex(index)
        self._device_combo.blockSignals(False)
        # Build-time call pins conductor.device_id to the first enumerated
        # device (loopback sorts first, so usually the right one anyway);
        # load_settings() re-selects any persisted choice right after.
        self._on_device_changed(self._device_combo.currentIndex())

    # --- SettingsPlugin persistence ------------------------------------

    def load_settings(self) -> None:
        prefs = PreferencesManager.get_instance()
        conductor = get_conductor()
        if self._sensitivity_slider is not None:
            stored = prefs.get(PREF_SENSITIVITY, 1.0)
            self._sensitivity_slider.setValue(round(float(stored) * 10))
        if self._pulse_beats_spin is not None:
            stored_beats = prefs.get(PREF_PULSE_BEATS, DEFAULT_BEATS_PER_PULSE)
            self._pulse_beats_spin.setValue(int(stored_beats))
        for effect_name, check in self._effect_checks.items():
            default = conductor.effect_enabled(effect_name)
            check.setChecked(bool(prefs.get(PREF_EFFECT.format(effect_name), default)))
        if self._device_combo is not None:
            stored_device = prefs.get(PREF_DEVICE, None)
            if stored_device is not None:
                index = self._device_combo.findData(stored_device)
                if index >= 0:
                    self._device_combo.setCurrentIndex(index)

    def save_settings(self) -> None:
        prefs = PreferencesManager.get_instance()
        if self._sensitivity_slider is not None:
            prefs.set(PREF_SENSITIVITY, self._sensitivity_slider.value() / 10.0)
        if self._pulse_beats_spin is not None:
            prefs.set(PREF_PULSE_BEATS, self._pulse_beats_spin.value())
        for effect_name, check in self._effect_checks.items():
            prefs.set(PREF_EFFECT.format(effect_name), check.isChecked())
        if self._device_combo is not None:
            device_id = self._device_combo.currentData()
            if device_id is not None:
                prefs.set(PREF_DEVICE, device_id)
