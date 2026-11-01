# Sink Recorder

**Beta 0.9.0 · Linux · Developed and maintained by Iberbits**

Sink Recorder is a GTK4 desktop application for recording system audio from the default PulseAudio-compatible monitor source using FFmpeg. It supports WAV, MP3 and FLAC, a live audio visualizer, and optional post-recording peak normalization to -1 dBFS. When normalization is enabled, the original recording is preserved and a separate normalized copy is generated.

## Installation (Ubuntu)

A public beta package will be published in [Releases](https://github.com/iberbits/sink-recorder/releases) after packaging verification.

The application requires Python 3, GTK4 Python bindings, FFmpeg and PulseAudio utilities. A PulseAudio-compatible sound server (including PipeWire with PulseAudio compatibility) and an available default sink monitor are required.

## Beta status

This is a beta project. Recording behavior has not yet been validated across all Ubuntu versions, desktop environments, audio devices and failure conditions. Check the destination and recording output before relying on it for important audio.

## License

The intended license is GNU GPL v3.0 only (GPL-3.0-only). The full license text and corresponding source will be added before the beta release.

Project maintained by **Iberbits**. External dependencies remain under their respective licenses.
