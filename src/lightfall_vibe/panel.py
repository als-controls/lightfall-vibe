"""Vibe spectrum panel: 24-band pyqtgraph bar analyzer with beat flash."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
from lightfall.visualization import pg
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor

from lightfall.plugins.panel_plugin import PanelPlugin
from lightfall.ui.panels.base import BasePanel, PanelMetadata
from lightfall.ui.theme.manager import ThemeManager

from lightfall_vibe.audio.features import N_BANDS, VibeFrame
from lightfall_vibe.conductor import get_conductor

_FLASH_MS = 90


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
        category="Dev",
        keywords=["vibe", "music", "spectrum", "audio"],
        default_area="right",
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

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(_FLASH_MS)
        self._flash_timer.timeout.connect(self._end_flash)

        self._brush_key = None
        self._apply_theme_colors()
        theme.colors_changed.connect(self._apply_theme_colors)
        get_conductor().frame_ready.connect(self._on_frame)

    def _apply_theme_colors(self) -> None:
        colors = ThemeManager.get_instance().colors
        key = (colors.primary, colors.secondary, colors.background, colors.surface)
        if key == self._brush_key:
            return
        self._brush_key = key
        self._brushes = _gradient_brushes(colors.primary, colors.secondary, N_BANDS)
        self._bg_normal = QColor(colors.background)
        self._bg_flash = QColor(colors.surface)
        self._bars.setOpts(brushes=self._brushes, pen=None)
        if not self._flash_timer.isActive():
            self._plot.setBackground(self._bg_normal)

    def _on_frame(self, frame: VibeFrame) -> None:
        self._bars.setOpts(height=frame.bands)
        if frame.beat:
            self._plot.setBackground(self._bg_flash)
            self._flash_timer.start()

    def _end_flash(self) -> None:
        self._plot.setBackground(self._bg_normal)


class VibePanelPlugin(PanelPlugin):
    """Panel plugin exposing the Vibe spectrum analyzer."""

    @property
    def name(self) -> str:
        return "vibe_spectrum"

    def get_panel_class(self) -> type[BasePanel]:
        return VibePanel
