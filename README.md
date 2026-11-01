# Sink Recorder

**Beta 0.9.0 · Linux · Developed and maintained by Iberbits**

Sink Recorder is a GTK4 desktop application for recording system audio from the default PulseAudio-compatible monitor source using FFmpeg. It supports WAV, MP3 and FLAC, a live audio visualizer, and optional post-recording peak normalization to -1 dBFS. When normalization is enabled, the original recording is preserved and a separate normalized copy is generated.

## Installation (Ubuntu)

Download the `.deb` from the GitHub release and run:

```bash
sudo apt install ./sink-recorder_0.9.0-2_all.deb
```

The package requires Python 3.10+, GTK4 Python bindings, FFmpeg and `pulseaudio-utils`. A PulseAudio-compatible sound server (including PipeWire with PulseAudio compatibility) and an available default sink monitor are required.

## Run from source

Install the dependencies above, then run:

```bash
python3 sink_recorder.py
```

Translations are provided as gettext `.po` sources in `po/` and compiled `.mo` catalogs in `locale/`.

## Beta status

This is a beta release. Recording behavior has not yet been validated across all Ubuntu versions, desktop environments, audio devices and failure conditions. Check the destination and recording output before relying on it for important audio.

## License

GNU General Public License v3.0 only (`GPL-3.0-only`). See [LICENSE](LICENSE).

Project maintained by **Iberbits**. External dependencies remain under their respective licenses.
