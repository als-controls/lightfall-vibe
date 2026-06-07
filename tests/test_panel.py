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


def test_panel_metadata_is_surfaceable_by_host():
    """Regression: lightfall's default layout only sweeps the registry for
    left/bottom/center areas (mainwindow._setup_default_panels); a preloaded
    panel with default_area="right" registers fine but never appears.
    An empty icon renders an invisible sidebar button (icon_sidebar).
    """
    meta = VibePanel.panel_metadata
    assert meta.default_area in {"left", "bottom", "center"}
    assert meta.icon


def test_panel_updates_bar_heights(qtbot):
    panel = VibePanel()
    qtbot.addWidget(panel)
    panel._on_frame(_frame(heights=0.7))
    _x, heights = panel._bars.getData()
    assert np.allclose(heights, 0.7)


def test_beat_frames_do_not_change_background(qtbot):
    """The beat background flash was removed (too much, per live feedback);
    beats must render exactly like non-beat frames."""
    panel = VibePanel()
    qtbot.addWidget(panel)
    before = panel._plot.backgroundBrush().color().name()
    panel._on_frame(_frame(beat=True))
    assert panel._plot.backgroundBrush().color().name() == before


def test_panel_survives_frames_without_conductor_running(qtbot):
    panel = VibePanel()
    qtbot.addWidget(panel)
    for _ in range(3):
        panel._on_frame(_frame())
    panel._on_frame(_frame(beat=True))
    # No assertion needed beyond "did not raise".
