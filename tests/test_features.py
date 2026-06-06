"""Tests for the pure-numpy spectral feature extractor."""

import numpy as np
import pytest

from lightfall_vibe.audio.features import N_BANDS, SpectrumAnalyzer, VibeFrame

SR = 48000
BLOCK = 1024


def _run_signal(analyzer: SpectrumAnalyzer, signal: np.ndarray) -> list[VibeFrame]:
    """Feed a 1-D signal through the analyzer block by block."""
    frames = []
    for start in range(0, len(signal) - BLOCK + 1, BLOCK):
        frames.append(analyzer.process(signal[start : start + BLOCK]))
    return frames


def _sine(freq: float, seconds: float) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return 0.5 * np.sin(2 * np.pi * freq * t)


def _click_track(bpm: float, seconds: float) -> np.ndarray:
    """Silence with one-block-long broadband bursts at the given tempo."""
    rng = np.random.default_rng(42)
    out = np.zeros(int(SR * seconds))
    interval = int(SR * 60.0 / bpm)
    for start in range(0, len(out) - BLOCK, interval):
        out[start : start + BLOCK] = 0.8 * rng.uniform(-1, 1, BLOCK)
    return out


def test_silence_produces_no_beats_and_zero_rms():
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    frames = _run_signal(analyzer, np.zeros(SR * 2))
    assert all(not f.beat for f in frames)
    assert all(f.rms == pytest.approx(0.0) for f in frames)


def test_frame_shape_and_range():
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    frames = _run_signal(analyzer, _sine(440, 1.0))
    f = frames[-1]
    assert f.bands.shape == (N_BANDS,)
    assert np.all(f.bands >= 0.0)
    assert np.all(f.bands <= 1.0 + 1e-9)
    assert 0.0 <= f.centroid <= 1.0


def test_centroid_tracks_brightness():
    low = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    high = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    low_frames = _run_signal(low, _sine(100, 0.5))
    high_frames = _run_signal(high, _sine(8000, 0.5))
    assert low_frames[-1].centroid < high_frames[-1].centroid


def test_band_energy_lands_in_right_bands():
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    frames = _run_signal(analyzer, _sine(100, 0.5))
    bands = frames[-1].bands
    # A 100 Hz tone should put its energy in the bottom third of the bands.
    assert np.argmax(bands) < N_BANDS // 3


def test_click_track_beats_detected_at_roughly_correct_count():
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    # 120 BPM for 4 seconds = 8 clicks.
    frames = _run_signal(analyzer, _click_track(120, 4.0))
    n_beats = sum(f.beat for f in frames)
    assert 5 <= n_beats <= 11


def test_refractory_prevents_double_triggers():
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    frames = _run_signal(analyzer, _click_track(120, 4.0))
    beat_indices = [i for i, f in enumerate(frames) if f.beat]
    # No two beats within 150 ms (~7 blocks at 1024/48k).
    gaps = np.diff(beat_indices)
    assert np.all(gaps >= 6)


def test_higher_sensitivity_detects_at_least_as_many_beats():
    quiet = _click_track(120, 4.0) * 0.3
    insensitive = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK, sensitivity=0.5)
    sensitive = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK, sensitivity=2.0)
    n_insensitive = sum(f.beat for f in _run_signal(insensitive, quiet))
    n_sensitive = sum(f.beat for f in _run_signal(sensitive, quiet))
    assert n_sensitive >= n_insensitive


def test_short_block_is_padded_not_crashed():
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    frame = analyzer.process(np.zeros(100))
    assert frame.bands.shape == (N_BANDS,)
