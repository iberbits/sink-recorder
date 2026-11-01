#!/usr/bin/env python3
"""Build the Sink Recorder .deb from this repository (requires dpkg-deb)."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parent
version = "0.9.0-4"
out = root / f"sink-recorder_{version}_all.deb"
with tempfile.TemporaryDirectory(prefix="sink-recorder-") as tmp:
    pkg = Path(tmp) / "pkg"
    app = pkg / "usr/share/sink-recorder"
    app.mkdir(parents=True)
    for name in ("sink_recorder.py", "audio_visualizer.py", "style.css", "sink-recorder.png"):
        shutil.copy2(root / name, app / name)
    catalogs = sorted((root / "locale").glob("*/LC_MESSAGES/sink-recorder.mo"))
    if len(catalogs) != 6:
        raise RuntimeError("Expected six compiled gettext catalogs")
    for src in catalogs:
        dest = app / "locale" / src.parent.parent.name / "LC_MESSAGES" / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    launcher = pkg / "usr/bin/sink-recorder"
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/share/sink-recorder/sink_recorder.py "$@"\n')
    launcher.chmod(0o755)
    desktop = pkg / "usr/share/applications/com.recorder.app.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.write_text("[Desktop Entry]\nType=Application\nName=Sink Recorder\nComment=Record system audio\nComment[es]=Graba el audio del sistema\nExec=sink-recorder\nIcon=sink-recorder\nTerminal=false\nCategories=AudioVideo;Audio;Recorder;\nStartupNotify=true\n")
    icon = pkg / "usr/share/icons/hicolor/256x256/apps/sink-recorder.png"
    icon.parent.mkdir(parents=True)
    shutil.copy2(root / "sink-recorder.png", icon)
    doc = pkg / "usr/share/doc/sink-recorder"
    doc.mkdir(parents=True)
    shutil.copy2(root / "LICENSE", doc / "LICENSE")
    (doc / "copyright").write_text("Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\nUpstream-Name: Sink Recorder\nSource: https://github.com/iberbits/sink-recorder\n\nFiles: *\nCopyright: 2026 Iberbits\nLicense: GPL-3.0-only\n See /usr/share/doc/sink-recorder/LICENSE for the complete license text.\n\nExternal dependencies are distributed under their own licenses.\n")
    control = pkg / "DEBIAN/control"
    control.parent.mkdir(parents=True)
    control.write_text(f"Package: sink-recorder\nVersion: {version}\nSection: sound\nPriority: optional\nArchitecture: all\nMaintainer: Iberbits <262950674+iberbits@users.noreply.github.com>\nDepends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, ffmpeg, pulseaudio-utils\nDescription: GTK4 system audio recorder\n Records desktop audio using FFmpeg and PulseAudio-compatible sinks.\n Includes a live visualizer, optional peak normalization and translations.\n")
    for path in (pkg, *pkg.rglob("*")):
        if path.is_dir():
            path.chmod(0o755)
    subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(pkg), str(out)], check=True)
print(f"Built {out}")
