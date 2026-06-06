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


def _kick_track(bpm: float, seconds: float, amplitude: float = 0.8) -> np.ndarray:
    """Silence with 50 ms 60 Hz tone bursts (synthetic kick drum)."""
    out = np.zeros(int(SR * seconds))
    interval = int(SR * 60.0 / bpm)
    burst_len = int(SR * 0.05)
    t = np.arange(burst_len) / SR
    burst = amplitude * np.sin(2 * np.pi * 60.0 * t) * np.linspace(1, 0, burst_len)
    for start in range(0, len(out) - burst_len, interval):
        out[start : start + burst_len] = burst
    return out


def _bassline_wobble(seconds: float, amplitude: float = 0.15) -> np.ndarray:
    """Sustained quiet bass with slow amplitude modulation (no kicks)."""
    t = np.arange(int(SR * seconds)) / SR
    am = 0.8 + 0.2 * np.sin(2 * np.pi * 2.0 * t)  # 2 Hz swell
    return amplitude * am * np.sin(2 * np.pi * 70.0 * t)


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
    assert len(beat_indices) >= 2
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


def test_kick_track_beats_detected():
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    # 120 BPM for 4 seconds = 8 synthetic kicks.
    frames = _run_signal(analyzer, _kick_track(120, 4.0))
    n_beats = sum(f.beat for f in frames)
    assert 5 <= n_beats <= 11


def test_kick_pause_with_residual_bassline_stays_silent():
    """Regression (live report 2026-06-06): when the kicks pause but a quiet
    bassline keeps playing, the detector must NOT keep firing. Onset strength
    is anchored to the recent kick peak, not just a relative median."""
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    signal = np.concatenate([_kick_track(120, 4.0), _bassline_wobble(4.0)])
    frames = _run_signal(analyzer, signal)
    n_pause_frames = int(SR * 4.0) // BLOCK
    pause_beats = sum(f.beat for f in frames[-n_pause_frames:])
    assert pause_beats == 0


def test_detector_recalibrates_after_long_quiet_spell():
    """The kick-peak anchor decays: a genuinely quieter song must still get
    beats once the loud-song memory fades (~tens of seconds)."""
    analyzer = SpectrumAnalyzer(samplerate=SR, block_size=BLOCK)
    loud = _kick_track(120, 4.0, amplitude=0.8)
    silence = np.zeros(int(SR * 30.0))
    quiet = _kick_track(120, 4.0, amplitude=0.1)
    frames = _run_signal(analyzer, np.concatenate([loud, silence, quiet]))
    n_quiet_frames = int(SR * 4.0) // BLOCK
    quiet_beats = sum(f.beat for f in frames[-n_quiet_frames:])
    assert quiet_beats >= 4
