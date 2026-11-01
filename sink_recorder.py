import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gdk
import subprocess
import threading
import os
import re
import time
from pathlib import Path
from datetime import datetime

from audio_visualizer import AudioVisualizer

import gettext

_LOCALE_DIR = Path(__file__).resolve().parent / 'locale'
_ = gettext.translation('sink-recorder', localedir=str(_LOCALE_DIR), fallback=True).gettext


class RecorderApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.recorder.app')
        self.proc = None
        self.output_dir = None
        self.current_sink = None
        self.current_file = None
        self.stopping = False
        self.generation = 0
        self.level = None
        self.normalize_requested = False
        self.normalizing = False
        self.started_at = None
        self.recording_active = False

    def _label(self, text, css=None, align=Gtk.Align.START):
        label = Gtk.Label(label=text)
        label.set_halign(align)
        label.set_xalign(0 if align == Gtk.Align.START else 0.5)
        if css:
            label.add_css_class(css)
        return label

    def _card(self, css='panel'):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class(css)
        card.set_hexpand(True)
        return card

    def load_css(self):
        css_file = Path(__file__).resolve().with_name('style.css')
        if not css_file.is_file():
            print(_('Warning: {css_file} not found; using the GTK theme.').format(css_file=css_file))
            return
        provider = Gtk.CssProvider()
        try:
            provider.load_from_path(str(css_file))
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception as exc:
            print(_('Warning: could not load CSS: {exc}').format(exc=exc))

    def do_activate(self):
        if hasattr(self, 'window'):
            self.window.present()
            return
        self.load_css()
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title('Sink Recorder')
        self.window.set_default_size(920, 650)
        self.window.set_size_request(640, 540)
        self.window.connect('close-request', self.on_close)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer.add_css_class('app-root')
        outer.set_hexpand(True)
        outer.set_vexpand(True)
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.add_css_class('app-header')
        header.set_hexpand(True)
        # Icono de marca; si falta, mantener un icono simbólico del tema.
        icon_path = Path(__file__).resolve().with_name('sink-recorder.png')
        if icon_path.is_file():
            logo = Gtk.Image.new_from_file(str(icon_path))
        else:
            logo = Gtk.Image.new_from_icon_name('audio-input-microphone-symbolic')
        logo.set_pixel_size(40)
        logo.add_css_class('brand-icon')
        header.append(logo)
        brand = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        brand.append(self._label('Sink Recorder', 'brand-title'))
        brand.append(self._label(_('System audio capture'), 'muted'))
        header.append(brand)
        outer.append(header)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        outer.append(scroller)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.add_css_class('content')
        content.set_hexpand(True)
        scroller.set_child(content)

        hero = self._card('hero-panel')
        hero_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.status_dot = Gtk.Box()
        self.status_dot.add_css_class('status-dot')
        hero_header.append(self.status_dot)
        hero_header.append(self._label(_('RECORDING STATUS'), 'eyebrow'))
        hero.append(hero_header)
        self.timer_label = self._label('00:00:00', 'timer', Gtk.Align.CENTER)
        hero.append(self.timer_label)
        self.level_label = self._label(_('Status: ready'), 'status-message', Gtk.Align.CENTER)
        self.level_label.set_wrap(True)
        hero.append(self.level_label)
        self.visualizer = AudioVisualizer()
        hero.append(self.visualizer)
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls.set_halign(Gtk.Align.CENTER)
        self.start_btn = Gtk.Button(label=_('Start recording'))
        self.start_btn.add_css_class('suggested-action')
        self.start_btn.add_css_class('control-button')
        self.start_btn.connect('clicked', self.start_recording)
        controls.append(self.start_btn)
        self.stop_btn = Gtk.Button(label=_('Stop'))
        self.stop_btn.add_css_class('destructive-action')
        self.stop_btn.add_css_class('control-button')
        self.stop_btn.connect('clicked', self.stop_recording)
        self.stop_btn.set_sensitive(False)
        controls.append(self.stop_btn)
        hero.append(controls)
        content.append(hero)

        settings = self._card()
        settings.append(self._label(_('Recording settings'), 'section-title'))
        grid = Gtk.Grid(column_spacing=18, row_spacing=12)
        grid.set_hexpand(True)
        settings.append(grid)
        name_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        name_col.append(self._label(_('File name'), 'field-label'))
        self.entry = Gtk.Entry(placeholder_text=_('Name or automatic date'))
        self.entry.set_hexpand(True)
        name_col.append(self.entry)
        grid.attach(name_col, 0, 0, 1, 1)
        format_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        format_col.append(self._label(_('Format'), 'field-label'))
        self.format_combo = Gtk.DropDown.new_from_strings(['wav', 'mp3', 'flac'])
        format_col.append(self.format_combo)
        grid.attach(format_col, 1, 0, 1, 1)
        grid.set_column_homogeneous(True)
        folder_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        folder_col.append(self._label(_('Destination folder'), 'field-label'))
        self.folder_btn = Gtk.Button(label=_('Choose destination folder…'))
        self.folder_btn.set_halign(Gtk.Align.FILL)
        self.folder_btn.connect('clicked', self.select_folder)
        folder_col.append(self.folder_btn)
        grid.attach(folder_col, 0, 1, 2, 1)
        content.append(settings)

        processing = self._card()
        processing.append(self._label(_('Processing'), 'section-title'))
        normalize_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.normalize_check = Gtk.CheckButton(label=_('Normalize when finished (−1 dBFS)'))
        self.normalize_check.set_active(True)
        normalize_row.append(self.normalize_check)
        info_btn = Gtk.MenuButton()
        info_btn.set_icon_name('dialog-information-symbolic')
        info_btn.set_tooltip_text(_('About normalization'))
        info_btn.update_property([Gtk.AccessibleProperty.LABEL],
                                 [_('About normalization')])
        popover = Gtk.Popover()
        info = self._label(_('Raises the audio peak to −1 dBFS without equalization or compression. It may sound louder, but cannot restore lost detail. The original is kept and, when applicable, another file with the suffix _normalizado is generated.'))
        info.set_wrap(True)
        info.set_max_width_chars(46)
        info.set_margin_top(12)
        info.set_margin_bottom(12)
        info.set_margin_start(12)
        info.set_margin_end(12)
        popover.set_child(info)
        info_btn.set_popover(popover)
        normalize_row.append(info_btn)
        processing.append(normalize_row)
        processing.append(self._label(_('Normalizes the recording to −1 dBFS when finished. A normalized version is created, and the original recording is always kept unchanged.'), 'muted'))
        content.append(processing)

        device = self._card()
        device.append(self._label(_('Audio source'), 'section-title'))
        self.device_label = self._label(_('Device: awaiting detection'), 'device-name')
        self.device_label.set_wrap(True)
        self.device_label.set_selectable(True)
        device.append(self.device_label)
        content.append(device)

        self.window.set_child(outer)
        self.window.present()
        GLib.timeout_add_seconds(1, self.check_sink_change)
        GLib.timeout_add(250, self.update_timer)

    def update_timer(self):
        if self.started_at is not None:
            seconds = int(time.monotonic() - self.started_at)
            self.timer_label.set_text(f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}')
        return True

    def select_folder(self, _button):
        dialog = Gtk.FileChooserDialog(title=_('Select folder'), transient_for=self.window,
                                       modal=True, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(_('Cancel'), Gtk.ResponseType.CANCEL,
                           _('Select'), Gtk.ResponseType.ACCEPT)
        dialog.connect('response', self.on_folder_selected)
        dialog.present()

    def on_folder_selected(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            path = file.get_path() if file else None
            if path:
                self.output_dir = path
                self.folder_btn.set_label(path)
        dialog.destroy()

    def get_default_sink(self):
        try:
            result = subprocess.run(['pactl', 'get-default-sink'], capture_output=True,
                                    text=True, timeout=3, check=True)
            return result.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None

    def make_filename(self):
        title = self.entry.get_text().strip() or datetime.now().strftime('%Y%m%d_%H%M%S')
        title = re.sub(r'[\\/\x00-\x1f]', '_', title)
        fmt = self.format_combo.get_selected_item().get_string()
        if self.output_dir:
            folder = self.output_dir
        else:
            music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC)
            base_dir = Path(music) if music else Path.home() / 'Grabaciones'
            folder = str(base_dir / 'Sink Recorder')
            os.makedirs(folder, mode=0o755, exist_ok=True)
        if not os.path.isdir(folder):
            raise OSError(_('The destination folder does not exist'))
        base = os.path.join(folder, title)
        for n in range(10000):
            path = f'{base}{"_" + str(n) if n else ""}.{fmt}'
            try:
                # Reserva exclusiva: evita sobrescribir una grabación existente.
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.close(fd)
                return path
            except FileExistsError:
                continue
        raise OSError(_('Too many files with the same name'))

    def set_ui(self, recording=False, busy=False, message=None):
        self.start_btn.set_sensitive(not recording and not busy)
        self.stop_btn.set_sensitive(recording and not busy)
        self.start_btn.set_label(_('Recording…') if recording else _('Start recording'))
        self.status_dot.set_css_classes(['status-dot', 'recording-dot'] if recording else ['status-dot'])
        self.recording_active = recording
        if recording and self.started_at is None:
            self.started_at = time.monotonic()
        if not recording:
            self.started_at = None
        self.level_label.set_label(message or (_('Status: recording') if recording else _('Status: ready')))

    def launch(self, sink):
        filename = self.make_filename()
        cmd = ['ffmpeg', '-hide_banner', '-nostats', '-loglevel', 'error',
               '-f', 'pulse', '-i', sink + '.monitor', '-y', filename]
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except Exception:
            os.unlink(filename)
            raise
        self.proc = proc
        self.current_sink = sink
        self.current_file = filename
        self.normalize_requested = self.normalize_check.get_active()
        self.generation += 1
        gen = self.generation
        self.device_label.set_label(_('Device: {sink}').format(sink=sink))
        self.set_ui(recording=True)
        self.visualizer.start(sink)
        threading.Thread(target=self.watch_process, args=(proc, gen), daemon=True).start()

    def watch_process(self, proc, gen):
        # No usar communicate(): cierra stdin y FFmpeg puede detenerse
        # inmediatamente al recibir EOF. Mantener stdin abierto hasta enviar 'q'.
        try:
            err = proc.stderr.read() if proc.stderr else b''
            proc.wait()
            error = err.decode('utf-8', errors='replace')[-1200:]
        except Exception as exc:
            error = str(exc)
        GLib.idle_add(self.process_finished, proc, gen, error)

    def process_finished(self, proc, gen, error):
        if gen != self.generation or proc is not self.proc:
            return False
        self.proc = None
        self.stopping = False
        self.visualizer.stop()
        if proc.returncode != 0:
            self.set_ui(message=_('FFmpeg error ({code}): {error}').format(code=proc.returncode, error=error[:180]))
            print(_('FFmpeg error:'), error)
        else:
            self.set_ui(message=_('Saved: {file}').format(file=self.current_file))
        return False

    def normalize_async(self, source):
        """Procesamiento posterior: nunca modifica la grabación original."""
        self.normalizing = True
        self.set_ui(busy=True, message=_('Status: analyzing volume...'))
        def worker():
            output = None
            try:
                scan = subprocess.run(
                    ['ffmpeg', '-hide_banner', '-nostats', '-i', source,
                     '-af', 'volumedetect', '-f', 'null', '-'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    text=True, timeout=3600)
                if scan.returncode != 0:
                    raise RuntimeError(_('Error analyzing audio: ') + scan.stderr[-300:])
                peaks = re.findall(r'max_volume:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*dB', scan.stderr)
                if not peaks:
                    raise RuntimeError(_('Could not determine audio peak'))
                peak = float(peaks[-1])
                if peak == float('-inf'):
                    message = _('Silent recording: original kept, not normalized')
                elif peak >= -1.0:
                    message = _('Peak >= -1 dBFS: original kept, no amplification')
                else:
                    gain = -1.0 - peak
                    base, ext = os.path.splitext(source)
                    for n in range(10000):
                        candidate = f'{base}_normalizado{("_" + str(n)) if n else ""}{ext}'
                        try:
                            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                            os.close(fd)
                            output = candidate
                            break
                        except FileExistsError:
                            continue
                    if not output:
                        raise RuntimeError(_('Could not reserve a name for the normalized file'))
                    fmt = ext.lower()
                    codec = ['-c:a', 'pcm_s16le'] if fmt == '.wav' else (
                        ['-c:a', 'flac'] if fmt == '.flac' else ['-c:a', 'libmp3lame', '-q:a', '2'])
                    result = subprocess.run(
                        ['ffmpeg', '-hide_banner', '-nostats', '-loglevel', 'error',
                         '-i', source, '-map', '0:a:0', '-af', f'volume={gain:.4f}dB',
                         *codec, '-y', output],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        text=True, timeout=3600)
                    if result.returncode != 0:
                        raise RuntimeError(_('Normalization error: ') + result.stderr[-300:])
                    verify = subprocess.run(
                        ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type',
                         '-of', 'default=noprint_wrappers=1', output],
                        capture_output=True, text=True, timeout=30)
                    if verify.returncode != 0 or 'codec_type=audio' not in verify.stdout or os.path.getsize(output) == 0:
                        raise RuntimeError(_('Normalized file failed verification'))
                    message = _('Normalized: {file} (gain +{gain:.1f} dB)').format(file=output, gain=gain)
            except Exception as exc:
                if output:
                    try:
                        os.unlink(output)
                    except OSError:
                        pass
                message = _('Normalization failed (original unchanged): {error}').format(error=exc)
            GLib.idle_add(self.normalization_finished, message)
        threading.Thread(target=worker, daemon=True).start()

    def normalization_finished(self, message):
        self.normalizing = False
        self.set_ui(message=message)
        return False

    def start_recording(self, _button):
        if self.proc or self.stopping or self.normalizing:
            return
        sink = self.get_default_sink()
        if not sink:
            self.set_ui(message=_('Error: audio output not found'))
            return
        try:
            self.launch(sink)
        except (OSError, subprocess.SubprocessError) as exc:
            self.set_ui(message=_('Error starting: {error}').format(error=exc))

    def finish_async(self, restart_sink=None, closing=False):
        if not self.proc or self.stopping:
            return
        proc = self.proc
        gen = self.generation
        self.stopping = True
        self.visualizer.stop()
        self.set_ui(busy=True, message=_('Status: finalizing file...'))
        def worker():
            try:
                # FFmpeg acepta 'q' en stdin y escribe el tráiler del archivo.
                if proc.poll() is None and proc.stdin:
                    proc.stdin.write(b'q\n')
                    proc.stdin.flush()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            except (BrokenPipeError, OSError, ValueError):
                pass
            GLib.idle_add(self.after_finish, proc, gen, restart_sink, closing)
        threading.Thread(target=worker, daemon=True).start()

    def after_finish(self, proc, gen, restart_sink, closing):
        if gen != self.generation:
            return False
        # El hilo observador puede no haber publicado aún el resultado.
        self.proc = None
        self.stopping = False
        if closing:
            self.visualizer.dispose_monitor()
            self.window.destroy()
            return False
        if restart_sink:
            try:
                self.launch(restart_sink)
                self.level_label.set_label(_('Status: recording (new segment after output change)'))
            except OSError as exc:
                self.set_ui(message=_('Error changing output: {error}').format(error=exc))
        else:
            if proc.returncode == 0 and self.normalize_requested:
                self.normalize_async(self.current_file)
            else:
                self.set_ui(message=(_('Status: recording saved') if proc.returncode == 0
                                     else _('Error closing file (code {code})').format(code=proc.returncode)))
        return False

    def stop_recording(self, _button):
        self.finish_async()

    def check_sink_change(self):
        if self.proc and not self.stopping and self.proc.poll() is None:
            sink = self.get_default_sink()
            if sink and sink != self.current_sink:
                self.finish_async(restart_sink=sink)
        return True

    def on_close(self, _window):
        if self.normalizing:
            self.level_label.set_label(_('Wait for normalization to finish before closing'))
            return True
        if self.proc:
            if not self.stopping:
                self.finish_async(closing=True)
            return True
        self.visualizer.dispose_monitor()
        return False


app = RecorderApp()
app.run()
