"""Vibe spectrum panel: 24-band pyqtgraph bar analyzer."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
from lightfall.visualization import pg
from PySide6.QtGui import QColor

from lightfall.plugins.panel_plugin import PanelPlugin
from lightfall.ui.panels.base import BasePanel, PanelMetadata
from lightfall.ui.theme.manager import ThemeManager

from lightfall_vibe.audio.features import N_BANDS, VibeFrame
from lightfall_vibe.conductor import get_conductor


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
        category="Dev",
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
        get_conductor().frame_ready.connect(self._on_frame)

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
