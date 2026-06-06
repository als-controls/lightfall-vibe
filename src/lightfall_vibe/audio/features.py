"""Pure-numpy spectral feature extraction for Vibe mode.

No Qt imports in this module -- it must stay unit-testable without a
QApplication and reusable from any thread.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

N_BANDS = 24
_PEAK_DECAY = 0.999  # per-block decay of the display auto-gain peak tracker
_SMOOTH_DECAY = 0.82  # band display smoothing (fast attack, slow decay)

# --- Kick detection -------------------------------------------------------
# Kicks live here; computed from the RAW spectrum, not the auto-gained
# display bands (auto-gain couples bass flux to whatever band is loudest).
_KICK_LO_HZ = 40.0
_KICK_HI_HZ = 160.0
# A beat must be at least this fraction as strong as the strongest recent
# kick onset. This is the "kick memory" that keeps the detector silent when
# the kicks pause but a quieter bassline keeps playing (live report
# 2026-06-06): a relative-only threshold collapses during the pause and
# promotes bass wobble to beats.
_REL_THRESHOLD = 0.3
_ONSET_PEAK_HALFLIFE_S = 8.0  # kick memory fade: quieter songs recalibrate
_ONSET_SMOOTH = 0.5  # one-pole smoothing of the onset envelope
_REFRACTORY_S = 0.25  # min time between beats (240 BPM ceiling)
_RMS_GATE = 1e-4  # ignore blocks that are essentially silence


@dataclass(frozen=True)
class VibeFrame:
    """One block's worth of audio features.

    Attributes:
        bands: (N_BANDS,) smoothed, auto-gained band magnitudes in [0, 1].
        rms: Root-mean-square level of the (padded/truncated) block.
        centroid: Spectral centroid, log-normalized to [0, 1] over the
            analyzer's frequency range (0 = bass-heavy, 1 = bright).
        flux: Kick onset strength relative to the recent kick peak, ~[0, 1].
        beat: True if this block is a kick onset (beat).
    """

    bands: np.ndarray
    rms: float
    centroid: float
    flux: float
    beat: bool


class SpectrumAnalyzer:
    """Stateful block-by-block spectral analyzer.

    Feed equal-size mono blocks to process(); get a VibeFrame per block.
    Beat detection is kick (40-160 Hz) spectral-flux onset detection,
    anchored to a slow-decaying peak of recent kick onsets: an onset only
    counts as a beat if it is comparable in strength to the kicks the
    detector has recently heard, so pauses in the kick pattern stay silent
    instead of degenerating into noise-triggering.
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

        self._smoothed = np.zeros(n_bands)
        self._peak = 1e-9

        # Kick detector state. The raw-spectrum bin range is independent of
        # the display banding above.
        kick_lo = np.searchsorted(self._freqs, _KICK_LO_HZ)
        kick_hi = max(np.searchsorted(self._freqs, _KICK_HI_HZ), kick_lo + 1)
        self._kick_slice = slice(kick_lo, kick_hi)
        self._prev_kick_energy = 0.0
        self._onset_smoothed = 0.0
        self._onset_peak = 1e-12
        blocks_per_halflife = _ONSET_PEAK_HALFLIFE_S * samplerate / block_size
        self._onset_peak_decay = 0.5 ** (1.0 / blocks_per_halflife)
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
        # (Display only -- the kick detector below uses the raw spectrum.)
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

        # --- Kick onset detection ------------------------------------
        kick_energy = float(spec[self._kick_slice].sum())
        onset = max(0.0, kick_energy - self._prev_kick_energy)
        self._prev_kick_energy = kick_energy
        self._onset_smoothed = (
            _ONSET_SMOOTH * onset + (1.0 - _ONSET_SMOOTH) * self._onset_smoothed
        )
        # Kick memory: remembers how strong real kicks are, fading with a
        # multi-second half-life so quieter material can recalibrate.
        self._onset_peak = max(
            self._onset_peak * self._onset_peak_decay,
            self._onset_smoothed,
            1e-12,
        )
        rel = self._onset_smoothed / self._onset_peak

        beat = False
        if self._refractory > 0:
            self._refractory -= 1
        elif rms > _RMS_GATE:
            threshold = min(_REL_THRESHOLD / max(self.sensitivity, 0.1), 0.95)
            if rel > threshold:
                beat = True
                self._refractory = self._refractory_blocks

        return VibeFrame(
            bands=self._smoothed.copy(),
            rms=rms,
            centroid=centroid,
            flux=rel,
            beat=beat,
        )
