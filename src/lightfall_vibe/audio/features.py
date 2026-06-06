"""Pure-numpy spectral feature extraction for Vibe mode.

No Qt imports in this module -- it must stay unit-testable without a
QApplication and reusable from any thread.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

N_BANDS = 24
_REFRACTORY_S = 0.15  # min time between beats
_FLUX_WINDOW_S = 1.0  # rolling window for the adaptive beat threshold
_PEAK_DECAY = 0.999  # per-block decay of the auto-gain peak tracker
_SMOOTH_DECAY = 0.82  # band display smoothing (fast attack, slow decay)
_FLUX_FLOOR = 0.02  # absolute flux floor so silence never beats


@dataclass(frozen=True)
class VibeFrame:
    """One block's worth of audio features.

    Attributes:
        bands: (N_BANDS,) smoothed, auto-gained band magnitudes in [0, 1].
        rms: Root-mean-square level of the (padded/truncated) block.
        centroid: Spectral centroid, log-normalized to [0, 1] over the
            analyzer's frequency range (0 = bass-heavy, 1 = bright).
        flux: Positive bass-band spectral flux for this block.
        beat: True if this block is an onset (beat).
    """

    bands: np.ndarray
    rms: float
    centroid: float
    flux: float
    beat: bool


class SpectrumAnalyzer:
    """Stateful block-by-block spectral analyzer.

    Feed equal-size mono blocks to process(); get a VibeFrame per block.
    Beat detection is classic bass spectral-flux onset detection with an
    adaptive (rolling-median) threshold and a refractory period.
    """

    def __init__(
        self,
        samplerate: int = 48000,
        block_size: int = 1024,
        n_bands: int = N_BANDS,
        f_lo: float = 40.0,
        f_hi: float = 16000.0,
        sensitivity: float = 1.0,
    ) -> None:
        self.samplerate = samplerate
        self.block_size = block_size
        self.n_bands = n_bands
        self.f_lo = f_lo
        self.f_hi = min(f_hi, samplerate / 2)
        # >1.0 lowers the beat threshold (more beats); live-tunable.
        self.sensitivity = sensitivity

        self._window = np.hanning(block_size)
        self._freqs = np.fft.rfftfreq(block_size, 1.0 / samplerate)
        edges = np.geomspace(self.f_lo, self.f_hi, n_bands + 1)
        self._band_idx = np.searchsorted(self._freqs, edges)

        self._bass_bands = max(1, n_bands // 6)  # ~4 of 24: the "kick" region

        self._smoothed = np.zeros(n_bands)
        self._peak = 1e-9
        self._prev_bass = 0.0
        blocks_per_window = max(int(_FLUX_WINDOW_S * samplerate / block_size), 4)
        self._flux_history: deque[float] = deque(maxlen=blocks_per_window)
        self._refractory_blocks = max(
            int(_REFRACTORY_S * samplerate / block_size), 1
        )
        self._refractory = 0

    def process(self, block: np.ndarray) -> VibeFrame:
        """Analyze one mono block and return its features."""
        block = np.asarray(block, dtype=np.float64).ravel()
        if block.shape[0] < self.block_size:
            block = np.pad(block, (0, self.block_size - block.shape[0]))
        elif block.shape[0] > self.block_size:
            block = block[: self.block_size]

        spec = np.abs(np.fft.rfft(block * self._window))

        raw_bands = np.empty(self.n_bands)
        for i in range(self.n_bands):
            lo = self._band_idx[i]
            hi = max(self._band_idx[i + 1], lo + 1)
            raw_bands[i] = spec[lo:hi].mean()

        # Auto-gain: normalize against a slowly decaying running peak.
        self._peak = max(self._peak * _PEAK_DECAY, float(raw_bands.max()), 1e-9)
        norm = np.clip(raw_bands / self._peak, 0.0, 1.0)

        # Fast attack, slow decay -- bars jump up and fall smoothly.
        decayed = self._smoothed * _SMOOTH_DECAY
        self._smoothed = np.maximum(norm, decayed)

        rms = float(np.sqrt(np.mean(block**2)))

        total = float(spec.sum())
        if total > 1e-12:
            centroid_hz = float((spec * self._freqs).sum() / total)
            centroid_hz = float(np.clip(centroid_hz, self.f_lo, self.f_hi))
            centroid = float(
                np.log(centroid_hz / self.f_lo) / np.log(self.f_hi / self.f_lo)
            )
        else:
            centroid = 0.0

        bass = float(norm[:self._bass_bands].sum())
        flux = max(0.0, bass - self._prev_bass)
        self._prev_bass = bass

        beat = False
        if self._refractory > 0:
            self._refractory -= 1
        elif len(self._flux_history) >= 4:
            median = float(np.median(self._flux_history))
            threshold = max(
                median * 1.5 / max(self.sensitivity, 0.1), _FLUX_FLOOR
            )
            if flux > threshold:
                beat = True
                self._refractory = self._refractory_blocks
        self._flux_history.append(flux)

        return VibeFrame(
            bands=self._smoothed.copy(),
            rms=rms,
            centroid=centroid,
            flux=flux,
            beat=beat,
        )
