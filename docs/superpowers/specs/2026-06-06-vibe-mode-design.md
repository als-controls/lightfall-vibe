# lightfall-vibe: Music-Reactive UI Plugin — Design

**Date:** 2026-06-06
**Status:** Approved
**Purpose:** Fun demo feature. Makes the Lightfall UI react to music: the run-engine
spinner spins with the energy, theme colors shift on beats, dock widgets pulse on
kicks, and a spectrum-analyzer panel shows the audio driving it all.

## Goals & Constraints

- **Demo-grade, not production-grade.** Maximum spectacle when shown off at a
  meeting; correctness bar is "looks awesome and never harms the host app."
- **New repo** (`lightfall-vibe`) so Lightfall and lightfall-dev-plugins gain no
  audio dependencies.
- **Cross-platform:** Windows and Linux. Audio loopback capture must work on both.
- **One new dependency:** `soundcard` (WASAPI loopback on Windows, PulseAudio
  monitor sources on Linux, incl. PipeWire's pulse compat; also plain mic capture).
  Everything else (numpy, pyqtgraph, PySide6) arrives transitively via lightfall.

## Repo & Packaging

- Location: `~/PycharmProjects/ncs/lightfall-vibe` (alongside the other
  `lightfall-*` plugin repos).
- hatch + hatch-vcs `pyproject.toml`, `src/lightfall_vibe/` layout, own `.venv`,
  `README.md`, pytest.
- Declared deps: `lightfall`, `soundcard`, `numpy`, `pyqtgraph` (numpy/pyqtgraph
  declared because imported directly; satisfied transitively).
- Registers via the `lightfall.plugins` entry-point group with a `manifest.py`
  modeled on lightfall-dev-plugins (`PluginEntry` list), declaring two entries:
  - `settings` → `VibeSettingsPlugin`
  - `panel` → `VibePanel`

## Package Layout

```
src/lightfall_vibe/
  manifest.py          # PluginEntry declarations (settings + panel)
  audio/
    capture.py         # CaptureWorker: soundcard capture on background thread
    features.py        # pure-numpy DSP: FFT, bands, beat detection (no Qt)
  conductor.py         # VibeConductor: GUI-thread fan-out of frames to effects
  effects/
    spinner.py         # SpinnerEffect
    theme.py           # ThemeEffect
    pulse.py           # DockPulseEffect
  panel.py             # VibePanel: pyqtgraph spectrum analyzer
  settings.py          # VibeSettingsPlugin: preferences page
```

## Audio Engine

**Capture** (`audio/capture.py`): a background thread runs `soundcard` capture.
Default device is the system loopback (whatever is playing); any mic or monitor
source is selectable. Blocks of ~1024 samples at the device rate.

**Features** (`audio/features.py`, pure numpy, no Qt imports): per block —
windowed rFFT → ~24 log-spaced bands (40 Hz–16 kHz) → a `VibeFrame` dataclass:

| Field      | Meaning                                            |
|------------|----------------------------------------------------|
| `bands`    | band magnitudes (smoothed), for the spectrum panel |
| `rms`      | overall energy → spinner speed                     |
| `centroid` | spectral centroid (brightness)                     |
| `flux`     | bass-band spectral flux                            |
| `beat`     | onset flag: flux vs. rolling-median threshold      |

Beat detection is classic spectral-flux onset detection — demo-grade by design.

**Thread crossing:** frames are emitted via a queued Qt signal to the GUI thread,
throttled to ~30 Hz.

## Conductor & Effects

`VibeConductor` (GUI thread) receives `VibeFrame`s and fans out to three
independently-toggleable effects:

- **SpinnerEffect** — locates `SpinnerIndicator`
  (`lightfall/ui/widgets/runengine_control.py`) via `findChild` and drives its
  rotation rate from RMS. Spins even when the RE is idle (it's a demo). This
  touches the widget's private timer/degrees attributes — accepted brittleness
  for a toy; if it breaks, the fix is a small public `set_spin_rate()` upstream.
- **ThemeEffect** — on enable, snapshots `ThemeManager.get_instance().colors`;
  on beats, rotates accent hues in HSV space and eases back, emitting
  `colors_changed` at **≤10 Hz** (never per-frame — app-wide stylesheet repolish
  is the one real perf hazard). On disable, restores the snapshot exactly.
- **DockPulseEffect** — `QPropertyAnimation` blip on central-area margins on
  kicks. Subtle; off by default; first feature cut if it fights the layout
  system.

## Spectrum Panel

`VibePanel` (a lightfall `PanelPlugin`): pyqtgraph `PlotWidget` +
`BarGraphItem`, 24 bars, heights updated per frame via `setOpts`. Bar brushes
gradient-mapped from the *current* theme accent so the panel and the theme
effect visibly agree; background flashes on beat. Axes hidden, mouse
interaction disabled.

## Settings Page

`VibeSettingsPlugin` (a lightfall `SettingsPlugin`, modeled on
`DevSettingsPlugin`): enable toggle, audio-device combo with refresh button,
sensitivity slider, per-effect checkboxes, and a beat-indicator LED for
verifying detection before a demo. Persisted via `PreferencesManager`.

## Failure Posture

The plugin must never hurt the host:

- Capture errors (no device, device vanished, backend missing) disable vibe
  mode with a toast — never a crash. A box with no audio stack is a no-op.
- Disable always restores theme snapshot and spinner state.
- All effect callbacks are exception-guarded; a failing effect disables itself.

## Testing

- **pytest on `features.py`** with synthetic signals: clicks at a known tempo →
  beats detected at that tempo; sine sweeps → centroid tracks; silence → no
  beats.
- **Conductor mapping** tested with hand-built `VibeFrame`s (no audio, no
  widgets where avoidable).
- Capture, effects, and panel verified manually by playing music at it.
- Tests run with the repo venv (`.venv/Scripts/python -m pytest` /
  `.venv/bin/python -m pytest`), never bare `pytest`.

## Out of Scope

- macOS loopback (soundcard has no loopback there; mic would work untested).
- Real beat *tracking* (tempo/phase estimation) — onset detection only.
- Re-docking choreography / moving widgets between dock areas.
- Upstream lightfall changes (unless the spinner-private approach breaks).
