"""VibePanel renders band magnitudes as a pyqtgraph bar chart."""

import numpy as np

from lightfall_vibe.audio.features import N_BANDS, VibeFrame
from lightfall_vibe.panel import VibePanel, VibePanelPlugin


def _frame(heights: float = 0.5, beat: bool = False) -> VibeFrame:
    return VibeFrame(
        bands=np.full(N_BANDS, heights),
        rms=0.1,
        centroid=0.5,
        flux=0.0,
        beat=beat,
    )


def test_plugin_provides_panel_class():
    plugin = VibePanelPlugin()
    assert plugin.name == "vibe_spectrum"
    assert plugin.get_panel_class() is VibePanel


def test_panel_updates_bar_heights(qtbot):
    panel = VibePanel()
    qtbot.addWidget(panel)
    panel._on_frame(_frame(heights=0.7))
    heights = panel._bars.opts["height"]
    assert np.allclose(heights, 0.7)


def test_beat_flash_sets_and_clears(qtbot):
    panel = VibePanel()
    qtbot.addWidget(panel)
    panel._on_frame(_frame(beat=True))
    assert panel._flash_timer.isActive()
    qtbot.waitUntil(lambda: not panel._flash_timer.isActive(), timeout=1000)


def test_panel_survives_frames_without_conductor_running(qtbot):
    panel = VibePanel()
    qtbot.addWidget(panel)
    for _ in range(3):
        panel._on_frame(_frame())
    # No assertion needed beyond "did not raise".
