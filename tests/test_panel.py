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


# --- title-bar on/off toggle ---------------------------------------------------

import pytest  # noqa: E402
from PySide6.QtCore import QObject, Signal  # noqa: E402

import lightfall_vibe.conductor as conductor_mod  # noqa: E402
import lightfall_vibe.panel as panel_mod  # noqa: E402
from lightfall_vibe.conductor import VibeConductor  # noqa: E402


class _FakeCapture(QObject):
    frame_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, *_args):
        super().__init__()

    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture
def conductor(monkeypatch):
    c = VibeConductor(capture_factory=_FakeCapture, effect_factories={})
    monkeypatch.setattr(conductor_mod, "_conductor", c)
    return c


@pytest.fixture
def saved(monkeypatch):
    out = []
    monkeypatch.setattr(panel_mod, "_persist_enabled", out.append)
    return out


def test_title_bar_has_checkable_vibe_toggle(qtbot, conductor):
    panel = VibePanel()
    qtbot.addWidget(panel)
    action = panel._toggle_action
    assert action in panel._title_bar_actions
    assert action.isCheckable()
    assert not action.isChecked()
    assert "on" in action.toolTip()


def test_toggle_starts_and_stops_vibe_and_persists(qtbot, conductor, saved):
    panel = VibePanel()
    qtbot.addWidget(panel)
    panel._toggle_action.trigger()
    assert conductor.is_running
    assert panel._toggle_action.isChecked()
    assert "off" in panel._toggle_action.toolTip()
    panel._toggle_action.trigger()
    assert not conductor.is_running
    assert not panel._toggle_action.isChecked()
    assert saved == [True, False]


def test_toggle_follows_starts_and_stops_made_elsewhere(qtbot, conductor, saved):
    """Preferences or a capture failure change the conductor; the button follows."""
    panel = VibePanel()
    qtbot.addWidget(panel)
    conductor.start()
    assert panel._toggle_action.isChecked()
    conductor._capture.failed.emit("device unplugged")
    assert not conductor.is_running
    assert not panel._toggle_action.isChecked()
    assert saved == []  # only clicks write the setting


def test_toggle_shows_running_state_when_panel_opens(qtbot, conductor):
    conductor.start()
    panel = VibePanel()
    qtbot.addWidget(panel)
    assert panel._toggle_action.isChecked()
