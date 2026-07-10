import ctypes
import os
import platform
import queue
import threading
import time
import uuid

import numpy as np
import pyperclip
import sounddevice as sd
from pynput import keyboard
from scipy.io.wavfile import write


# ---------------------------------------------------------------------------
# Asset sound player (Windows MCI — no extra dependencies)
# ---------------------------------------------------------------------------
_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "asset")

# Map logical names to filenames (handles the typo in starrt.mp3).
_SOUND_FILES = {
    "start": "starrt.mp3",
    "end":   "end.mp3",
}


def play_asset_sound(name: str) -> None:
    """Play an asset MP3 non-blocking. Silently skipped on non-Windows or if
    the file is missing."""
    if os.name != "nt":
        return
    filename = _SOUND_FILES.get(name)
    if not filename:
        return
    path = os.path.join(_ASSET_DIR, filename)
    if not os.path.isfile(path):
        return

    def _play(p=path):
        try:
            winmm = ctypes.windll.winmm
            # Use a unique alias per play call so overlapping calls don't clash.
            alias = f"ss_{name}_{id(p)}"
            cmd_open  = f'open "{p}" type mpegvideo alias {alias}'
            cmd_play  = f'play {alias} wait'
            cmd_close = f'close {alias}'
            winmm.mciSendStringW(cmd_open,  None, 0, None)
            winmm.mciSendStringW(cmd_play,  None, 0, None)
            winmm.mciSendStringW(cmd_close, None, 0, None)
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()
from refiner import Refiner
from runtime import configure_logging, recordings_dir
from transcriber import Transcriber

logger = configure_logging()

SAMPLE_RATE = 16000
POLL_INTERVAL_S = 0.01
PASTE_DELAY_S = 0.04
INDICATOR_POLL_MS = 50
INDICATOR_DEFAULT_TTL_S = 1.2
ALT_HOLD_TRIGGER_S = 0.28
PRINT_HOTKEY_DEBUG_TRANSCRIPTS = False
KEEP_ONLY_LATEST_PENDING_JOB = True

APP_PAUSED = False
APP_RUNNING = True

IS_WINDOWS = os.name == "nt"
IS_MACOS = platform.system() == "Darwin"

VK_RMENU = 0xA5
_user32 = ctypes.windll.user32 if IS_WINDOWS else None
SW_RESTORE = 9

ALT_KEYS = tuple(
    key
    for key in (
        keyboard.Key.alt,
        keyboard.Key.alt_l,
        keyboard.Key.alt_r,
        getattr(keyboard.Key, "alt_gr", None),
    )
    if key is not None
)
SHIFT_KEYS = tuple(
    key
    for key in (
        keyboard.Key.shift,
        keyboard.Key.shift_l,
        keyboard.Key.shift_r,
    )
    if key is not None
)


def is_right_alt_pressed():
    if _user32 is None:
        return False
    return bool(_user32.GetAsyncKeyState(VK_RMENU) & 0x8000)


def get_foreground_window_handle():
    if _user32 is None:
        return None
    try:
        hwnd = _user32.GetForegroundWindow()
    except Exception:
        return None
    return int(hwnd) if hwnd else None


def restore_foreground_window_handle(hwnd):
    if _user32 is None or not hwnd:
        return
    try:
        # Only un-minimise if the window is actually iconic; otherwise just
        # bring it to the foreground without altering its visual state.
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
        _user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

def cleanup_audio_file(path):
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not remove temporary recording: %s", path)


def paste_text_at_cursor(text, key_controller, target_hwnd=None):
    payload = text.strip()
    if not payload:
        return False

    previous_clipboard = None
    should_restore_clipboard = False
    try:
        previous_clipboard = pyperclip.paste()
        should_restore_clipboard = True
    except pyperclip.PyperclipException:
        should_restore_clipboard = False

    pyperclip.copy(payload)
    time.sleep(PASTE_DELAY_S)

    if IS_WINDOWS:
        # Explicitly release modifiers in case they are stuck logically by the OS
        for key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
                    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
            key_controller.release(key)

        if target_hwnd:
            restore_foreground_window_handle(target_hwnd)
        time.sleep(0.1)

    modifier_key = keyboard.Key.cmd if IS_MACOS else keyboard.Key.ctrl

    # Send explicit press and release rather than context managers for complete execution
    key_controller.press(modifier_key)
    time.sleep(0.02)
    key_controller.press("v")
    time.sleep(0.02)
    key_controller.release("v")
    key_controller.release(modifier_key)

    if should_restore_clipboard:
        # Give target app ample time (0.35s) to read the clipboard asynchronously
        # before we overwrite it with the previous content.
        time.sleep(0.35)
        try:
            pyperclip.copy(previous_clipboard)
        except pyperclip.PyperclipException:
            pass

    return True


class FloatingStatusIndicator:
    """
    Floating status pill styled after the HTML glassmorphism design:
    - Glassmorphic pill with gradient background (similar to HTML .widget-container)
    - Ambient glow effect underneath the indicator
    - Ultra-thin border with glass effect
    - Inset top-edge highlight simulating CSS 'inset 0 1px 1px rgba(255,255,255,0.1)'
    - Accent color applied to text, border tint, dot — NOT heavy background fill
    - Pulsing dot animation for the recording state
    """

    _TRANSPARENT_KEY = "#fdfdfc"

    # Geometry — matches HTML: border-radius 30px, padding 8px 18px
    # _RADIUS is passed large; _pill() caps it at h//2 → true stadium/pill shape.
    _RADIUS  = 999
    _PAD_X   = 18
    _PAD_Y   = 8

    # Dot left of the label — matches HTML icon gap of 8px
    _DOT_R   = 4
    _DOT_GAP = 8

    _ALPHA   = 0.95
    # Inter 14px weight-500 maps to Segoe UI 10pt on Windows (96dpi)
    _FONT    = ("Segoe UI", 10, "normal")

    # ---------------------------------------------------------------
    # Glassmorphism colors matching HTML index.html exactly
    # ---------------------------------------------------------------
    # Background base color from HTML
    _BG_BASE = "#1a1a1c"

    # Glass effect: rgba(255,255,255,0.04) on #1a1a1c
    _GLASS_BG_TOP = "#1f1f21"  # gradient top (slightly lighter)
    _GLASS_BG_BOTTOM = "#171718"  # gradient bottom (slightly darker)

    # Default border: rgba(255,255,255,0.08) on #1a1a1c
    _GLASS_BORDER_DEFAULT = "#2c2c2e"
    # Capture border: rgba(255,255,255,0.15)
    _GLASS_BORDER_CAPTURE = "#3c3c3e"

    # Inset shine: rgba(255,255,255,0.05)
    _SHINE_COLOR = "#252527"

    # Top highlight: rgba(255,255,255,0.1)
    _TOP_HIGHLIGHT = "#3a3a3c"

    # Per-tone colors — simple and clean glassmorphic, only text/dot color changes.
    COLORS = {
        "recording": {"bg_top": "#1f1f21", "bg_bottom": "#171718", "border": "#3c3c3e", "dot": "#ffffff", "fg": "#ffffff", "pulse": True, "glow": None},
        "working":   {"bg_top": "#1f1f21", "bg_bottom": "#171718", "border": "#3c3c3e", "dot": "#ffffff", "fg": "#ffffff", "pulse": False, "glow": None},
        "success":   {"bg_top": "#1f1f21", "bg_bottom": "#171718", "border": "#3c3c3e", "dot": "#ffffff", "fg": "#ffffff", "pulse": False, "glow": None},
        "warning":   {"bg_top": "#1f1f21", "bg_bottom": "#171718", "border": "#3c3c3e", "dot": "#ffffff", "fg": "#ffffff", "pulse": False, "glow": None},
        "error":     {"bg_top": "#1f1f21", "bg_bottom": "#171718", "border": "#3c3c3e", "dot": "#ffffff", "fg": "#ffffff", "pulse": False, "glow": None},
        "info":      {"bg_top": "#1f1f21", "bg_bottom": "#171718", "border": "#3c3c3e", "dot": "#ffffff", "fg": "#ffffff", "pulse": False, "glow": None},
        "capture":   {"bg_top": "#1f1f21", "bg_bottom": "#171718", "border": "#3c3c3e", "dot": "#ffffff", "fg": "#ffffff", "pulse": False, "glow": None},
    }

    # Acrylic tint (0xAARRGBB) — high transparency for true liquid glass fluid effect
    _ACRYLIC_TINT = {
        "recording": 0x60171719,
        "working":   0x60171719,
        "success":   0x60171719,
        "warning":   0x60171719,
        "error":     0x60171719,
        "info":      0x60171719,
        "capture":   0x60171719,
    }

    # Glow settings for ambient effect (similar to HTML .ambient-glow)
    _GLOW_RADIUS = 50
    _GLOW_OPACITY = 0.35

    # Pulse animation: alternates between two dot radii for recording tone
    _PULSE_INTERVAL_MS = 600
    _DOT_R_SMALL       = 3
    _DOT_R_LARGE       = 5

    def __init__(self):
        self._tk        = None
        self._tkfont    = None
        self._root      = None
        self._canvas    = None
        self._commands  = queue.Queue()
        self._hide_deadline  = None
        self._started   = False
        self._available = True
        self._current_tone  = "info"
        # Pulse state
        self._pulse_on      = True
        self._pulse_after_id = None
        self._current_text  = ""
        self._current_w     = 0
        self._current_h     = 0
        self._photo         = None  # prevent GC of PhotoImage

    def start(self):
        if self._started:
            return
        try:
            import tkinter as tk
            from tkinter import font as tkfont
            from PIL import Image, ImageDraw, ImageFont, ImageTk
        except Exception:
            self._available = False
            print("[SimpleSpeech] Floating indicator unavailable on this environment.")
            return

        self._tk     = tk
        self._tkfont = tkfont
        self._Image     = Image
        self._ImageDraw = ImageDraw
        self._ImageFont = ImageFont
        self._ImageTk   = ImageTk

        # Load font once (Segoe UI Semibold ≈ Inter 500)
        self._pil_font = None
        for fname in ("seguisb.ttf", "segoeui.ttf"):
            try:
                self._pil_font = ImageFont.truetype(fname, 13)
                break
            except Exception:
                continue
        if self._pil_font is None:
            self._pil_font = ImageFont.load_default()
        self._root   = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        try:
            self._root.attributes("-alpha", self._ALPHA)
        except Exception:
            pass
        self._root.configure(bg=self._TRANSPARENT_KEY)
        try:
            self._root.attributes("-transparentcolor", self._TRANSPARENT_KEY)
        except Exception:
            pass

        self._canvas = tk.Canvas(
            self._root, highlightthickness=0, bg=self._TRANSPARENT_KEY,
        )
        self._canvas.pack(fill="both", expand=True)

        self._apply_dwm_effects()
        self._apply_non_activating_style()
        self._started = True

    # ------------------------------------------------------------------
    # DWM / composition helpers
    # ------------------------------------------------------------------

    def _apply_dwm_effects(self):
        if os.name != "nt":
            return
        try:
            hwnd_parent = ctypes.windll.user32.GetParent(self._root.winfo_id())
            val = ctypes.c_int(2)  # DWMWCP_ROUND — Windows 11 rounded corners
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd_parent, 33, ctypes.byref(val), ctypes.sizeof(val),
            )
        except Exception:
            pass
        self._apply_acrylic_blur_win10()

    def _apply_acrylic_blur_win10(self, tone=None):
        if os.name != "nt":
            return
        try:
            hwnd = self._root.winfo_id()
            tint = self._ACRYLIC_TINT.get(tone or self._current_tone, 0xE0171719)

            class _ACCENT(ctypes.Structure):
                _fields_ = [("AccentState",   ctypes.c_uint),
                             ("AccentFlags",   ctypes.c_uint),
                             ("GradientColor", ctypes.c_uint),
                             ("AnimationId",   ctypes.c_uint)]

            class _WCAD(ctypes.Structure):
                _fields_ = [("Attribute",  ctypes.c_int),
                             ("Data",       ctypes.c_void_p),
                             ("SizeOfData", ctypes.c_size_t)]

            accent = _ACCENT()
            accent.AccentState   = 4      # ACCENT_ENABLE_ACRYLICBLURBEHIND
            accent.AccentFlags   = 0x20
            accent.GradientColor = tint

            wcad = _WCAD()
            wcad.Attribute  = 19          # WCA_ACCENT_POLICY
            wcad.SizeOfData = ctypes.sizeof(accent)
            wcad.Data       = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)

            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(wcad))
        except Exception:
            pass

    def _apply_non_activating_style(self):
        if os.name != "nt":
            return
        try:
            hwnd     = self._root.winfo_id()
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ex_style |= 0x08000000  # WS_EX_NOACTIVATE
            ex_style |= 0x00000080  # WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, ex_style)
        except Exception:
            pass

    def stop(self):
        if not self._started or not self._available:
            return
        try:
            self._root.destroy()
        except Exception:
            pass
        self._root       = None
        self._canvas     = None
        self._started    = False
        self._hide_deadline = None

    def show(self, text, tone="info", ttl=None):
        if not self._available or not self._started:
            return
        self._commands.put(("show", text, tone, ttl))

    def hide(self):
        if not self._available or not self._started:
            return
        self._commands.put(("hide",))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _pill(self, x1, y1, x2, y2, r, **kw):
        """Smooth pill shape — r is auto-capped at half the shorter side."""
        r = min(r, int((x2 - x1) / 2), int((y2 - y1) / 2))
        pts = [
            x1 + r, y1,     x2 - r, y1,
            x2,     y1,     x2,     y1 + r,
            x2,     y2 - r, x2,     y2,
            x2 - r, y2,     x1 + r, y2,
            x1,     y2,     x1,     y2 - r,
            x1,     y1 + r, x1,     y1,
        ]
        return self._canvas.create_polygon(pts, smooth=True, **kw)

    @staticmethod
    def _hex_to_rgb(hex_color):
        h = hex_color.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def _draw_frame(self, text, tone, pulse_on):
        """Render a complete frame using PIL for smooth anti-aliased glassmorphism."""
        style = self.COLORS.get(tone, self.COLORS["info"])

        # --- Measure text at native scale to avoid color key mixing ---
        scale = 1
        font_1x = self._pil_font
        tmp = self._Image.new("RGB", (1, 1))
        td = self._ImageDraw.Draw(tmp)
        bbox = td.textbbox((0, 0), text, font=font_1x)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        dot_d = self._DOT_R * 2
        content_w = dot_d + self._DOT_GAP + text_w
        w = content_w + self._PAD_X * 2
        h = text_h + self._PAD_Y * 2 + 6  # breathing room
        h = max(h, 30)

        # --- Create supersampled image ---
        sw, sh = w * scale, h * scale
        bg_rgb = self._hex_to_rgb(self._TRANSPARENT_KEY)
        img = self._Image.new("RGB", (sw, sh), bg_rgb)
        draw = self._ImageDraw.Draw(img)

        # Scaled font for supersampled rendering
        s_font = None
        for fname in ("seguisb.ttf", "segoeui.ttf"):
            try:
                s_font = self._ImageFont.truetype(fname, 13 * scale)
                break
            except Exception:
                continue
        if s_font is None:
            s_font = self._ImageFont.load_default()



        # --- Layer 3: Dot + Text (centered) ---
        s_dot_d = dot_d * scale
        s_gap = self._DOT_GAP * scale
        s_text_bbox = draw.textbbox((0, 0), text, font=s_font)
        s_text_w = s_text_bbox[2] - s_text_bbox[0]
        s_content_w = s_dot_d + s_gap + s_text_w

        cy = sh // 2
        group_left = max(self._PAD_X * scale, (sw - s_content_w) // 2)

        # Dot
        dot_r = self._DOT_R * scale
        if style.get("pulse"):
            dot_r = (self._DOT_R_LARGE if pulse_on else self._DOT_R_SMALL) * scale

        dot_cx = group_left + self._DOT_R * scale
        dot_color = self._hex_to_rgb(style["dot"])
        if style.get("pulse") and not pulse_on:
            dot_color = self._hex_to_rgb("#555555")

        draw.ellipse(
            [dot_cx - dot_r, cy - dot_r, dot_cx + dot_r, cy + dot_r],
            fill=dot_color,
        )

        # Text
        text_x = group_left + s_dot_d + s_gap
        text_y = cy - (s_text_bbox[3] - s_text_bbox[1]) // 2 - s_text_bbox[1]
        text_color = self._hex_to_rgb(style["fg"])
        draw.text((text_x, text_y), text, fill=text_color, font=s_font)

        # --- Display on canvas ---
        self._photo = self._ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        self._canvas.configure(width=w, height=h)
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)

        return w, h

    def _apply_show(self, text, tone, ttl):
        self._current_tone = tone
        self._current_text = text
        self._apply_acrylic_blur_win10(tone=tone)

        # Cancel any existing pulse callback
        if self._pulse_after_id is not None:
            try:
                self._root.after_cancel(self._pulse_after_id)
            except Exception:
                pass
            self._pulse_after_id = None

        self._pulse_on = True
        w, h = self._draw_frame(text, tone, self._pulse_on)
        self._current_w, self._current_h = w, h

        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()
        x = max(0, (screen_w - w) // 2)
        y = max(20, int(screen_h * 0.08))
        self._root.geometry(f"{w}x{h}+{x}+{y}")

        # --- Liquid Glass Native Os Window ---
        # We rely on DWM (Desktop Window Manager) to apply smooth rounded corners
        # and native glass border (handled in _apply_dwm_effects).

        self._root.deiconify()
        try:
            self._root.attributes("-topmost", True)
        except Exception:
            pass

        # Start pulse loop if needed
        if self.COLORS.get(tone, {}).get("pulse"):
            self._schedule_pulse()

        if ttl is not None and ttl > 0:
            self._hide_deadline = time.time() + ttl
        else:
            self._hide_deadline = None

    def _schedule_pulse(self):
        """Schedule next pulse frame using tkinter after()."""
        if not self._started or not self._available:
            return
        if not self.COLORS.get(self._current_tone, {}).get("pulse"):
            return
        if self._hide_deadline is not None and time.time() >= self._hide_deadline:
            return
        self._pulse_on = not self._pulse_on
        self._draw_frame(self._current_text, self._current_tone, self._pulse_on)
        self._pulse_after_id = self._root.after(
            self._PULSE_INTERVAL_MS, self._schedule_pulse,
        )

    def _apply_hide(self):
        self._hide_deadline = None
        # Stop any running pulse animation
        if self._pulse_after_id is not None:
            try:
                self._root.after_cancel(self._pulse_after_id)
            except Exception:
                pass
            self._pulse_after_id = None
        self._root.withdraw()

    def process_events(self):
        if not self._available or not self._started:
            return

        while True:
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                break

            action = cmd[0]
            if action == "show":
                _, text, tone, ttl = cmd
                self._apply_show(text, tone, ttl)
            elif action == "hide":
                self._apply_hide()

        if self._hide_deadline is not None and time.time() >= self._hide_deadline:
            self._apply_hide()

        try:
            self._root.update_idletasks()
            self._root.update()
        except self._tk.TclError:
            self._available = False
            self._started = False


class HotkeyAudioRecorder:
    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._lock = threading.Lock()
        self._stream = None
        self._chunks = []

    def _callback(self, indata, _frames, _time_info, _status):
        with self._lock:
            if self._stream is not None:
                self._chunks.append(indata.copy())

    def start(self):
        with self._lock:
            if self._stream is not None:
                return False
            self._chunks = []
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
            return True

    def stop_and_save(self):
        with self._lock:
            stream = self._stream
            self._stream = None
        if stream is None:
            raise RuntimeError("No active recording.")

        stream.stop()
        stream.close()

        with self._lock:
            chunks = self._chunks
            self._chunks = []

        if not chunks:
            raise RuntimeError("No audio captured.")

        audio = np.concatenate(chunks, axis=0)
        filename = recordings_dir() / f"recording-{uuid.uuid4().hex}.wav"
        write(str(filename), self.sample_rate, audio)
        duration = audio.shape[0] / self.sample_rate
        return str(filename), duration

    def abort(self):
        with self._lock:
            stream = self._stream
            self._stream = None
            self._chunks = []
        if stream is None:
            return
        stream.stop()
        stream.close()


class HotkeyDictationService:
    def __init__(self, transcriber, refiner, indicator=None):
        self._transcriber = transcriber
        self._refiner = refiner
        self._indicator = indicator
        self._recorder = HotkeyAudioRecorder()
        self._paste_controller = keyboard.Controller()

        self._state_lock = threading.Lock()
        self._alt_down = set()
        self._shift_down = set()
        self._recording = False
        self._refine_requested = False
        self._alt_started_at = None
        self._ignore_alt_cycle = False
        self._paste_target_hwnd = None

        self._jobs = queue.Queue()
        self._jobs_lock = threading.Lock()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._listener = None
        self._running = False

    def start(self):
        self._running = True
        self._worker.start()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False,
        )
        self._listener.start()

    def stop(self):
        self._running = False
        if self._listener is not None:
            self._listener.stop()
        self._recorder.abort()
        if self._indicator is not None:
            self._indicator.hide()
        with self._jobs_lock:
            self._jobs.put(None)
        self._worker.join(timeout=5)

    def _on_press(self, key):
        with self._state_lock:
            if key in ALT_KEYS:
                if not self._alt_down and not self._recording:
                    self._alt_started_at = time.monotonic()
                    self._ignore_alt_cycle = False
                self._alt_down.add(key)
            if key in SHIFT_KEYS:
                self._shift_down.add(key)

            if self._recording and self._shift_down:
                self._refine_requested = True

            # If Alt is being used with any non-modifier key, ignore this Alt cycle.
            if self._alt_down and not self._recording:
                if key not in ALT_KEYS and key not in SHIFT_KEYS:
                    self._ignore_alt_cycle = True

    def _on_release(self, key):
        should_stop_recording = False
        mode = "raw"
        target_hwnd = None

        with self._state_lock:
            if key in ALT_KEYS:
                self._alt_down.discard(key)
            if key in SHIFT_KEYS:
                self._shift_down.discard(key)

            if self._recording and not self._alt_down:
                should_stop_recording = True
                mode = "refined" if self._refine_requested else "raw"
                target_hwnd = self._paste_target_hwnd
                self._recording = False
                self._refine_requested = False
                self._paste_target_hwnd = None
            elif not self._recording and not self._alt_down:
                self._alt_started_at = None
                self._ignore_alt_cycle = False
                self._paste_target_hwnd = None

        if not should_stop_recording:
            return

        try:
            audio_path, audio_len = self._recorder.stop_and_save()
            enqueued = self._enqueue_job(audio_path, mode, target_hwnd)
            if enqueued:
                print(f"[SimpleSpeech] Captured {audio_len:.2f}s. Processing ({mode})...")
                if self._indicator is not None:
                    self._indicator.show("Transcribing...", tone="working")
        except Exception as exc:
            print(f"[SimpleSpeech] Could not stop recording: {exc}")
            if self._indicator is not None:
                self._indicator.show("Capture failed", tone="error", ttl=2.0)

    def _enqueue_job(self, audio_path, mode, target_hwnd):
        dropped = 0
        enqueue_ok = True
        with self._jobs_lock:
            if not self._running:
                enqueue_ok = False
            elif KEEP_ONLY_LATEST_PENDING_JOB:
                while True:
                    try:
                        pending = self._jobs.get_nowait()
                    except queue.Empty:
                        break

                    self._jobs.task_done()
                    if pending is None:
                        # Stop request already queued: preserve it and skip new work.
                        self._jobs.put(None)
                        enqueue_ok = False
                        break

                    stale_audio_path = pending[0]
                    cleanup_audio_file(stale_audio_path)
                    dropped += 1

            if enqueue_ok:
                self._jobs.put((audio_path, mode, target_hwnd))

        if not enqueue_ok:
            cleanup_audio_file(audio_path)
            return False

        if dropped:
            print(
                f"[SimpleSpeech] Dropped {dropped} stale pending recording(s); "
                "kept the latest."
            )
        return True

    def tick(self):
        global APP_PAUSED
        if APP_PAUSED:
            return
        should_start_recording = False

        with self._state_lock:
            if self._recording:
                return
            if not self._alt_down:
                return
            if self._ignore_alt_cycle:
                return
            if self._alt_started_at is None:
                self._alt_started_at = time.monotonic()
                return
            if time.monotonic() - self._alt_started_at < ALT_HOLD_TRIGGER_S:
                return

            self._recording = True
            self._refine_requested = bool(self._shift_down)
            self._paste_target_hwnd = get_foreground_window_handle()
            should_start_recording = True

        if not should_start_recording:
            return

        try:
            started = self._recorder.start()
            if not started:
                with self._state_lock:
                    self._recording = False
                return
            play_asset_sound("start")
            mode_label = "refined" if self._refine_requested else "raw"
            print(f"\n[SimpleSpeech] Recording started ({mode_label}). Release Alt to stop.")
            if self._indicator is not None:
                self._indicator.show(f"Recording ({mode_label})", tone="recording")
        except Exception as exc:
            with self._state_lock:
                self._recording = False
                self._refine_requested = False
                self._alt_started_at = None
            print(f"[SimpleSpeech] Could not start recording: {exc}")
            if self._indicator is not None:
                self._indicator.show("Mic error", tone="error", ttl=2.0)

    def _worker_loop(self):
        while True:
            job = self._jobs.get()
            if job is None:
                self._jobs.task_done()
                break

            audio_path, mode, target_hwnd = job
            try:
                raw, duration = self._transcriber.transcribe(audio_path)


                refined_text = raw
                refinement_available = True
                if mode == "refined":
                    if self._indicator is not None:
                        self._indicator.show("Refining...", tone="working")
                    refined_text, refinement_available = self._refiner.refine(raw)

                if PRINT_HOTKEY_DEBUG_TRANSCRIPTS:
                    print("\n--- HOTKEY RAW ---")
                    print(raw)
                    print("\n--- HOTKEY REFINED ---")
                    print(refined_text)
                    print("--------------------")

                final_text = raw if mode == "raw" else refined_text

                pasted = paste_text_at_cursor(
                    final_text,
                    self._paste_controller,
                    target_hwnd=target_hwnd,
                )
                if pasted:
                    play_asset_sound("end")
                    print(
                        f"[SimpleSpeech] Pasted {mode} transcript "
                        f"({len(final_text)} chars, transcribe {duration:.2f}s)."
                    )
                    if self._indicator is not None:
                        message = (
                            "Ollama unavailable — pasted raw text"
                            if mode == "refined" and not refinement_available
                            else f"Pasted ({mode})"
                        )
                        self._indicator.show(
                            message,
                            tone="success",
                            ttl=2.0 if not refinement_available else INDICATOR_DEFAULT_TTL_S,
                        )
                else:
                    print("[SimpleSpeech] Transcript was empty. Nothing pasted.")
                    if self._indicator is not None:
                        self._indicator.show(
                            "No speech detected",
                            tone="warning",
                            ttl=INDICATOR_DEFAULT_TTL_S,
                        )
            except Exception as exc:
                logger.exception("Processing failed")
                print(f"[SimpleSpeech] Processing failed: {exc}")
                if self._indicator is not None:
                    self._indicator.show("Processing error", tone="error", ttl=2.0)
            finally:
                cleanup_audio_file(audio_path)
                self._jobs.task_done()


def setup_tray_icon():
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("[SimpleSpeech] pystray or PIL not found. No system tray icon will be shown.")
        return None

    def on_toggle_pause(icon, item):
        global APP_PAUSED
        APP_PAUSED = not APP_PAUSED
        icon.update_menu()

    def on_quit(icon, item):
        global APP_RUNNING
        APP_RUNNING = False
        icon.stop()

    def on_open_logs(icon, item):
        try:
            os.startfile(str(recordings_dir().parent / "simplespeech.log"))
        except OSError:
            logger.exception("Could not open log file")

    def get_pause_text(item):
        return "Resume Dictation" if APP_PAUSED else "Pause Dictation"

    menu = pystray.Menu(
        pystray.MenuItem(get_pause_text, on_toggle_pause),
        pystray.MenuItem("Open Logs", on_open_logs),
        pystray.MenuItem("Quit", on_quit),
    )

    try:
        icon_path = os.path.join(_ASSET_DIR, "icon.png")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(_ASSET_DIR, "icon.ico")
        image = Image.open(icon_path)
    except Exception:
        image = Image.new('RGB', (64, 64), 'black')
        dc = ImageDraw.Draw(image)
        dc.rectangle((32, 0, 64, 32), fill='white')
        dc.rectangle((0, 32, 32, 64), fill='white')

    icon = pystray.Icon("SimpleSpeech", image, "SimpleSpeech", menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return icon


def run_hotkey_mode():
    global APP_RUNNING
    print("\n--- SimpleSpeech (Hotkey Core) ---")
    print(f"Hold Alt (~{ALT_HOLD_TRIGGER_S:.2f}s) = raw transcript paste")
    print(f"Hold Alt+Shift (~{ALT_HOLD_TRIGGER_S:.2f}s) = refined transcript paste")
    print("Works with left or right Alt/Shift. Press Ctrl+C to quit.\n")

    transcriber = Transcriber()
    refiner = Refiner()

    indicator = FloatingStatusIndicator()
    indicator.start()

    service = HotkeyDictationService(transcriber, refiner, indicator=indicator)
    service.start()

    icon = setup_tray_icon()

    try:
        while APP_RUNNING:
            service.tick()
            indicator.process_events()
            time.sleep(INDICATOR_POLL_MS / 1000.0)
    except KeyboardInterrupt:
        print("\n[SimpleSpeech] Exiting.")
    finally:
        APP_RUNNING = False
        service.stop()
        indicator.stop()
        if icon:
            icon.stop()


def main():
    run_hotkey_mode()


if __name__ == "__main__":
    main()
