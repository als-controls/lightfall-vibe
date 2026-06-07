# lightfall-vibe

---

The Lightfall plugin you didn't know you didn't need. 

Vibe mode for [Lightfall](https://git.als.lbl.gov/ncs/lightfall): a demo plugin
that makes the UI react to whatever music is playing.

- **Spinner** — the RunEngine spinner spins with the music's energy
- **Theme** — accent colors hue-shift on every beat
- **Dock pulse** — the layout blips on kicks (off by default)
- **Spectrum panel** — a live 24-band analyzer showing the audio driving it all

Audio comes from system loopback by default (WASAPI on Windows, PulseAudio/
PipeWire monitor sources on Linux) via [`soundcard`](https://pypi.org/project/SoundCard/),
so it reacts to whatever you're playing — or pick a microphone in settings.

## Install

Install into the same environment that runs Lightfall:

    pip install -e .

Then in Lightfall: Preferences → Vibe → pick a device, hit Enable, play music.

## Development

    python -m venv .venv
    .venv/Scripts/python -m pip install -e ../lightfall -e .[dev]
    .venv/Scripts/python -m pytest

This is a toy. It pokes one private attribute of the host's spinner widget and
is proud of it.
