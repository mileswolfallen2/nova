#!/usr/bin/env python3
# NOVA UI — graphical wrapper around jarvis.py
# Run: python ui.py
# All logic (voice, Ollama, commands, TTS, memory) lives in jarvis.py.

import tkinter as tk
import threading
import math
import random
import json
import os
import sys
import queue
import subprocess
import wave
import struct

try:
    import psutil
except ImportError:
    psutil = None

from datetime import datetime

# Import jarvis as the single backend (--ui skips CLI main loop)
if "--ui" not in sys.argv:
    sys.argv.insert(1, "--ui")

try:
    import jarvis
except Exception as _import_err:
    print(f"[UI] Could not import jarvis.py: {_import_err}")
    sys.exit(1)

_SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")

# UI thread events: (event, *payload) from jarvis.ui_emit or voice thread
ui_events = queue.Queue()


def _jarvis_to_ui(event, *payload):
    ui_events.put((event,) + payload)


jarvis.set_ui_emit(_jarvis_to_ui)


# ---------------------------------------------------------------------------
# Theme — Iron Man JARVIS holographic HUD
# ---------------------------------------------------------------------------

class Theme:
    BG = "#010508"
    BG_GRID = "#061420"
    PANEL = "#040C14"
    PANEL_EDGE = "#1A4A6E"
    ACCENT = "#4FC3F7"       # holographic cyan
    ACCENT_BRIGHT = "#8FE8FF"
    ACCENT_DIM = "#1E5A7A"
    GOLD = "#D4AF37"         # Stark gold accent
    GOLD_DIM = "#8A7028"
    SUCCESS = "#5CE1FF"
    DANGER = "#FF5566"
    WARN = "#E8C547"
    TEXT = "#C5E8F7"
    TEXT_DIM = "#5A8AA8"
    GLOW = "#6DD5FA"
    CORE = "#E8F8FF"         # arc reactor white
    USER_BUBBLE = "#061018"
    NOVA_BUBBLE = "#040E18"
    CMD_BG = "#081420"
    SCAN = "#0E3050"
    BTN_BG = "#0A1A2A"
    BTN_FG = "#8FE8FF"
    BTN_BORDER = "#2A6A8F"
    BTN_ACTIVE_BG = "#1A4A6E"
    BTN_ACTIVE_FG = "#E8F8FF"
    BTN_DISABLED_BG = "#061018"
    BTN_DISABLED_FG = "#3A5A6A"


# Typography (JARVIS: clean sans + mono data readouts)
FONT_TITLE = ("Helvetica Neue", 20, "normal")
FONT_SUB = ("Helvetica Neue", 9)
FONT_HUD = ("Helvetica Neue", 10)
FONT_HUD_BOLD = ("Helvetica Neue", 10, "bold")
FONT_HUD_SM = ("Helvetica Neue", 8)
FONT_DATA = ("Courier New", 10)
FONT_BODY = ("Helvetica Neue", 11)
FONT_CHAT_LABEL = ("Helvetica Neue", 7, "bold")


def apply_hud_widget_defaults(root):
    """Override macOS default white widgets."""
    root.option_add("*Button.Background", Theme.BTN_BG)
    root.option_add("*Button.Foreground", Theme.BTN_FG)
    root.option_add("*Button.activeBackground", Theme.BTN_ACTIVE_BG)
    root.option_add("*Button.activeForeground", Theme.BTN_ACTIVE_FG)
    root.option_add("*Button.highlightBackground", Theme.BTN_BORDER)
    root.option_add("*Button.highlightColor", Theme.ACCENT_BRIGHT)
    root.option_add("*Button.relief", "flat")
    root.option_add("*Button.borderWidth", 0)
    root.option_add("*Entry.Background", Theme.PANEL)
    root.option_add("*Entry.Foreground", Theme.TEXT)
    root.option_add("*Listbox.Background", Theme.PANEL)
    root.option_add("*Listbox.Foreground", Theme.TEXT)
    root.option_add("*Listbox.selectBackground", Theme.ACCENT_DIM)
    root.option_add("*Listbox.selectForeground", Theme.CORE)


class HudButton(tk.Button):
    """HUD-styled button (avoids default white macOS chrome)."""

    def __init__(self, parent, text="", command=None, accent=False, **kw):
        style = dict(
            font=kw.pop("font", FONT_HUD_SM),
            bg=Theme.ACCENT_DIM if accent else Theme.BTN_BG,
            fg=Theme.CORE if accent else Theme.BTN_FG,
            activebackground=Theme.ACCENT if accent else Theme.BTN_ACTIVE_BG,
            activeforeground=Theme.BG if accent else Theme.BTN_ACTIVE_FG,
            disabledforeground=Theme.BTN_DISABLED_FG,
            highlightthickness=1,
            highlightbackground=Theme.GOLD_DIM if accent else Theme.BTN_BORDER,
            highlightcolor=Theme.GOLD if accent else Theme.ACCENT_BRIGHT,
            relief="flat",
            borderwidth=0,
            padx=kw.pop("padx", 14),
            pady=kw.pop("pady", 7),
            cursor="hand2",
            text=text,
            command=command,
        )
        style.update(kw)
        super().__init__(parent, **style)


# ---------------------------------------------------------------------------
# Sound effects
# ---------------------------------------------------------------------------

class SoundManager:
    MAC_FALLBACKS = {
        "startup": "/System/Library/Sounds/Hero.aiff",
        "listen": "/System/Library/Sounds/Pop.aiff",
        "think": "/System/Library/Sounds/Tink.aiff",
        "success": "/System/Library/Sounds/Glass.aiff",
        "error": "/System/Library/Sounds/Basso.aiff",
    }

    def __init__(self):
        os.makedirs(_SOUNDS_DIR, exist_ok=True)
        self._ensure_placeholders()

    def _ensure_placeholders(self):
        specs = {
            "startup": (880, 0.12),
            "listen": (660, 0.06),
            "think": (440, 0.04),
            "success": (990, 0.1),
            "error": (220, 0.15),
        }
        for name, (freq, dur) in specs.items():
            path = os.path.join(_SOUNDS_DIR, f"{name}.wav")
            if not os.path.exists(path):
                self._write_beep(path, freq, dur)

    @staticmethod
    def _write_beep(path, freq, duration, rate=22050):
        n = int(rate * duration)
        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            for i in range(n):
                t = i / rate
                env = 1.0 - (i / n) ** 0.5
                val = int(16000 * env * math.sin(2 * math.pi * freq * t))
                wf.writeframes(struct.pack("<h", val))

    def play(self, name):
        path = os.path.join(_SOUNDS_DIR, f"{name}.wav")
        if os.path.exists(path):
            subprocess.Popen(
                ["afplay", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        fb = self.MAC_FALLBACKS.get(name)
        if fb and os.path.exists(fb):
            subprocess.Popen(
                ["afplay", fb],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


sounds = SoundManager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def lerp_color(c1, c2, t):
    r1, g1, b1 = hex_rgb(c1)
    r2, g2, b2 = hex_rgb(c2)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def blend_alpha(fg, bg, alpha):
    fr, fg_c, fb = hex_rgb(fg)
    br, bg_c, bb = hex_rgb(bg)
    r = int(br + (fr - br) * alpha)
    g = int(bg_c + (fg_c - bg_c) * alpha)
    b = int(bb + (fb - bb) * alpha)
    return f"#{r:02x}{g:02x}{b:02x}"


def round_rect_points(x1, y1, x2, y2, r):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def draw_hud_corners(canvas, x1, y1, x2, y2, color, length=14, width=2, tag="hud"):
    """Corner bracket chrome (Iron Man HUD)."""
    L = length
    for ax, ay, dx, dy in (
        (x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1),
    ):
        canvas.create_line(ax, ay, ax + dx * L, ay, fill=color, width=width, tags=tag)
        canvas.create_line(ax, ay, ax, ay + dy * L, fill=color, width=width, tags=tag)


class HudBackdrop(tk.Canvas):
    """Animated grid + scan line behind the interface."""

    def __init__(self, parent):
        super().__init__(parent, bg=Theme.BG, highlightthickness=0, bd=0)
        self._tick = 0
        self.bind("<Configure>", lambda e: self._draw())
        self._animate()

    def _animate(self):
        self._tick += 1
        self._draw()
        self.after(50, self._animate)

    def _draw(self):
        self.delete("grid", "scan")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return
        step = 40
        for x in range(0, w, step):
            col = Theme.BG_GRID if x % (step * 2) else Theme.SCAN
            self.create_line(x, 0, x, h, fill=col, tags="grid")
        for y in range(0, h, step):
            col = Theme.BG_GRID if y % (step * 2) else Theme.SCAN
            self.create_line(0, y, w, y, fill=col, tags="grid")
        sweep = (self._tick * 4) % (h + 80) - 40
        self.create_line(0, sweep, w, sweep, fill=Theme.ACCENT_DIM, tags="scan")
        self.create_line(0, sweep + 2, w, sweep + 2, fill=Theme.SCAN, tags="scan")
        # Vignette bars top/bottom
        for i in range(6):
            a = 0.15 - i * 0.02
            c = blend_alpha(Theme.BG, Theme.ACCENT_DIM, max(0, a))
            self.create_rectangle(0, i * 3, w, i * 3 + 2, fill=c, outline="", tags="grid")
            self.create_rectangle(0, h - i * 3 - 2, w, h - i * 3, fill=c, outline="", tags="grid")


def process_user_input(text):
    """Delegate to jarvis.process_input (TTS + routing handled there)."""
    try:
        sounds.play("think")
        jarvis.process_input(text)
        sounds.play("success")
    except Exception as e:
        ui_events.put(("error", str(e)))
        sounds.play("error")


# ---------------------------------------------------------------------------
# Glass panel (canvas rounded rect)
# ---------------------------------------------------------------------------


class HudPanel(tk.Canvas):
    """HUD panel with corner brackets and holographic border."""

    def __init__(self, parent, width=None, height=None, glow=False, **kw):
        super().__init__(
            parent,
            bg=Theme.BG,
            highlightthickness=0,
            bd=0,
            width=width or 1,
            height=height or 1,
            **kw,
        )
        self._glow = glow
        self._panel_w = width
        self._panel_h = height
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4 or h < 4:
            return
        pad = 6
        fill = blend_alpha(Theme.PANEL, Theme.BG, 0.92)
        edge = Theme.ACCENT if self._glow else Theme.PANEL_EDGE
        self.create_rectangle(pad, pad, w - pad, h - pad, fill=fill, outline=edge, width=1)
        draw_hud_corners(self, pad, pad, w - pad, h - pad, Theme.ACCENT if self._glow else Theme.GOLD_DIM, length=16)
        if self._glow:
            draw_hud_corners(self, pad + 2, pad + 2, w - pad - 2, h - pad - 2, Theme.GLOW, length=10, width=1)
        # Top accent tick
        cx = w / 2
        self.create_line(cx - 30, pad, cx + 30, pad, fill=Theme.ACCENT, width=1)
        self.create_line(cx, pad - 3, cx, pad + 3, fill=Theme.GOLD, width=1)


# ---------------------------------------------------------------------------
# Scrollable chat (message cards)
# ---------------------------------------------------------------------------


class ChatScrollArea(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=Theme.BG)
        self._cards = []

        head = tk.Frame(self, bg=Theme.BG)
        head.pack(fill="x", pady=(0, 6))
        tk.Label(
            head, text="◢ COMMS CHANNEL", font=FONT_CHAT_LABEL,
            fg=Theme.GOLD, bg=Theme.BG,
        ).pack(side="left")
        tk.Label(
            head, text="SECURE LINK", font=FONT_HUD_SM,
            fg=Theme.ACCENT_DIM, bg=Theme.BG,
        ).pack(side="right")

        border = tk.Frame(self, bg=Theme.ACCENT, padx=1, pady=1)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg=Theme.PANEL)
        inner.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(
            inner, bg=Theme.PANEL, highlightthickness=0, bd=0
        )
        self._scrollbar = tk.Scrollbar(
            inner,
            orient="vertical",
            command=self._canvas.yview,
            bg=Theme.BTN_BG,
            troughcolor=Theme.PANEL,
            activebackground=Theme.ACCENT_DIM,
            highlightthickness=0,
            relief="flat",
            width=10,
        )
        self._frame = tk.Frame(self._canvas, bg=Theme.PANEL)

        self._frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._win = self._canvas.create_window((0, 0), window=self._frame, anchor="nw")

        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self._canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._win, width=event.width)

    def _on_mousewheel(self, event):
        if self._canvas.winfo_containing(event.x_root, event.y_root) == self._canvas:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")

    def _scroll_bottom(self):
        self._canvas.update_idletasks()
        self._canvas.yview_moveto(1.0)

    def _add_card(self, card):
        card.pack(fill="x", padx=10, pady=6)
        self._cards.append(card)
        self._scroll_bottom()

    def add_user(self, text):
        card = MessageCard(self._frame, "you", text)
        self._add_card(card)

    def add_nova(self, text):
        card = MessageCard(self._frame, "nova", text)
        self._add_card(card)
        return card

    def add_system(self, text):
        card = MessageCard(self._frame, "sys", text)
        self._add_card(card)

    def add_command(self, cmd, status="RUNNING", detail=""):
        card = CommandCard(self._frame, cmd, status, detail)
        self._add_card(card)
        return card


class MessageCard(tk.Frame):
    def __init__(self, parent, role, text):
        super().__init__(parent, bg=Theme.PANEL)
        align = "e" if role == "you" else "w"
        if role == "you":
            fg_title, label, bg, border = Theme.GOLD, "OPERATOR", Theme.USER_BUBBLE, Theme.GOLD_DIM
        elif role == "nova":
            fg_title, label, bg, border = Theme.ACCENT_BRIGHT, "NOVA", Theme.NOVA_BUBBLE, Theme.ACCENT
        else:
            fg_title, label, bg, border = Theme.TEXT_DIM, "SYSTEM", Theme.PANEL, Theme.PANEL_EDGE

        row = tk.Frame(self, bg=Theme.PANEL)
        row.pack(anchor=align, fill="x")

        shell = tk.Frame(row, bg=border, padx=1, pady=1)
        shell.pack(anchor=align)
        bubble = tk.Frame(shell, bg=bg, padx=14, pady=10)
        bubble.pack()

        if role != "sys":
            tk.Label(
                bubble, text=f"▸ {label}", font=FONT_CHAT_LABEL,
                fg=fg_title, bg=bg,
            ).pack(anchor="w")

        self._body = tk.Label(
            bubble, text=text, font=FONT_BODY, fg=Theme.TEXT, bg=bg,
            wraplength=440, justify="left", anchor="w",
        )
        self._body.pack(anchor="w", pady=(4, 0))
        tk.Frame(bubble, bg=fg_title, height=1).pack(fill="x", pady=(8, 0))

    def set_text(self, text):
        self._body.config(text=text)


class CommandCard(tk.Frame):
    def __init__(self, parent, cmd, status, detail=""):
        super().__init__(parent, bg=Theme.PANEL)
        shell = tk.Frame(self, bg=Theme.GOLD, padx=1, pady=1)
        shell.pack(fill="x")
        box = tk.Frame(shell, bg=Theme.CMD_BG, padx=14, pady=10)
        box.pack(fill="x")

        tk.Label(
            box, text="◈ PROTOCOL EXECUTION", font=FONT_CHAT_LABEL,
            fg=Theme.GOLD, bg=Theme.CMD_BG,
        ).pack(anchor="w")
        self._cmd_lbl = tk.Label(
            box, text=cmd, font=FONT_HUD_BOLD,
            fg=Theme.ACCENT_BRIGHT, bg=Theme.CMD_BG,
        )
        self._cmd_lbl.pack(anchor="w", pady=(4, 0))
        self._status_lbl = tk.Label(
            box, text=f"▸ {status}", font=FONT_DATA,
            fg=Theme.TEXT_DIM, bg=Theme.CMD_BG,
        )
        self._status_lbl.pack(anchor="w", pady=(4, 0))
        if detail:
            tk.Label(
                box, text=detail, font=FONT_HUD_SM, fg=Theme.TEXT,
                bg=Theme.CMD_BG, wraplength=400, justify="left",
            ).pack(anchor="w", pady=(4, 0))

    def set_status(self, status, ok=False):
        color = Theme.SUCCESS if ok else Theme.GOLD
        sym = "COMPLETE" if ok else status
        self._status_lbl.config(text=f"▸ {sym}", fg=color)


# ---------------------------------------------------------------------------
# JARVIS arc-reactor core (holographic sphere)
# ---------------------------------------------------------------------------


class JarvisCore(tk.Canvas):
    """Arc-reactor style hologram — wireframe sphere, rotating rings, sweep."""

    def __init__(self, parent, size=360):
        super().__init__(
            parent, width=size, height=size,
            bg=Theme.BG, highlightthickness=0,
        )
        self._size = size
        self._tick = 0
        self._state = "idle"
        self._audio_level = 0.0
        self._wake_pulse = 0.0

    def set_state(self, state):
        self._state = state

    def set_audio_level(self, level):
        self._audio_level = max(0.0, min(1.0, level))

    def pulse_wake(self):
        self._wake_pulse = 1.0

    def animate(self):
        self._tick += 1
        if self._wake_pulse > 0:
            self._wake_pulse = max(0, self._wake_pulse - 0.035)
        self._draw()
        self.after(33, self.animate)

    def _draw(self):
        self.delete("all")
        cx = cy = self._size / 2
        R = self._size * 0.32
        t = self._tick * 0.04
        state = self._state
        pulse = 0.12 * math.sin(t * 2.5) + self._audio_level * 0.4

        accent = Theme.ACCENT
        if state == "speaking":
            accent = Theme.SUCCESS
        elif state == "thinking":
            accent = Theme.ACCENT_BRIGHT

        # Outer HUD ring ticks
        for i in range(36):
            ang = math.radians(i * 10 + t * 20)
            r1, r2 = R + 38, R + 44 + pulse * 6
            x1, y1 = cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)
            x2, y2 = cx + r2 * math.cos(ang), cy + r2 * math.sin(ang)
            col = Theme.GOLD if i % 9 == 0 else Theme.ACCENT_DIM
            self.create_line(x1, y1, x2, y2, fill=col, width=1 if i % 9 else 2)

        # Rotating dashed rings (arc reactor tiers)
        for ri, (speed, offset, w) in enumerate(((0.6, 0, 1), (-0.9, 15, 2), (1.2, 30, 1))):
            rr = R + 14 + ri * 12 + pulse * 8
            start = (t * 40 * speed + offset) % 360
            col = lerp_color(Theme.BG, accent, 0.35 + ri * 0.2)
            for seg in range(6):
                self.create_arc(
                    cx - rr, cy - rr, cx + rr, cy + rr,
                    start=start + seg * 60, extent=28,
                    outline=col, width=w, style="arc",
                )

        # Wireframe hologram sphere
        n_lat, n_lon = 10, 16
        tilt = 0.35
        for li in range(n_lat):
            lat = -math.pi / 2 + math.pi * li / (n_lat - 1)
            pts = []
            for lj in range(n_lon + 1):
                lon = 2 * math.pi * lj / n_lon + t * 0.2
                x = math.cos(lat) * math.cos(lon)
                y = math.sin(lat)
                z = math.cos(lat) * math.sin(lon)
                y2 = y * math.cos(tilt) - z * math.sin(tilt)
                z2 = y * math.sin(tilt) + z * math.cos(tilt)
                if z2 < -0.2:
                    continue
                px = cx + x * R * (1 + pulse * 0.1)
                py = cy + y2 * R * (1 + pulse * 0.1)
                pts.extend([px, py])
            if len(pts) >= 4:
                bright = 0.25 + 0.5 * (1 - abs(lat) / (math.pi / 2))
                col = lerp_color(Theme.BG, accent, bright)
                self.create_line(*pts, fill=col, width=1, smooth=True)

        for lj in range(n_lon):
            lon = 2 * math.pi * lj / n_lon + t * 0.15
            pts = []
            for li in range(n_lat):
                lat = -math.pi / 2 + math.pi * li / (n_lat - 1)
                x = math.cos(lat) * math.cos(lon)
                y = math.sin(lat)
                z = math.cos(lat) * math.sin(lon)
                y2 = y * math.cos(tilt) - z * math.sin(tilt)
                z2 = y * math.sin(tilt) + z * math.cos(tilt)
                if z2 < -0.15:
                    continue
                pts.extend([cx + x * R, cy + y2 * R])
            if len(pts) >= 4:
                self.create_line(*pts, fill=Theme.ACCENT_DIM, width=1, smooth=True)

        # Rotating radar sweep
        sweep_ang = math.radians(t * 80)
        sx = cx + R * 1.1 * math.cos(sweep_ang)
        sy = cy + R * 1.1 * math.sin(sweep_ang)
        self.create_line(cx, cy, sx, sy, fill=lerp_color(Theme.BG, accent, 0.5), width=1)
        self.create_arc(
            cx - R * 1.15, cy - R * 1.15, cx + R * 1.15, cy + R * 1.15,
            start=math.degrees(sweep_ang) - 25, extent=50,
            fill=blend_alpha(accent, Theme.BG, 0.08), outline="",
        )

        # Arc reactor core
        core_r = R * (0.22 + 0.04 * math.sin(t * 4) + pulse * 0.05)
        for i in range(10, 0, -1):
            cr = core_r * (i / 10)
            col = lerp_color(Theme.BG, Theme.CORE if i > 6 else accent, (10 - i) / 12)
            self.create_oval(cx - cr, cy - cr, cx + cr, cy + cr, fill=col, outline="")
        self.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=Theme.CORE, outline=Theme.ACCENT_BRIGHT)

        # Hex ring around core
        hex_r = core_r * 1.35
        hex_pts = []
        for i in range(6):
            a = math.radians(60 * i + t * 30)
            hex_pts.extend([cx + hex_r * math.cos(a), cy + hex_r * math.sin(a)])
        self.create_polygon(hex_pts, outline=Theme.GOLD, fill="", width=1)

        self._draw_voice_rings(cx, cy, R, t, accent)

        if self._wake_pulse > 0:
            wr = R + 50 + 30 * (1 - self._wake_pulse)
            self.create_oval(
                cx - wr, cy - wr, cx + wr, cy + wr,
                outline=Theme.ACCENT_BRIGHT, width=2,
            )

    def _draw_voice_rings(self, cx, cy, R, t, accent):
        state = self._state
        if state == "idle":
            self.create_oval(
                cx - R - 20, cy - R - 20, cx + R + 20, cy + R + 20,
                outline=Theme.PANEL_EDGE, width=1,
            )
            return
        if state == "listening":
            for i in range(4):
                ph = t * 3.5 - i * 0.7
                r = R + 22 + i * 8 + 5 * math.sin(ph)
                self.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    outline=lerp_color(Theme.BG, accent, 0.3 + 0.2 * math.sin(ph)),
                    width=2,
                )
        elif state == "thinking":
            for i in range(3):
                ang = t * 2.5 + i * (2 * math.pi / 3)
                self.create_line(
                    cx, cy,
                    cx + (R + 30) * math.cos(ang), cy + (R + 30) * math.sin(ang),
                    fill=Theme.GOLD, width=1,
                )
        elif state == "speaking":
            for i in range(6):
                wave = abs(math.sin(t * 5 + i))
                r = R + 18 + i * 4 + wave * 12
                self.create_oval(
                    cx - r, cy - r * 0.55, cx + r, cy + r * 0.55,
                    outline=lerp_color(Theme.BG, Theme.SUCCESS, 0.2 + wave * 0.6),
                    width=1,
                )


# ---------------------------------------------------------------------------
# Command palette & memory viewer
# ---------------------------------------------------------------------------


PALETTE_ACTIONS = [
    ("Open Discord", "open discord"),
    ("Open YouTube", "open youtube and play music"),
    ("Search Google", "search google for "),
    ("System Status", "what is my system status"),
    ("Weather", "what is the weather"),
    ("Memory Viewer", "__memory__"),
    ("Web Search", "search the web for "),
]


class CommandPalette(tk.Toplevel):
    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.on_select = on_select
        self.title("NOVA — Command Interface")
        self.configure(bg=Theme.BG)
        self.geometry("500x380")
        self.transient(parent)
        self.grab_set()

        tk.Label(
            self, text="PROTOCOL SELECTOR", font=FONT_HUD_BOLD,
            fg=Theme.GOLD, bg=Theme.BG,
        ).pack(pady=(16, 8))

        self._entry = tk.Entry(
            self, font=FONT_HUD, bg=Theme.PANEL, fg=Theme.TEXT,
            insertbackground=Theme.ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=Theme.ACCENT_DIM,
            highlightcolor=Theme.ACCENT,
        )
        self._entry.pack(fill="x", padx=20, ipady=8)
        self._entry.bind("<KeyRelease>", self._filter)
        self._entry.bind("<Return>", self._activate)
        self._entry.bind("<Escape>", lambda e: self.destroy())
        self._entry.focus_set()

        list_frame = tk.Frame(self, bg=Theme.ACCENT_DIM, padx=1, pady=1)
        list_frame.pack(fill="both", expand=True, padx=20, pady=8)
        self._list = tk.Listbox(
            list_frame, font=FONT_HUD, bg=Theme.PANEL, fg=Theme.TEXT,
            selectbackground=Theme.ACCENT_DIM, selectforeground=Theme.CORE,
            relief="flat", highlightthickness=0, bd=0,
            activestyle="none",
        )
        self._list.pack(fill="both", expand=True)
        self._list.bind("<Double-Button-1>", self._activate)
        self._items = list(PALETTE_ACTIONS)
        self._refresh()
        self.bind("<Escape>", lambda e: self.destroy())

        btn_row = tk.Frame(self, bg=Theme.BG)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        HudButton(btn_row, text="EXECUTE", accent=True, command=self._activate).pack(
            side="right", padx=(8, 0),
        )
        HudButton(btn_row, text="CLOSE", command=self.destroy).pack(side="right")

    def _refresh(self):
        q = self._entry.get().lower()
        self._list.delete(0, "end")
        self._filtered = []
        for label, action in self._items:
            if q in label.lower() or q in action.lower():
                self._list.insert("end", label)
                self._filtered.append((label, action))
        if self._filtered:
            self._list.selection_set(0)

    def _filter(self, _event=None):
        self._refresh()

    def _activate(self, _event=None):
        sel = self._list.curselection()
        if not sel and self._filtered:
            idx = 0
        elif sel:
            idx = sel[0]
        else:
            return
        label, action = self._filtered[idx]
        self.destroy()
        self.on_select(label, action)


class MemoryViewer(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("NOVA — Memory Core")
        self.configure(bg=Theme.BG)
        self.geometry("520x400")
        self.transient(parent)

        tk.Label(
            self, text="◈ LONG-TERM MEMORY BANK", font=FONT_HUD_BOLD,
            fg=Theme.GOLD, bg=Theme.BG,
        ).pack(pady=(16, 8))

        jarvis.load_memory()
        mems = jarvis.memory.get("memories", [])
        body = "Miles remembers:\n" if mems else "No memories stored yet.\n"
        if mems:
            body += "\n".join(f"  • {m}" for m in mems)
        body = "━" * 36 + "\n" + body + "\n" + "━" * 36

        text = tk.Text(
            self, font=FONT_DATA, bg=Theme.PANEL, fg=Theme.TEXT,
            relief="flat", wrap="word", padx=16, pady=12,
            insertbackground=Theme.ACCENT,
        )
        text.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        text.insert("1.0", body)
        text.config(state="disabled")
        HudButton(self, text="CLOSE", command=self.destroy).pack(pady=(0, 16))


# ---------------------------------------------------------------------------
# Voice — jarvis.listen_loop()
# ---------------------------------------------------------------------------


def voice_bridge_thread():
    try:
        ui_events.put(("voice_status", True))
        for utterance in jarvis.listen_loop():
            ui_events.put(("voice_input", utterance))
    except Exception as e:
        print(f"[UI Voice] {e}")
        ui_events.put(("voice_status", False))


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------


class NovaUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NOVA")
        self.root.configure(bg=Theme.BG)
        self.root.geometry("1200x820")
        self.root.minsize(960, 680)

        self._state = "idle"
        self._busy = False
        self._cmd_card = None
        self._voice_online = False
        self._chat_visible = False
        self._panel_visible = False

        apply_hud_widget_defaults(self.root)

        self._backdrop = HudBackdrop(self.root)
        self._backdrop.place(x=0, y=0, relwidth=1, relheight=1)

        self._shell = tk.Frame(self.root, bg=Theme.BG)
        self._shell.place(x=0, y=0, relwidth=1, relheight=1)

        self._build()
        self._bind_keys()
        self._orb.animate()
        self._poll_events()
        self._update_stats()
        self._tick_clock()

        sounds.play("startup")
        self.root.after(300, self._startup_check)

        threading.Thread(target=voice_bridge_thread, daemon=True).start()

    def _build(self):
        root = self._shell

        # Header
        header = tk.Frame(root, bg=Theme.BG, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_block = tk.Frame(header, bg=Theme.BG)
        title_block.pack(side="left", padx=24, pady=10)
        tk.Label(
            title_block, text="N O V A", font=FONT_TITLE,
            fg=Theme.ACCENT_BRIGHT, bg=Theme.BG,
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="Novel Operating Variability Assistant",
            font=FONT_HUD_SM, fg=Theme.GOLD_DIM, bg=Theme.BG,
        ).pack(anchor="w")

        self._wake_frame = tk.Frame(header, bg=Theme.BG)
        self._wake_frame.pack(side="left", padx=16)
        tk.Label(
            self._wake_frame, text="VOICE TRIGGER", font=FONT_HUD_SM,
            fg=Theme.TEXT_DIM, bg=Theme.BG,
        ).pack(side="left")
        self._wake_word_lbl = tk.Label(
            self._wake_frame, text='"NOVA"', font=FONT_HUD_BOLD,
            fg=Theme.GOLD, bg=Theme.BG,
        )
        self._wake_word_lbl.pack(side="left", padx=(6, 0))
        self._wake_indicator = tk.Canvas(
            self._wake_frame, width=12, height=12, bg=Theme.BG, highlightthickness=0,
        )
        self._wake_indicator.pack(side="left", padx=8)
        self._wake_dot = self._wake_indicator.create_oval(
            2, 2, 10, 10, fill=Theme.ACCENT_DIM, outline=Theme.ACCENT,
        )

        self._time_lbl = tk.Label(
            header, text="", font=FONT_DATA, fg=Theme.ACCENT, bg=Theme.BG,
        )
        self._time_lbl.pack(side="right", padx=20)
        self._state_hdr = tk.Label(
            header, text="STANDBY", font=FONT_HUD_BOLD,
            fg=Theme.TEXT_DIM, bg=Theme.BG,
        )
        self._state_hdr.pack(side="right", padx=8)

        tk.Frame(root, bg=Theme.ACCENT_DIM, height=1).pack(fill="x")

        # Arc reactor — fills window until Ctrl+T
        self._orb_sec = tk.Frame(root, bg=Theme.BG)
        self._orb_sec.pack(fill="both", expand=True)

        self._orb = JarvisCore(self._orb_sec, size=380)
        self._orb.pack(expand=True, pady=(8, 0))

        self._mode_lbl = tk.Label(
            self._orb_sec, text="◈ STANDBY", font=FONT_HUD,
            fg=Theme.TEXT_DIM, bg=Theme.BG,
        )
        self._mode_lbl.pack(pady=(0, 8))

        self._orb_hint = tk.Label(
            self._orb_sec,
            text="Ctrl+T  ·  open interface",
            font=FONT_HUD_SM,
            fg=Theme.TEXT_DIM,
            bg=Theme.BG,
        )
        self._orb_hint.pack(pady=(0, 16))

        self._gold_line = tk.Frame(root, bg=Theme.GOLD_DIM, height=1)

        lower = tk.Frame(root, bg=Theme.BG)
        self._lower = lower

        left = tk.Frame(lower, bg=Theme.BG, width=260)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        stats_wrap = HudPanel(left, width=236, height=300, glow=True)
        stats_wrap.pack(fill="x", padx=12, pady=12)

        self._stats_frame = tk.Frame(stats_wrap, bg=Theme.PANEL)
        stats_wrap.create_window(16, 28, window=self._stats_frame, anchor="nw")

        tk.Label(
            self._stats_frame, text="◈ SYSTEM DIAGNOSTICS", font=FONT_CHAT_LABEL,
            fg=Theme.GOLD, bg=Theme.PANEL,
        ).pack(anchor="w", pady=(0, 8))
        self._stat_labels = {}
        for key in ("CPU", "RAM", "GPU", "TEMP", "OLLAMA", "VOICE", "MEMORY"):
            row = tk.Frame(self._stats_frame, bg=Theme.PANEL)
            row.pack(fill="x", pady=3)
            tk.Label(
                row, text=f"{key}", font=FONT_HUD_SM,
                fg=Theme.TEXT_DIM, bg=Theme.PANEL, width=8, anchor="w",
            ).pack(side="left")
            lbl = tk.Label(
                row, text="— —", font=FONT_DATA,
                fg=Theme.ACCENT_BRIGHT, bg=Theme.PANEL, anchor="w",
            )
            lbl.pack(side="left", fill="x")
            self._stat_labels[key] = lbl

        btn_row = tk.Frame(left, bg=Theme.BG)
        btn_row.pack(fill="x", padx=12, pady=4)

        HudButton(btn_row, text="◈ MEMORY", command=self._open_memory).pack(
            side="left", padx=(0, 8),
        )
        HudButton(btn_row, text="◈ PROTOCOLS", command=self._open_palette).pack(
            side="left", padx=(0, 8),
        )
        HudButton(
            btn_row, text="◈ COMMS", accent=True, command=self._toggle_chat,
        ).pack(side="left")

        self._voice_lbl = tk.Label(
            left, text="AUDIO  …", font=FONT_HUD_SM,
            fg=Theme.TEXT_DIM, bg=Theme.BG,
        )
        self._voice_lbl.pack(padx=16, anchor="w", pady=8)

        tk.Frame(lower, bg=Theme.ACCENT_DIM, width=1).pack(side="left", fill="y")

        right = tk.Frame(lower, bg=Theme.BG)
        right.pack(side="left", fill="both", expand=True)

        self._chat_panel = tk.Frame(right, bg=Theme.BG)
        self._chat = ChatScrollArea(self._chat_panel)
        self._chat.pack(fill="both", expand=True)

        input_row = tk.Frame(self._chat_panel, bg=Theme.BG)
        input_row.pack(fill="x", pady=(8, 0))

        tk.Label(
            input_row, text="▸", font=FONT_HUD_BOLD,
            fg=Theme.GOLD, bg=Theme.BG,
        ).pack(side="left", padx=(0, 6))

        self._input = tk.Entry(
            input_row, font=FONT_HUD, bg=Theme.PANEL, fg=Theme.TEXT,
            insertbackground=Theme.ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=Theme.ACCENT_DIM,
            highlightcolor=Theme.ACCENT_BRIGHT,
        )
        self._input.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 10))
        self._input.bind("<Return>", self._on_submit)

        self._send_btn = HudButton(
            input_row, text="TRANSMIT", accent=True,
            font=FONT_HUD_BOLD, command=self._on_submit,
        )
        self._send_btn.pack(side="left")

        self._chat_placeholder = tk.Frame(right, bg=Theme.BG)
        tk.Label(
            self._chat_placeholder,
            text="COMMS CHANNEL OFFLINE",
            font=FONT_HUD_BOLD,
            fg=Theme.ACCENT_DIM,
            bg=Theme.BG,
        ).pack(expand=True)
        tk.Label(
            self._chat_placeholder,
            text="Press  Ctrl+T  to open text interface",
            font=FONT_HUD,
            fg=Theme.TEXT_DIM,
            bg=Theme.BG,
        ).pack(pady=(0, 80))
        self._chat_placeholder.pack(fill="both", expand=True)

        self._footer = tk.Frame(root, bg=Theme.BG, height=28)
        self._footer_lbl = tk.Label(
            self._footer,
            text="Ctrl+T hide  ·  Ctrl+K protocols  ·  Voice active",
            font=FONT_HUD_SM, fg=Theme.TEXT_DIM, bg=Theme.BG,
        )
        self._footer_lbl.pack(side="left", padx=20, pady=5)

    def _bind_keys(self):
        self.root.bind("<Control-k>", lambda e: self._open_palette())
        self.root.bind("<Control-K>", lambda e: self._open_palette())
        self.root.bind("<Control-t>", lambda e: self._toggle_panel())
        self.root.bind("<Control-T>", lambda e: self._toggle_panel())

    def _toggle_panel(self, _event=None):
        """Show/hide full lower UI (stats, chat, footer). Orb-only when hidden."""
        self._panel_visible = not self._panel_visible
        if self._panel_visible:
            self._orb_hint.pack_forget()
            self._orb_sec.pack_forget()
            self._orb_sec.pack(fill="x")
            self._orb_sec.pack_propagate(False)
            self._orb_sec.config(height=360)
            self._orb.pack_configure(expand=False, pady=(4, 0))
            self._gold_line.pack(fill="x")
            self._lower.pack(fill="both", expand=True)
            self._footer.pack(fill="x")
            self._chat_visible = True
            self._chat_placeholder.pack_forget()
            self._chat_panel.pack(fill="both", expand=True, padx=16, pady=12)
            self.root.after(50, lambda: self._input.focus_set())
        else:
            self._lower.pack_forget()
            self._footer.pack_forget()
            self._gold_line.pack_forget()
            self._orb_sec.pack_forget()
            self._orb_sec.pack(fill="both", expand=True)
            self._orb_sec.pack_propagate(True)
            self._orb.pack_configure(expand=True, pady=(8, 0))
            self._orb_hint.pack(pady=(0, 16))
            self._chat_visible = False

    def _toggle_chat(self, _event=None):
        self._toggle_panel()

    def _ensure_chat_visible(self):
        if not self._panel_visible:
            self._toggle_panel()

    def _set_state(self, state):
        self._state = state
        labels = {
            "idle": ("◈ STANDBY", Theme.TEXT_DIM),
            "listening": ("◈ RECEIVING", Theme.ACCENT_BRIGHT),
            "thinking": ("◈ PROCESSING", Theme.GOLD),
            "speaking": ("◈ TRANSMITTING", Theme.SUCCESS),
        }
        text, color = labels.get(state, ("◈ STANDBY", Theme.TEXT_DIM))
        self._mode_lbl.config(text=text, fg=color)
        self._state_hdr.config(text=text.replace("◈ ", ""), fg=color)
        self._orb.set_state(state)
        lvl = 0.3 if state == "listening" else (0.5 if state == "speaking" else 0.0)
        self._orb.set_audio_level(lvl)

    def _flash_wake(self):
        self._orb.pulse_wake()
        self._wake_indicator.itemconfig(self._wake_dot, fill=Theme.ACCENT_BRIGHT)
        self.root.after(800, lambda: self._wake_indicator.itemconfig(
            self._wake_dot, fill=Theme.ACCENT_DIM
        ))

    def _startup_check(self):
        if jarvis.check_ollama():
            self._chat.add_system("NOVA online. Neural core connected.")
            self._stat_labels["OLLAMA"].config(text="ONLINE", fg=Theme.SUCCESS)
        else:
            self._chat.add_system("⚠ Ollama offline. Start Ollama and retry.")
            self._stat_labels["OLLAMA"].config(text="OFFLINE", fg=Theme.DANGER)
        wake = ", ".join(f'"{w}"' for w in jarvis.WAKE_WORDS[:3])
        self._wake_word_lbl.config(text=wake.upper() if wake else '"NOVA"')

    def _update_stats(self):
        if psutil:
            try:
                cpu = psutil.cpu_percent(interval=None)
                vm = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                ram_gb = vm.used / (1024 ** 3)
                self._stat_labels["CPU"].config(text=f"{cpu:.0f}%")
                self._stat_labels["RAM"].config(text=f"{ram_gb:.1f}GB / {vm.percent:.0f}%")
                self._stat_labels["GPU"].config(text="—")
            except Exception:
                pass
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for entries in temps.values():
                        if entries:
                            self._stat_labels["TEMP"].config(
                                text=f"{entries[0].current:.0f}°C"
                            )
                            break
                else:
                    self._stat_labels["TEMP"].config(text="—")
            except Exception:
                self._stat_labels["TEMP"].config(text="—")
        else:
            self._stat_labels["CPU"].config(text="n/a")

        online = jarvis.check_ollama()
        self._stat_labels["OLLAMA"].config(
            text="ONLINE" if online else "OFFLINE",
            fg=Theme.SUCCESS if online else Theme.DANGER,
        )
        self._stat_labels["VOICE"].config(
            text="ONLINE" if self._voice_online else "OFFLINE",
            fg=Theme.SUCCESS if self._voice_online else Theme.DANGER,
        )
        jarvis.load_memory()
        n = len(jarvis.memory.get("memories", []))
        self._stat_labels["MEMORY"].config(text=str(n))

        self.root.after(2000, self._update_stats)

    def _tick_clock(self):
        self._time_lbl.config(text=datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    def _open_memory(self):
        MemoryViewer(self.root)

    def _open_palette(self):
        CommandPalette(self.root, self._palette_action)

    def _palette_action(self, label, action):
        if action == "__memory__":
            self._open_memory()
            return
        if action.endswith(" "):
            self._ensure_chat_visible()
            self._input.delete(0, "end")
            self._input.insert(0, action)
            self._input.focus_set()
            return
        self._submit_text(action)

    def _on_submit(self, event=None):
        self._ensure_chat_visible()
        text = self._input.get().strip()
        if not text:
            return
        self._input.delete(0, "end")
        self._submit_text(text)

    def _submit_text(self, text):
        if self._busy:
            return
        self._busy = True
        self._send_btn.config(state="disabled")
        self._chat.add_user(text)
        self._set_state("thinking")
        threading.Thread(target=process_user_input, args=(text,), daemon=True).start()

    def _on_voice_input(self, text):
        if self._busy:
            return
        self._chat.add_user(f"🎤 {text}")
        self._busy = True
        self._set_state("thinking")
        threading.Thread(target=process_user_input, args=(text,), daemon=True).start()

    def _poll_events(self):
        try:
            while True:
                ev = ui_events.get_nowait()
                self._handle_event(ev)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_events)

    def _handle_event(self, ev):
        kind = ev[0]
        if kind == "state":
            self._set_state(ev[1])
        elif kind == "wake":
            self._flash_wake()
            self._chat.add_system("Voice trigger acknowledged. Listening…")
            self._set_state("listening")
        elif kind == "voice_input":
            self._on_voice_input(ev[1])
        elif kind == "voice_status":
            self._voice_online = ev[1]
            self._voice_lbl.config(
                text="AUDIO  ONLINE" if ev[1] else "AUDIO  OFFLINE",
                fg=Theme.SUCCESS if ev[1] else Theme.DANGER,
            )
        elif kind == "command_start":
            self._cmd_card = self._chat.add_command(ev[1], "RUNNING")
        elif kind == "command_done":
            if self._cmd_card:
                self._cmd_card.set_status("COMPLETE", ok=True)
            self._cmd_card = None
            if len(ev) > 2 and ev[2]:
                self._chat.add_nova(ev[2])
            self._finish_turn(speaking=True)
        elif kind == "chat_done":
            self._chat.add_nova(ev[1])
            self._finish_turn(speaking=True)
        elif kind == "error":
            self._chat.add_system(f"Error: {ev[1]}")
            sounds.play("error")
            self._finish_turn()
        else:
            pass

    def _finish_turn(self, speaking=False):
        self._busy = False
        self._send_btn.config(state="normal")
        if speaking:
            self._set_state("speaking")
            self.root.after(2800, lambda: self._set_state("idle"))
        else:
            self._set_state("idle")


if __name__ == "__main__":
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    app = NovaUI(root)
    root.mainloop()
