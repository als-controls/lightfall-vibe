"""Vibe spectrum panel: 24-band pyqtgraph bar analyzer.

The title bar carries an on/off toggle for Vibe mode itself. It mirrors the
conductor (checked while it runs, so a start from Preferences or a stop on
capture failure shows up here) and a click saves ``vibe.enabled`` at User
scope, the same setting as Preferences > Vibe > "Enable Vibe mode".
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
from loguru import logger
from lightfall.visualization import pg
from PySide6.QtGui import QColor

from lightfall.plugins.panel_plugin import PanelPlugin
from lightfall.ui.panels.base import BasePanel, PanelMetadata
from lightfall.ui.theme.manager import ThemeManager

from lightfall_vibe.audio.features import N_BANDS, VibeFrame
from lightfall_vibe.conductor import get_conductor

_ICON_ON = "mdi6.music"
_ICON_OFF = "mdi6.music-off"


def _persist_enabled(on: bool) -> None:
    """Save the toggle as ``vibe.enabled`` so the choice survives a restart."""
    from lightfall.ui.preferences.manager import PreferencesManager

    from lightfall_vibe.settings import PREF_ENABLED

    PreferencesManager.get_instance().set(PREF_ENABLED, bool(on))


def _gradient_brushes(start_hex: str, end_hex: str, n: int) -> list[QColor]:
    """Per-bar colors lerped from start to end."""
    start = QColor(start_hex)
    end = QColor(end_hex)
    out = []
    for i in range(n):
        t = i / max(n - 1, 1)
        out.append(
            QColor(
                round(start.red() + (end.red() - start.red()) * t),
                round(start.green() + (end.green() - start.green()) * t),
                round(start.blue() + (end.blue() - start.blue()) * t),
            )
        )
    return out


class VibePanel(BasePanel):
    """Live spectrum bars driven by the vibe conductor's frames."""

    panel_metadata: ClassVar[PanelMetadata] = PanelMetadata(
        id="lightfall_vibe.panels.spectrum",
        name="Vibe",
        description="Music spectrum analyzer driving Vibe mode",
        icon="music",  # bare name -> qtawesome fa5s.music in the sidebar
        category="Developer",
        keywords=["vibe", "music", "spectrum", "audio"],
        # The host's default layout only sweeps left/bottom/center areas;
        # a preloaded "right" panel registers but is never surfaced.
        default_area="bottom",
        sidebar_group="bottom",
        sidebar_order=8,  # after dev-plugins' record/viz/palette (5/6/7)
    )

    def _setup_ui(self) -> None:
        theme = ThemeManager.get_instance()

        self._plot = pg.PlotWidget()
        self._plot.hideAxis("left")
        self._plot.hideAxis("bottom")
        self._plot.setMouseEnabled(False, False)
        self._plot.setMenuEnabled(False)
        self._plot.hideButtons()
        self._plot.setYRange(0.0, 1.05, padding=0)
        self._plot.setXRange(-0.6, N_BANDS - 0.4, padding=0)
        self._plot.setMinimumHeight(160)

        self._bars = pg.BarGraphItem(
            x=list(range(N_BANDS)),
            height=np.zeros(N_BANDS),
            width=0.8,
        )
        self._plot.addItem(self._bars)
        self._layout.addWidget(self._plot)

        self._brush_key = None
        self._apply_theme_colors()
        theme.colors_changed.connect(self._apply_theme_colors)
        conductor = get_conductor()
        conductor.frame_ready.connect(self._on_frame)

        self._toggle_action = self.add_title_bar_button(
            _ICON_OFF,
            "Turn Vibe mode on",
            on_triggered=self._on_toggle,
            checkable=True,
        )
        conductor.started.connect(self._sync_toggle)
        conductor.stopped.connect(self._sync_toggle)
        theme.colors_changed.connect(self._sync_toggle)  # re-tint the icon
        self._sync_toggle()

    def _on_toggle(self, checked: bool) -> None:
        conductor = get_conductor()
        if checked:
            conductor.start()
        else:
            conductor.stop()
        try:
            _persist_enabled(conductor.is_running)
        except Exception:  # noqa: BLE001 - never let a prefs hiccup break the toggle
            logger.exception("Vibe: saving vibe.enabled failed")
        self._sync_toggle()

    def _sync_toggle(self, *_args) -> None:
        """Show the conductor's real state (it may have been changed elsewhere)."""
        action = self._toggle_action
        running = get_conductor().is_running
        action.setChecked(running)
        tip = "Turn Vibe mode off" if running else "Turn Vibe mode on"
        action.setToolTip(tip)
        action.setText(tip)
        try:
            import qtawesome as qta

            color = ThemeManager.get_instance().colors.text_secondary
            action.setIcon(qta.icon(_ICON_ON if running else _ICON_OFF, color=color))
        except Exception:  # noqa: BLE001 - keep the previous icon
            pass

    def _apply_theme_colors(self) -> None:
        colors = ThemeManager.get_instance().colors
        key = (colors.primary, colors.secondary, colors.background)
        if key == self._brush_key:
            return
        self._brush_key = key
        self._brushes = _gradient_brushes(colors.primary, colors.secondary, N_BANDS)
        self._bars.setOpts(brushes=self._brushes, pen=None)
        self._plot.setBackground(QColor(colors.background))

    def _on_frame(self, frame: VibeFrame) -> None:
        self._bars.setOpts(height=frame.bands)


class VibePanelPlugin(PanelPlugin):
    """Panel plugin exposing the Vibe spectrum analyzer."""

    @property
    def name(self) -> str:
        return "vibe_spectrum"

    def get_panel_class(self) -> type[BasePanel]:
        return VibePanel
