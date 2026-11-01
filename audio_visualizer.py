"""Visualizador GTK4 opcional; nunca interviene en el proceso de grabación."""
import math
import os
import select
import shutil
import struct
import subprocess
import threading
import time

from gi.repository import Gtk, GLib


class AudioVisualizer(Gtk.DrawingArea):
    """Ondas decorativas cuya amplitud depende del RMS real del monitor."""

    def __init__(self):
        super().__init__()
        self.set_content_height(110)
        self.set_hexpand(True)
        self.add_css_class('audio-visualizer')
        self.set_draw_func(self._draw)
        self._level = 0.0
        self._target = 0.0
        self._phase = 0.0
        self._running = False
        self._proc = None
        self._thread = None
        self._stop = threading.Event()
        self._session = 0
        self._timer_id = GLib.timeout_add(33, self._tick)

    def start(self, sink):
        self.stop()
        self._session += 1
        session = self._session
        self._stop = threading.Event()
        if not shutil.which('parec'):
            return False
        # Captura independiente, de baja resolución, sin almacenar audio.
        cmd = ['parec', '--device=' + sink + '.monitor', '--raw',
               '--format=s16le', '--rate=8000', '--channels=1']
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    bufsize=0)
        except OSError:
            return False
        self._proc = proc
        self._running = True
        self._thread = threading.Thread(target=self._read_levels,
                                        args=(proc, self._stop, session), daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._session += 1
        self._running = False
        self._target = 0.0
        self._stop.set()
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        # No bloquear el hilo GTK esperando a parec.

    def _read_levels(self, proc, stop_event, session):
        fd = proc.stdout.fileno()
        pending = bytearray()
        try:
            while not stop_event.is_set() and proc.poll() is None:
                ready, _, _ = select.select([fd], [], [], 0.25)
                if not ready:
                    continue
                data = os.read(fd, 4096)
                if not data:
                    break
                pending.extend(data)
                # Ventanas de 1024 muestras (128 ms); coste bajo.
                while len(pending) >= 2048:
                    block = bytes(pending[:2048])
                    del pending[:2048]
                    samples = struct.unpack('<1024h', block)
                    rms = math.sqrt(sum(v * v for v in samples) / 1024) / 32768.0
                    # Curva visual comprimida; el silencio sigue siendo cero.
                    level = min(1.0, math.sqrt(rms) * 2.0)
                    GLib.idle_add(self._receive_level, session, level)
        except (OSError, ValueError):
            pass
        finally:
            try:
                proc.stdout.close()
            except OSError:
                pass
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        proc.kill()
                    except OSError:
                        pass
            GLib.idle_add(self._monitor_ended, session)

    def _receive_level(self, session, level):
        if session == self._session and self._running:
            self._target = level
        return False

    def _monitor_ended(self, session):
        if session == self._session:
            self._running = False
            self._target = 0.0
        return False

    def _tick(self):
        self._level += (self._target - self._level) * (0.22 if self._target > self._level else 0.10)
        if self._level < 0.001:
            self._level = 0.0
        if self._running and self._level > 0.002:
            self._phase += 0.065
        self.queue_draw()
        return True

    def _draw(self, area, cr, width, height):
        mid = height / 2
        # GTK usa la paleta del tema para la superficie; ondas con acento moderado.
        colors = ((0.30, 0.57, 0.91, 0.85),
                  (0.30, 0.73, 0.76, 0.65),
                  (0.59, 0.50, 0.85, 0.50))
        for k, (r, g, b, alpha) in enumerate(colors):
            cr.set_source_rgba(r, g, b, alpha)
            cr.set_line_width(2.5 if k == 0 else 1.6)
            for x in range(max(2, width)):
                u = x / max(1, width - 1)
                envelope = max(0, math.sin(math.pi * u)) ** 1.7
                wave = (math.sin(u * (17 + k * 4) + self._phase + k * 0.8) * 0.75 +
                        math.sin(u * (31 - k * 2) - self._phase * 0.7 + k) * 0.25)
                y = mid + wave * envelope * self._level * height * 0.42
                if x == 0:
                    cr.move_to(x, y)
                else:
                    cr.line_to(x, y)
            cr.stroke()

    def dispose_monitor(self):
        self.stop()
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
