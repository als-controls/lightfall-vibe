"""ThemeEffect hue-walks accent colors on beats and restores on detach."""

import numpy as np
import pytest

from lightfall.ui.theme.manager import ThemeManager
from lightfall_vibe.audio.features import N_BANDS, VibeFrame
from lightfall_vibe.effects.theme import ThemeEffect


@pytest.fixture()
def manager(qtbot):
    ThemeManager.reset()
    mgr = ThemeManager.get_instance()
    yield mgr
    ThemeManager.reset()


def _beat() -> VibeFrame:
    return VibeFrame(
        bands=np.zeros(N_BANDS), rms=0.2, centroid=0.5, flux=0.5, beat=True
    )


def _no_beat() -> VibeFrame:
    return VibeFrame(
        bands=np.zeros(N_BANDS), rms=0.2, centroid=0.5, flux=0.0, beat=False
    )


def test_beat_changes_primary_and_emits(manager, qtbot):
    effect = ThemeEffect(manager=manager)
    assert effect.attach() is True
    original = manager.colors.primary
    with qtbot.waitSignal(manager.colors_changed, timeout=1000):
        effect.on_frame(_beat())
    assert manager.colors.primary != original
    effect.detach()


def test_no_beat_changes_nothing(manager):
    effect = ThemeEffect(manager=manager)
    effect.attach()
    original = manager.colors.primary
    effect.on_frame(_no_beat())
    assert manager.colors.primary == original
    effect.detach()


def test_detach_restores_exact_snapshot(manager):
    effect = ThemeEffect(manager=manager)
    effect.attach()
    snapshot = dict(vars(manager.colors))
    effect.on_frame(_beat())
    effect._last_emit = 0.0  # bypass throttle for the second beat
    effect.on_frame(_beat())
    effect.detach()
    assert dict(vars(manager.colors)) == snapshot


def test_emit_throttled_to_10hz(manager):
    effect = ThemeEffect(manager=manager)
    effect.attach()
    effect.on_frame(_beat())
    after_first = manager.colors.primary
    effect.on_frame(_beat())  # immediate second beat: throttled, no change
    assert manager.colors.primary == after_first
    effect.detach()


def test_text_fields_are_never_touched(manager):
    effect = ThemeEffect(manager=manager)
    effect.attach()
    text = manager.colors.text
    text_secondary = manager.colors.text_secondary
    effect.on_frame(_beat())
    assert manager.colors.text == text
    assert manager.colors.text_secondary == text_secondary
    effect.detach()


def test_backgrounds_are_never_touched(manager):
    """Foreground-only policy: canvas fields stay put; only accents and
    border lines move with the music."""
    effect = ThemeEffect(manager=manager)
    effect.attach()
    background = manager.colors.background
    surface = manager.colors.surface
    sea = manager.colors.sea
    effect.on_frame(_beat())
    assert manager.colors.background == background
    assert manager.colors.surface == surface
    assert manager.colors.sea == sea
    effect.detach()


def test_border_is_tinted_but_keeps_lightness(manager):
    """Borders get a low-saturation wash at the walking hue (pure hue
    rotation is a no-op on near-gray border colors), with value/lightness
    preserved so contrast survives."""
    from PySide6.QtGui import QColor

    effect = ThemeEffect(manager=manager)
    effect.attach()
    before = QColor(manager.colors.border)
    effect.on_frame(_beat())
    after = QColor(manager.colors.border)
    assert after.name() != before.name()  # panel outlines visibly shift
    assert after.valueF() == pytest.approx(before.valueF(), abs=0.02)
    effect.detach()


def test_theme_switch_while_attached_resnapshots(manager, qtbot):
    effect = ThemeEffect(manager=manager)
    effect.attach()
    effect.on_frame(_beat())  # walk away from the original colors
    manager.set_theme_by_name("slate")  # replaces manager._colors
    after_switch = dict(vars(manager.colors))
    effect.detach()
    # Detach must NOT undo the user's theme switch.
    assert dict(vars(manager.colors)) == after_switch
