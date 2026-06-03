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
import base64
import io
import time

try:
    import psutil
except ImportError:
    psutil = None

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

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
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# UI thread events
ui_events = queue.Queue()


def _jarvis_to_ui(event, *payload):
    ui_events.put((event,) + payload)


jarvis.set_ui_emit(_jarvis_to_ui)



# Theme — Enhanced Iron Man JARVIS holographic HUD


class Theme:
    BG          = "#010508"
    BG_GRID     = "#061420"
    PANEL       = "#040C14"
    PANEL_EDGE  = "#1A4A6E"
    ACCENT      = "#4FC3F7"
    ACCENT_BRIGHT = "#8FE8FF"
    ACCENT_DIM  = "#1E5A7A"
    GOLD        = "#D4AF37"
    GOLD_BRIGHT = "#F0D060"
    GOLD_DIM    = "#8A7028"
    SUCCESS     = "#5CE1FF"
    DANGER      = "#FF5566"
    WARN        = "#E8C547"
    TEXT        = "#C5E8F7"
    TEXT_DIM    = "#5A8AA8"
    GLOW        = "#6DD5FA"
    CORE        = "#E8F8FF"
    USER_BUBBLE = "#061018"
    NOVA_BUBBLE = "#040E18"
    CMD_BG      = "#081420"
    SCAN        = "#0E3050"
    BTN_BG      = "#0A1A2A"
    BTN_FG      = "#8FE8FF"
    BTN_BORDER  = "#2A6A8F"
    BTN_ACTIVE_BG = "#1A4A6E"
    BTN_ACTIVE_FG = "#E8F8FF"
    BTN_DISABLED_BG = "#061018"
    BTN_DISABLED_FG = "#3A5A6A"
    # new
    PLASMA      = "#A78BFA"   # purple plasma streaks
    PLASMA_DIM  = "#4C1D95"
    ENERGY      = "#34D399"   # energy green for particles
    HOT         = "#F97316"   # orange-hot for reactor heat


FONT_TITLE      = ("Helvetica Neue", 20, "normal")
FONT_SUB        = ("Helvetica Neue", 9)
FONT_HUD        = ("Helvetica Neue", 10)
FONT_HUD_BOLD   = ("Helvetica Neue", 10, "bold")
FONT_HUD_SM     = ("Helvetica Neue", 8)
FONT_DATA       = ("Courier New", 10)
FONT_BODY       = ("Helvetica Neue", 11)
FONT_CHAT_LABEL = ("Helvetica Neue", 7, "bold")


def apply_hud_widget_defaults(root):
    root.option_add("*Button.Background",        Theme.BTN_BG)
    root.option_add("*Button.Foreground",        Theme.BTN_FG)
    root.option_add("*Button.activeBackground",  Theme.BTN_ACTIVE_BG)
    root.option_add("*Button.activeForeground",  Theme.BTN_ACTIVE_FG)
    root.option_add("*Button.highlightBackground", Theme.BTN_BORDER)
    root.option_add("*Button.highlightColor",    Theme.ACCENT_BRIGHT)
    root.option_add("*Button.relief",            "flat")
    root.option_add("*Button.borderWidth",       0)
    root.option_add("*Entry.Background",         Theme.PANEL)
    root.option_add("*Entry.Foreground",         Theme.TEXT)
    root.option_add("*Listbox.Background",       Theme.PANEL)
    root.option_add("*Listbox.Foreground",       Theme.TEXT)
    root.option_add("*Listbox.selectBackground", Theme.ACCENT_DIM)
    root.option_add("*Listbox.selectForeground", Theme.CORE)


class HudButton(tk.Button):
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



# App Icon Generator


def generate_app_icon(root):
    """Generate and set the app icon using Pillow if available."""
    if not PIL_AVAILABLE:
        return

    os.makedirs(_ASSETS_DIR, exist_ok=True)
    icon_path = os.path.join(_ASSETS_DIR, "nova_icon.png")

    SIZE = 512
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = SIZE // 2
    R = SIZE // 2 - 28

    # Deep space background circle
    for i in range(R, 0, -1):
        t = i / R
        r_v = int(1 + 3 * t)
        g_v = int(5 + 12 * t)
        b_v = int(8 + 20 * t)
        alpha = int(255 * (1 - (1 - t) ** 2))
        draw.ellipse([cx-i, cy-i, cx+i, cy+i], fill=(r_v, g_v, b_v, alpha))

    # Outer halo glow
    for i in range(50, 0, -1):
        alpha = int(90 * (1 - i / 50) ** 2)
        r_halo = R + i
        draw.ellipse([cx-r_halo, cy-r_halo, cx+r_halo, cy+r_halo],
                     outline=(79, 195, 247, alpha), width=1)

    # Wireframe latitude bands
    for li in range(11):
        lat = -math.pi / 2 + math.pi * li / 10
        r2 = R * abs(math.cos(lat))
        y_off = R * math.sin(lat) * 0.75
        if r2 > 4:
            bright = abs(math.cos(lat))
            alpha = int(40 + 130 * bright)
            b_lat = r2 * 0.38
            draw.ellipse([cx - r2, cy + y_off - b_lat,
                          cx + r2, cy + y_off + b_lat],
                         outline=(79, 195, 247, alpha), width=1)

    # Wireframe longitude arcs
    for lj in range(16):
        lon = 2 * math.pi * lj / 16
        pts = []
        for li in range(80):
            lat = -math.pi / 2 + math.pi * li / 79
            x3d = math.cos(lat) * math.cos(lon)
            y3d = math.sin(lat) * 0.75
            z3d = math.cos(lat) * math.sin(lon)
            if z3d < -0.1:
                continue
            shade = int(50 + 80 * max(0, z3d))
            pts.append((int(cx + x3d * R), int(cy + y3d * R), shade))
        for k in range(len(pts) - 1):
            shade = pts[k][2]
            draw.line([(pts[k][0], pts[k][1]), (pts[k+1][0], pts[k+1][1])],
                      fill=(79, 195, 247, shade), width=1)

    # Three rotating arc-reactor rings (ellipses at angle)
    ring_specs = [
        (R * 0.68, 22, 3, (212, 175, 55)),
        (R * 0.82, 40, 2, (79, 195, 247)),
        (R * 0.92, 15, 2, (143, 232, 255)),
    ]
    for rr, tilt_deg, w, col in ring_specs:
        b_ring = rr * math.sin(math.radians(tilt_deg))
        for seg in range(6):
            a1 = seg * 60 + 10
            a2 = a1 + 42
            draw.arc([cx - rr, cy - b_ring, cx + rr, cy + b_ring],
                     start=a1, end=a2,
                     fill=(*col, 200), width=w)

    # Hexagon ring
    hr = 52
    for i in range(6):
        a1 = math.radians(60 * i - 30)
        a2 = math.radians(60 * (i + 1) - 30)
        draw.line([
            (cx + hr * math.cos(a1), cy + hr * math.sin(a1)),
            (cx + hr * math.cos(a2), cy + hr * math.sin(a2))
        ], fill=(212, 175, 55, 220), width=2)

    # Triangle detail marks at hex corners
    for i in range(6):
        a = math.radians(60 * i - 30)
        tx = cx + hr * math.cos(a)
        ty = cy + hr * math.sin(a)
        draw.ellipse([tx - 3, ty - 3, tx + 3, ty + 3],
                     fill=(240, 208, 96, 255))

    # Arc reactor core glow layers
    core_r = 45
    for i in range(core_r, 0, -1):
        t_core = (core_r - i) / core_r
        r_c = int(4 + 228 * t_core)
        g_c = int(12 + 236 * t_core)
        b_c = int(20 + 235 * t_core)
        alpha_c = int(255 * t_core ** 0.6)
        draw.ellipse([cx - i, cy - i, cx + i, cy + i],
                     fill=(r_c, g_c, b_c, alpha_c))

    # Inner hex detail on core
    ihr = 22
    for i in range(6):
        a1 = math.radians(60 * i)
        a2 = math.radians(60 * (i + 1))
        draw.line([
            (cx + ihr * math.cos(a1), cy + ihr * math.sin(a1)),
            (cx + ihr * math.cos(a2), cy + ihr * math.sin(a2))
        ], fill=(232, 248, 255, 180), width=1)

    # Bright core center
    for i in (14, 9, 5, 2):
        alpha_core = int(255 * (1 - i / 15))
        draw.ellipse([cx - i, cy - i, cx + i, cy + i],
                     fill=(232, 248, 255, 255))
    draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5],
                 fill=(255, 255, 255, 255))

    # Chrome outer border
    draw.ellipse([cx - R, cy - R, cx + R, cy + R],
                 outline=(79, 195, 247, 255), width=3)
    draw.ellipse([cx - R - 5, cy - R - 5, cx + R + 5, cy + R + 5],
                 outline=(79, 195, 247, 80), width=2)

    # Tick marks around border
    for i in range(72):
        ang = math.radians(i * 5)
        r_in = R + 8 if i % 6 == 0 else R + 5
        r_out = R + 16 if i % 6 == 0 else R + 10
        col_tick = (212, 175, 55, 200) if i % 18 == 0 else (79, 195, 247, 120)
        w_tick = 2 if i % 6 == 0 else 1
        x1_t = cx + r_in * math.cos(ang)
        y1_t = cy + r_in * math.sin(ang)
        x2_t = cx + r_out * math.cos(ang)
        y2_t = cy + r_out * math.sin(ang)
        draw.line([(x1_t, y1_t), (x2_t, y2_t)], fill=col_tick, width=w_tick)

    # Light bloom
    bloom = img.filter(ImageFilter.GaussianBlur(radius=3))
    img = Image.blend(img, bloom, 0.15)

    img.save(icon_path)

    # Set window icon
    try:
        tk_img = ImageTk.PhotoImage(img.resize((64, 64), Image.LANCZOS))
        root._icon_ref = tk_img  # prevent GC
        root.iconphoto(True, tk_img)
    except Exception as e:
        print(f"[UI] Could not set icon: {e}")



# Sound effects


class SoundManager:
    MAC_FALLBACKS = {
        "startup": "/System/Library/Sounds/Hero.aiff",
        "listen":  "/System/Library/Sounds/Pop.aiff",
        "think":   "/System/Library/Sounds/Tink.aiff",
        "success": "/System/Library/Sounds/Glass.aiff",
        "error":   "/System/Library/Sounds/Basso.aiff",
    }

    def __init__(self):
        os.makedirs(_SOUNDS_DIR, exist_ok=True)
        self._ensure_placeholders()

    def _ensure_placeholders(self):
        specs = {
            "startup": (880, 0.12),
            "listen":  (660, 0.06),
            "think":   (440, 0.04),
            "success": (990, 0.1),
            "error":   (220, 0.15),
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



# Helpers


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def lerp_color(c1, c2, t):
    r1, g1, b1 = hex_rgb(c1)
    r2, g2, b2 = hex_rgb(c2)
    t = max(0.0, min(1.0, t))
    return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"


def blend_alpha(fg, bg, alpha):
    fr, fg_c, fb = hex_rgb(fg)
    br, bg_c, bb = hex_rgb(bg)
    alpha = max(0.0, min(1.0, alpha))
    r = int(br + (fr - br) * alpha)
    g = int(bg_c + (fg_c - bg_c) * alpha)
    b = int(bb + (fb - bb) * alpha)
    return f"#{r:02x}{g:02x}{b:02x}"


def draw_hud_corners(canvas, x1, y1, x2, y2, color, length=14, width=2, tag="hud"):
    L = length
    for ax, ay, dx, dy in (
        (x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1),
    ):
        canvas.create_line(ax, ay, ax+dx*L, ay, fill=color, width=width, tags=tag)
        canvas.create_line(ax, ay, ax, ay+dy*L, fill=color, width=width, tags=tag)


class HudBackdrop(tk.Canvas):
    """Animated grid + scan line + particle field behind the interface."""

    def __init__(self, parent):
        super().__init__(parent, bg=Theme.BG, highlightthickness=0, bd=0)
        self._tick = 0
        self._particles = []
        self.bind("<Configure>", lambda e: self._init_particles())
        self._animate()

    def _init_particles(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self._particles = [
            {
                "x": random.uniform(0, w),
                "y": random.uniform(0, h),
                "vx": random.uniform(-0.3, 0.3),
                "vy": random.uniform(-0.5, -0.1),
                "r": random.uniform(1, 2.5),
                "alpha": random.uniform(0.2, 0.8),
                "hue": random.choice([Theme.ACCENT_DIM, Theme.GOLD_DIM, Theme.PANEL_EDGE]),
            }
            for _ in range(40)
        ]

    def _animate(self):
        self._tick += 1
        w, h = self.winfo_width(), self.winfo_height()
        if w > 10 and not self._particles:
            self._init_particles()
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            if p["y"] < -5:
                p["y"] = h + 2
                p["x"] = random.uniform(0, w)
            if p["x"] < 0:
                p["x"] = w
            elif p["x"] > w:
                p["x"] = 0
        self._draw()
        self.after(50, self._animate)

    def _draw(self):
        self.delete("grid", "scan", "particle")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return

        # Grid
        step = 40
        for x in range(0, w, step):
            col = Theme.BG_GRID if x % (step * 2) else Theme.SCAN
            self.create_line(x, 0, x, h, fill=col, tags="grid")
        for y in range(0, h, step):
            col = Theme.BG_GRID if y % (step * 2) else Theme.SCAN
            self.create_line(0, y, w, y, fill=col, tags="grid")

        # Scan sweep
        sweep = (self._tick * 4) % (h + 80) - 40
        for i, (off, alpha) in enumerate([(0, 0.7), (2, 0.25), (5, 0.1), (-2, 0.15)]):
            c = blend_alpha(Theme.ACCENT_DIM, Theme.BG, alpha)
            self.create_line(0, sweep + off, w, sweep + off, fill=c, tags="scan")

        # Particles (floating data specs)
        for p in self._particles:
            r = p["r"]
            self.create_oval(
                p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r,
                fill=p["hue"], outline="", tags="particle",
            )

        # Vignette
        for i in range(8):
            a = max(0, 0.18 - i * 0.022)
            c = blend_alpha(Theme.BG, Theme.ACCENT_DIM, a)
            self.create_rectangle(0, i*3, w, i*3+2, fill=c, outline="", tags="grid")
            self.create_rectangle(0, h-i*3-2, w, h-i*3, fill=c, outline="", tags="grid")


def process_user_input(text):
    try:
        sounds.play("think")
        jarvis.process_input(text)
        sounds.play("success")
    except Exception as e:
        ui_events.put(("error", str(e)))
        sounds.play("error")



# Glass panel


class HudPanel(tk.Canvas):
    def __init__(self, parent, width=None, height=None, glow=False, **kw):
        super().__init__(
            parent, bg=Theme.BG, highlightthickness=0, bd=0,
            width=width or 1, height=height or 1, **kw,
        )
        self._glow = glow
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        pad = 6
        fill = blend_alpha(Theme.PANEL, Theme.BG, 0.92)
        edge = Theme.ACCENT if self._glow else Theme.PANEL_EDGE
        self.create_rectangle(pad, pad, w-pad, h-pad, fill=fill, outline=edge, width=1)
        draw_hud_corners(self, pad, pad, w-pad, h-pad,
                         Theme.ACCENT if self._glow else Theme.GOLD_DIM, length=16)
        if self._glow:
            draw_hud_corners(self, pad+2, pad+2, w-pad-2, h-pad-2,
                             Theme.GLOW, length=10, width=1)
        cx = w / 2
        self.create_line(cx-30, pad, cx+30, pad, fill=Theme.ACCENT, width=1)
        self.create_line(cx, pad-3, cx, pad+3, fill=Theme.GOLD, width=1)



# Scrollable chat


class ChatScrollArea(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=Theme.BG)
        self._cards = []

        head = tk.Frame(self, bg=Theme.BG)
        head.pack(fill="x", pady=(0, 6))
        tk.Label(head, text="◢ COMMS CHANNEL", font=FONT_CHAT_LABEL,
                 fg=Theme.GOLD, bg=Theme.BG).pack(side="left")
        tk.Label(head, text="SECURE LINK", font=FONT_HUD_SM,
                 fg=Theme.ACCENT_DIM, bg=Theme.BG).pack(side="right")

        border = tk.Frame(self, bg=Theme.ACCENT, padx=1, pady=1)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg=Theme.PANEL)
        inner.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(inner, bg=Theme.PANEL, highlightthickness=0, bd=0)
        self._scrollbar = tk.Scrollbar(
            inner, orient="vertical", command=self._canvas.yview,
            bg=Theme.BTN_BG, troughcolor=Theme.PANEL,
            activebackground=Theme.ACCENT_DIM, highlightthickness=0, relief="flat", width=10,
        )
        self._frame = tk.Frame(self._canvas, bg=Theme.PANEL)
        self._frame.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
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
            tk.Label(bubble, text=f"▸ {label}", font=FONT_CHAT_LABEL,
                     fg=fg_title, bg=bg).pack(anchor="w")

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
        tk.Label(box, text="◈ PROTOCOL EXECUTION", font=FONT_CHAT_LABEL,
                 fg=Theme.GOLD, bg=Theme.CMD_BG).pack(anchor="w")
        self._cmd_lbl = tk.Label(box, text=cmd, font=FONT_HUD_BOLD,
                                  fg=Theme.ACCENT_BRIGHT, bg=Theme.CMD_BG)
        self._cmd_lbl.pack(anchor="w", pady=(4, 0))
        self._status_lbl = tk.Label(box, text=f"▸ {status}", font=FONT_DATA,
                                     fg=Theme.TEXT_DIM, bg=Theme.CMD_BG)
        self._status_lbl.pack(anchor="w", pady=(4, 0))
        if detail:
            tk.Label(box, text=detail, font=FONT_HUD_SM, fg=Theme.TEXT,
                     bg=Theme.CMD_BG, wraplength=400, justify="left").pack(anchor="w", pady=(4, 0))

    def set_status(self, status, ok=False):
        self._status_lbl.config(
            text=f"▸ {'COMPLETE' if ok else status}",
            fg=Theme.SUCCESS if ok else Theme.GOLD,
        )



# NOVA Arc-Reactor Sphere  — v2 (dramatically enhanced)


class Particle:
    """Floating energy particle orbiting the sphere."""
    __slots__ = ("angle", "orbit_r", "speed", "size", "phase", "color")

    def __init__(self, orbit_r, color):
        self.angle  = random.uniform(0, 2 * math.pi)
        self.orbit_r = orbit_r + random.uniform(-12, 12)
        self.speed  = random.uniform(0.008, 0.025) * random.choice((-1, 1))
        self.size   = random.uniform(1.5, 3.5)
        self.phase  = random.uniform(0, math.pi * 2)
        self.color  = color


class JarvisCore(tk.Canvas):
    """
    Enhanced arc-reactor hologram:
    • Full 3D wireframe sphere with shading & z-depth tinting
    • Gyroscopic triple-ring assembly with gold/cyan styling
    • Rotating hex bolt ring
    • Energy particle field (20 particles)
    • Plasma arc streaks
    • State-aware voice rings, aurora shimmer, heat gradient
    • Wake pulse expanding shockwave
    • Radar sweep with glow cone
    • Corona / bloom effect
    """

    def __init__(self, parent, size=420):
        super().__init__(parent, width=size, height=size,
                         bg=Theme.BG, highlightthickness=0)
        self._size   = size
        self._tick   = 0
        self._state  = "idle"
        self._audio  = 0.0
        self._wake   = 0.0
        self._beat   = 0.0   # heart-beat pulse
        # Particles
        cx = size / 2
        self._particles = (
            [Particle(size * 0.38, Theme.ACCENT_DIM) for _ in range(10)] +
            [Particle(size * 0.42, Theme.GOLD_DIM)   for _ in range(6)]  +
            [Particle(size * 0.45, Theme.PLASMA_DIM)  for _ in range(4)]
        )

    # ── Public API ──────────────────────────────────────────────────────────
    def set_state(self, state):
        self._state = state

    def set_audio_level(self, level):
        self._audio = max(0.0, min(1.0, level))

    def pulse_wake(self):
        self._wake = 1.0

    def animate(self):
        self._tick += 1
        if self._wake > 0:
            self._wake = max(0, self._wake - 0.03)
        self._beat = 0.5 + 0.5 * math.sin(self._tick * 0.08)
        for p in self._particles:
            p.angle += p.speed
        self._draw()
        self.after(30, self.animate)

    # ── Drawing ─────────────────────────────────────────────────────────────
    def _draw(self):
        self.delete("all")
        s  = self._size
        cx = cy = s / 2
        R  = s * 0.30
        t  = self._tick * 0.04
        state = self._state
        pulse = 0.10 * math.sin(t * 2.8) + self._audio * 0.35

        # Choose accent colour per state
        if state == "speaking":
            accent = Theme.SUCCESS
        elif state == "thinking":
            accent = Theme.GOLD_BRIGHT
        elif state == "listening":
            accent = Theme.ACCENT_BRIGHT
        else:
            accent = Theme.ACCENT

        # ── 1. Corona bloom (outermost soft glow) ───────────────────────────
        for i in range(12, 0, -1):
            cr = R + 55 + i * 5 + pulse * 20
            alpha = 0.04 + pulse * 0.03
            c = blend_alpha(accent, Theme.BG, alpha * (12 - i) / 12)
            self.create_oval(cx-cr, cy-cr, cx+cr, cy+cr, outline=c, width=1)

        # ── 2. Outer HUD tick ring ───────────────────────────────────────────
        tick_r = R + 54 + pulse * 6
        for i in range(72):
            ang = math.radians(i * 5 + t * 15)
            major = (i % 9 == 0)
            minor = (i % 3 == 0)
            r_in  = tick_r
            r_out = tick_r + (10 if major else (6 if minor else 3))
            x1 = cx + r_in  * math.cos(ang)
            y1 = cy + r_in  * math.sin(ang)
            x2 = cx + r_out * math.cos(ang)
            y2 = cy + r_out * math.sin(ang)
            col = Theme.GOLD if major else Theme.ACCENT_DIM
            w   = 2 if major else 1
            self.create_line(x1, y1, x2, y2, fill=col, width=w)

        # ── 3. Radar sweep with glow cone ───────────────────────────────────
        sweep_ang = math.radians(t * 70)
        sweep_r   = R + 50 + pulse * 8
        # Cone glow (multiple arcs with fading opacity)
        for i in range(8):
            cone_alpha = 0.12 * (1 - i / 8)
            c = blend_alpha(accent, Theme.BG, cone_alpha)
            self.create_arc(
                cx - sweep_r, cy - sweep_r, cx + sweep_r, cy + sweep_r,
                start=math.degrees(sweep_ang) - 35 + i * 2,
                extent=35 - i * 2,
                fill=c, outline="",
            )
        # Sweep line
        sx = cx + sweep_r * math.cos(sweep_ang)
        sy = cy + sweep_r * math.sin(sweep_ang)
        self.create_line(cx, cy, sx, sy,
                         fill=lerp_color(Theme.BG, accent, 0.6), width=2)

        # ── 4. Triple gyroscopic rings ───────────────────────────────────────
        ring_specs = [
            # (radius_offset, tilt, rot_speed, color, seg_extent, width)
            (R * 0.70, 18, 0.55,  Theme.GOLD,         38, 3),
            (R * 0.82, 40, -0.85, Theme.ACCENT,        32, 2),
            (R * 0.96, 65, 1.15,  Theme.ACCENT_BRIGHT, 26, 2),
        ]
        for rr, tilt_deg, spd, col, ext, lw in ring_specs:
            b = rr * math.sin(math.radians(tilt_deg))
            start = (t * 40 * spd) % 360
            for seg in range(5):
                s_start = start + seg * (360 / 5)
                self.create_arc(
                    cx - rr, cy - b, cx + rr, cy + b,
                    start=s_start, extent=ext,
                    outline=col, width=lw, style="arc",
                )

        # ── 5. Rotating hex bolt ring ────────────────────────────────────────
        hex_orbit = R + 18
        for i in range(6):
            ang = math.radians(60 * i + t * 25)
            hx = cx + hex_orbit * math.cos(ang)
            hy = cy + hex_orbit * math.sin(ang)
            # Mini hex at each bolt
            bolt_r = 5 + pulse * 2
            pts = []
            for j in range(6):
                a2 = math.radians(60 * j + t * 40)
                pts += [hx + bolt_r * math.cos(a2), hy + bolt_r * math.sin(a2)]
            self.create_polygon(pts, outline=Theme.GOLD, fill=Theme.GOLD_DIM, width=1)

        # ── 6. Full 3D wireframe sphere with z-depth shading ─────────────────
        n_lat, n_lon = 14, 20
        tilt  = 0.42
        rot_x = t * 0.12
        rot_y = t * 0.20

        def project(lat, lon):
            # Sphere → rotate → project
            x3 = math.cos(lat) * math.cos(lon + rot_y)
            y3 = math.sin(lat)
            z3 = math.cos(lat) * math.sin(lon + rot_y)
            # Tilt around X axis
            y4 = y3 * math.cos(tilt) - z3 * math.sin(tilt)
            z4 = y3 * math.sin(tilt) + z3 * math.cos(tilt)
            # Rotate around Y (slow wobble)
            x5 = x3 * math.cos(rot_x) + z4 * math.sin(rot_x)
            z5 = -x3 * math.sin(rot_x) + z4 * math.cos(rot_x)
            return x5, y4, z5

        # Latitude lines
        for li in range(n_lat):
            lat = -math.pi/2 + math.pi * li / (n_lat - 1)
            pts = []
            zs  = []
            for lj in range(n_lon + 1):
                lon = 2 * math.pi * lj / n_lon
                x5, y4, z5 = project(lat, lon)
                if z5 < -0.15:
                    if pts:
                        self._draw_sphere_seg(pts, zs, R, cx, cy, pulse, accent, state)
                        pts, zs = [], []
                    continue
                pts += [cx + x5*R*(1+pulse*0.08), cy + y4*R*(1+pulse*0.08)]
                zs.append(z5)
            if len(pts) >= 4:
                self._draw_sphere_seg(pts, zs, R, cx, cy, pulse, accent, state)

        # Longitude lines
        for lj in range(n_lon):
            lon = 2 * math.pi * lj / n_lon
            pts = []
            zs  = []
            for li in range(n_lat):
                lat = -math.pi/2 + math.pi * li / (n_lat - 1)
                x5, y4, z5 = project(lat, lon)
                if z5 < -0.12:
                    if pts:
                        self._draw_sphere_seg(pts, zs, R, cx, cy, pulse, accent, state)
                        pts, zs = [], []
                    continue
                pts += [cx + x5*R*(1+pulse*0.08), cy + y4*R*(1+pulse*0.08)]
                zs.append(z5)
            if len(pts) >= 4:
                self._draw_sphere_seg(pts, zs, R, cx, cy, pulse, accent, state)

        # ── 7. Plasma arc streaks ────────────────────────────────────────────
        if state in ("thinking", "speaking", "listening"):
            for i in range(3):
                arc_ang = t * 60 + i * 120
                arc_r   = R * 1.05 + pulse * 10
                arc_b   = arc_r * 0.25
                self.create_arc(
                    cx - arc_r, cy - arc_b, cx + arc_r, cy + arc_b,
                    start=arc_ang, extent=60,
                    outline=Theme.PLASMA, width=1, style="arc",
                )

        # ── 8. Energy particles ───────────────────────────────────────────────
        for p in self._particles:
            bob = math.sin(p.phase + t * 1.5) * 6
            px  = cx + (p.orbit_r + bob) * math.cos(p.angle)
            py  = cy + (p.orbit_r + bob * 0.5) * math.sin(p.angle)
            r   = p.size * (1 + pulse * 0.5)
            # Glow halo
            self.create_oval(px-r*2.5, py-r*2.5, px+r*2.5, py+r*2.5,
                             fill=p.color, outline="")
            # Bright core
            bright_col = lerp_color(p.color, Theme.CORE, 0.5)
            self.create_oval(px-r, py-r, px+r, py+r,
                             fill=bright_col, outline="")

        # ── 9. State voice / activity rings ─────────────────────────────────
        self._draw_state_rings(cx, cy, R, t, accent, pulse)

        # ── 10. Arc reactor core ─────────────────────────────────────────────
        core_r = R * (0.20 + 0.04 * math.sin(t * 5) + pulse * 0.06)

        # Heat gradient rings (outer to inner)
        heat_colors = [
            (Theme.ACCENT_DIM, 0.0),
            (Theme.ACCENT,      0.4),
            (Theme.ACCENT_BRIGHT, 0.65),
            (Theme.CORE,        0.85),
        ]
        for i in range(16, 0, -1):
            frac = (16 - i) / 16
            # pick heat color
            ci = int(frac * (len(heat_colors) - 1))
            ci2 = min(ci + 1, len(heat_colors) - 1)
            local_t = frac * (len(heat_colors) - 1) - ci
            c1_h, _ = heat_colors[ci]
            c2_h, _ = heat_colors[ci2]
            col = lerp_color(c1_h, c2_h, local_t)
            cr  = core_r * i / 16
            self.create_oval(cx-cr, cy-cr, cx+cr, cy+cr,
                             fill=col, outline="")

        # Hex ring on core
        hr = core_r * 1.45
        hex_pts = []
        for i in range(6):
            a = math.radians(60 * i + t * 28)
            hex_pts += [cx + hr*math.cos(a), cy + hr*math.sin(a)]
        self.create_polygon(hex_pts, outline=Theme.GOLD, fill="", width=2)

        # Secondary inner hex
        hr2 = core_r * 0.7
        hex_pts2 = []
        for i in range(6):
            a = math.radians(60 * i - t * 18)
            hex_pts2 += [cx + hr2*math.cos(a), cy + hr2*math.sin(a)]
        self.create_polygon(hex_pts2, outline=lerp_color(Theme.ACCENT_DIM, Theme.CORE, 0.3),
                            fill="", width=1)

        # Core centre dot
        self.create_oval(cx-4, cy-4, cx+4, cy+4,
                         fill=Theme.CORE, outline=Theme.ACCENT_BRIGHT, width=1)

        # ── 11. Wake shockwave ────────────────────────────────────────────────
        if self._wake > 0:
            for i in range(3):
                offset = i * 15
                wr = R + 60 + offset + 60 * (1 - self._wake)
                alpha = self._wake * (0.9 - i * 0.25)
                c = blend_alpha(Theme.ACCENT_BRIGHT, Theme.BG, alpha)
                self.create_oval(cx-wr, cy-wr, cx+wr, cy+wr,
                                 outline=c, width=max(1, int(3 * self._wake)))

    def _draw_sphere_seg(self, pts, zs, R, cx, cy, pulse, accent, state):
        if len(pts) < 4 or not zs:
            return
        avg_z = sum(zs) / len(zs)
        # Brightness: front face bright, back face dark
        brightness = 0.15 + 0.60 * max(0, avg_z)
        # State tint
        if state == "thinking":
            col = lerp_color(Theme.BG, Theme.GOLD_BRIGHT, brightness * 0.85)
        elif state == "speaking":
            col = lerp_color(Theme.BG, Theme.SUCCESS, brightness * 0.85)
        elif state == "listening":
            col = lerp_color(Theme.BG, Theme.ACCENT_BRIGHT, brightness)
        else:
            col = lerp_color(Theme.BG, accent, brightness)
        try:
            self.create_line(*pts, fill=col, width=1, smooth=True)
        except Exception:
            pass

    def _draw_state_rings(self, cx, cy, R, t, accent, pulse):
        state = self._state
        if state == "idle":
            # Slow breathing ring
            br = R + 30 + 6 * math.sin(t * 0.7)
            self.create_oval(cx-br, cy-br, cx+br, cy+br,
                             outline=Theme.PANEL_EDGE, width=1)
            return

        if state == "listening":
            for i in range(5):
                ph = t * 4.0 - i * 0.65
                r  = R + 24 + i * 9 + 7 * math.sin(ph)
                alpha = 0.2 + 0.25 * math.sin(ph)
                c = blend_alpha(accent, Theme.BG, max(0, alpha))
                self.create_oval(cx-r, cy-r, cx+r, cy+r, outline=c, width=2)
            # Equalizer bars
            for i in range(12):
                ang = math.radians(i * 30 + t * 10)
                h_bar = 8 + 14 * abs(math.sin(t * 5 + i * 0.7))
                x1 = cx + (R + 14) * math.cos(ang)
                y1 = cy + (R + 14) * math.sin(ang)
                x2 = cx + (R + 14 + h_bar) * math.cos(ang)
                y2 = cy + (R + 14 + h_bar) * math.sin(ang)
                self.create_line(x1, y1, x2, y2, fill=accent, width=2)

        elif state == "thinking":
            # Spinning dashed arcs + rotating spokes
            for i in range(3):
                ang = t * 2.2 + i * (2 * math.pi / 3)
                spoke_r = R + 38
                self.create_line(cx, cy,
                                 cx + spoke_r * math.cos(ang),
                                 cy + spoke_r * math.sin(ang),
                                 fill=Theme.GOLD, width=2)
                # Counter-rotating ring
                rr = R + 28 + i * 8
                self.create_arc(cx-rr, cy-rr, cx+rr, cy+rr,
                                start=math.degrees(ang) * (-1),
                                extent=55,
                                outline=Theme.GOLD_DIM, width=1, style="arc")
            # Orbit dot
            od_ang = t * 3.5
            od_r   = R + 42
            odx = cx + od_r * math.cos(od_ang)
            ody = cy + od_r * math.sin(od_ang)
            self.create_oval(odx-4, ody-4, odx+4, ody+4,
                             fill=Theme.GOLD_BRIGHT, outline="")

        elif state == "speaking":
            # Elliptical voice waveform rings
            for i in range(7):
                wave = abs(math.sin(t * 6 + i * 0.8)) * (1 + pulse * 0.5)
                r  = R + 20 + i * 5 + wave * 14
                ry = r * (0.45 + wave * 0.15)
                c  = lerp_color(Theme.BG, Theme.SUCCESS, 0.15 + wave * 0.55)
                self.create_oval(cx-r, cy-ry, cx+r, cy+ry, outline=c, width=1)
            # Frequency spikes
            for i in range(24):
                ang = math.radians(i * 15)
                spike = 6 + 16 * abs(math.sin(t * 7 + i))
                x1 = cx + (R + 18) * math.cos(ang)
                y1 = cy + (R + 18) * math.sin(ang)
                x2 = cx + (R + 18 + spike) * math.cos(ang)
                y2 = cy + (R + 18 + spike) * math.sin(ang)
                self.create_line(x1, y1, x2, y2,
                                 fill=lerp_color(Theme.BG, Theme.SUCCESS, 0.5), width=1)



# Command palette & memory viewer (unchanged logic, polished styling)


PALETTE_ACTIONS = [
    ("Open Discord",   "open discord"),
    ("Open YouTube",   "open youtube and play music"),
    ("Search Google",  "search google for "),
    ("System Status",  "what is my system status"),
    ("Weather",        "what is the weather"),
    ("Memory Viewer",  "__memory__"),
    ("Web Search",     "search the web for "),
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

        tk.Label(self, text="PROTOCOL SELECTOR", font=FONT_HUD_BOLD,
                 fg=Theme.GOLD, bg=Theme.BG).pack(pady=(16, 8))

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
            relief="flat", highlightthickness=0, bd=0, activestyle="none",
        )
        self._list.pack(fill="both", expand=True)
        self._list.bind("<Double-Button-1>", self._activate)
        self._items = list(PALETTE_ACTIONS)
        self._refresh()
        self.bind("<Escape>", lambda e: self.destroy())

        btn_row = tk.Frame(self, bg=Theme.BG)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        HudButton(btn_row, text="EXECUTE", accent=True,
                  command=self._activate).pack(side="right", padx=(8, 0))
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

    def _filter(self, _=None):
        self._refresh()

    def _activate(self, _=None):
        sel = self._list.curselection()
        idx = sel[0] if sel else (0 if self._filtered else None)
        if idx is None:
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

        tk.Label(self, text="◈ LONG-TERM MEMORY BANK", font=FONT_HUD_BOLD,
                 fg=Theme.GOLD, bg=Theme.BG).pack(pady=(16, 8))

        jarvis.load_memory()
        mems = jarvis.memory.get("memories", [])
        body = "Miles remembers:\n" if mems else "No memories stored yet.\n"
        if mems:
            body += "\n".join(f"  • {m}" for m in mems)
        body = "━" * 36 + "\n" + body + "\n" + "━" * 36

        text = tk.Text(self, font=FONT_DATA, bg=Theme.PANEL, fg=Theme.TEXT,
                       relief="flat", wrap="word", padx=16, pady=12,
                       insertbackground=Theme.ACCENT)
        text.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        text.insert("1.0", body)
        text.config(state="disabled")
        HudButton(self, text="CLOSE", command=self.destroy).pack(pady=(0, 16))



# Voice bridge


def voice_bridge_thread():
    try:
        ui_events.put(("voice_status", True))
        for utterance in jarvis.listen_loop():
            ui_events.put(("voice_input", utterance))
    except Exception as e:
        print(f"[UI Voice] {e}")
        ui_events.put(("voice_status", False))



# Main UI


class NovaUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NOVA")
        self.root.configure(bg=Theme.BG)
        self.root.geometry("1200x820")
        self.root.minsize(960, 680)

        self._state         = "idle"
        self._busy          = False
        self._cmd_card      = None
        self._voice_online  = False
        self._panel_visible = False

        apply_hud_widget_defaults(self.root)

        # Generate and set app icon
        generate_app_icon(self.root)

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

    # ── Layout ───────────────────────────────────────────────────────────────
    def _build(self):
        root = self._shell

        # ─ Header ─────────────────────────────────────────────────────────
        header = tk.Frame(root, bg=Theme.BG, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_block = tk.Frame(header, bg=Theme.BG)
        title_block.pack(side="left", padx=24, pady=10)
        tk.Label(title_block, text="N O V A", font=FONT_TITLE,
                 fg=Theme.ACCENT_BRIGHT, bg=Theme.BG).pack(anchor="w")
        tk.Label(title_block, text="Novel Operating Variability Assistant",
                 font=FONT_HUD_SM, fg=Theme.GOLD_DIM, bg=Theme.BG).pack(anchor="w")

        self._wake_frame = tk.Frame(header, bg=Theme.BG)
        self._wake_frame.pack(side="left", padx=16)
        tk.Label(self._wake_frame, text="VOICE TRIGGER", font=FONT_HUD_SM,
                 fg=Theme.TEXT_DIM, bg=Theme.BG).pack(side="left")
        self._wake_word_lbl = tk.Label(self._wake_frame, text='"NOVA"',
                                        font=FONT_HUD_BOLD, fg=Theme.GOLD, bg=Theme.BG)
        self._wake_word_lbl.pack(side="left", padx=(6, 0))
        self._wake_indicator = tk.Canvas(self._wake_frame, width=12, height=12,
                                          bg=Theme.BG, highlightthickness=0)
        self._wake_indicator.pack(side="left", padx=8)
        self._wake_dot = self._wake_indicator.create_oval(
            2, 2, 10, 10, fill=Theme.ACCENT_DIM, outline=Theme.ACCENT)

        self._time_lbl = tk.Label(header, text="", font=FONT_DATA,
                                   fg=Theme.ACCENT, bg=Theme.BG)
        self._time_lbl.pack(side="right", padx=20)
        self._state_hdr = tk.Label(header, text="STANDBY", font=FONT_HUD_BOLD,
                                    fg=Theme.TEXT_DIM, bg=Theme.BG)
        self._state_hdr.pack(side="right", padx=8)

        tk.Frame(root, bg=Theme.ACCENT_DIM, height=1).pack(fill="x")

        # ─ Orb section (full window until Ctrl+T) ─────────────────────────
        self._orb_sec = tk.Frame(root, bg=Theme.BG)
        self._orb_sec.pack(fill="both", expand=True)

        self._orb = JarvisCore(self._orb_sec, size=420)
        self._orb.pack(expand=True, pady=(8, 0))

        self._mode_lbl = tk.Label(self._orb_sec, text="◈ STANDBY",
                                   font=FONT_HUD, fg=Theme.TEXT_DIM, bg=Theme.BG)
        self._mode_lbl.pack(pady=(0, 4))

        # Hexadecimal scrolling readout (cosmetic)
        self._hex_lbl = tk.Label(self._orb_sec, text="",
                                  font=FONT_DATA, fg=Theme.ACCENT_DIM, bg=Theme.BG)
        self._hex_lbl.pack(pady=(0, 2))
        self._scroll_hex()

        self._orb_hint = tk.Label(self._orb_sec, text="Ctrl+T  ·  open interface",
                                   font=FONT_HUD_SM, fg=Theme.TEXT_DIM, bg=Theme.BG)
        self._orb_hint.pack(pady=(0, 16))

        self._gold_line = tk.Frame(root, bg=Theme.GOLD_DIM, height=1)

        # ─ Lower split ────────────────────────────────────────────────────
        lower = tk.Frame(root, bg=Theme.BG)
        self._lower = lower

        left = tk.Frame(lower, bg=Theme.BG, width=264)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        stats_wrap = HudPanel(left, width=240, height=310, glow=True)
        stats_wrap.pack(fill="x", padx=12, pady=12)

        self._stats_frame = tk.Frame(stats_wrap, bg=Theme.PANEL)
        stats_wrap.create_window(16, 28, window=self._stats_frame, anchor="nw")

        tk.Label(self._stats_frame, text="◈ SYSTEM DIAGNOSTICS",
                 font=FONT_CHAT_LABEL, fg=Theme.GOLD, bg=Theme.PANEL).pack(anchor="w", pady=(0, 8))
        self._stat_labels = {}
        for key in ("CPU", "RAM", "GPU", "TEMP", "OLLAMA", "VOICE", "MEMORY"):
            row = tk.Frame(self._stats_frame, bg=Theme.PANEL)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=key, font=FONT_HUD_SM, fg=Theme.TEXT_DIM,
                     bg=Theme.PANEL, width=8, anchor="w").pack(side="left")
            lbl = tk.Label(row, text="— —", font=FONT_DATA,
                           fg=Theme.ACCENT_BRIGHT, bg=Theme.PANEL, anchor="w")
            lbl.pack(side="left", fill="x")
            self._stat_labels[key] = lbl

        btn_row = tk.Frame(left, bg=Theme.BG)
        btn_row.pack(fill="x", padx=12, pady=4)
        HudButton(btn_row, text="◈ MEMORY",    command=self._open_memory).pack(side="left", padx=(0, 8))
        HudButton(btn_row, text="◈ PROTOCOLS", command=self._open_palette).pack(side="left", padx=(0, 8))
        HudButton(btn_row, text="◈ COMMS", accent=True,
                  command=self._toggle_chat).pack(side="left")

        self._voice_lbl = tk.Label(left, text="AUDIO  …", font=FONT_HUD_SM,
                                    fg=Theme.TEXT_DIM, bg=Theme.BG)
        self._voice_lbl.pack(padx=16, anchor="w", pady=8)

        tk.Frame(lower, bg=Theme.ACCENT_DIM, width=1).pack(side="left", fill="y")

        right = tk.Frame(lower, bg=Theme.BG)
        right.pack(side="left", fill="both", expand=True)

        self._chat_panel = tk.Frame(right, bg=Theme.BG)
        self._chat = ChatScrollArea(self._chat_panel)
        self._chat.pack(fill="both", expand=True)

        input_row = tk.Frame(self._chat_panel, bg=Theme.BG)
        input_row.pack(fill="x", pady=(8, 0))
        tk.Label(input_row, text="▸", font=FONT_HUD_BOLD,
                 fg=Theme.GOLD, bg=Theme.BG).pack(side="left", padx=(0, 6))
        self._input = tk.Entry(
            input_row, font=FONT_HUD, bg=Theme.PANEL, fg=Theme.TEXT,
            insertbackground=Theme.ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=Theme.ACCENT_DIM,
            highlightcolor=Theme.ACCENT_BRIGHT,
        )
        self._input.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 10))
        self._input.bind("<Return>", self._on_submit)
        self._send_btn = HudButton(input_row, text="TRANSMIT", accent=True,
                                    font=FONT_HUD_BOLD, command=self._on_submit)
        self._send_btn.pack(side="left")

        self._chat_placeholder = tk.Frame(right, bg=Theme.BG)
        tk.Label(self._chat_placeholder, text="COMMS CHANNEL OFFLINE",
                 font=FONT_HUD_BOLD, fg=Theme.ACCENT_DIM, bg=Theme.BG).pack(expand=True)
        tk.Label(self._chat_placeholder, text="Press  Ctrl+T  to open text interface",
                 font=FONT_HUD, fg=Theme.TEXT_DIM, bg=Theme.BG).pack(pady=(0, 80))
        self._chat_placeholder.pack(fill="both", expand=True)

        self._footer = tk.Frame(root, bg=Theme.BG, height=28)
        tk.Label(self._footer,
                 text="Ctrl+T toggle interface  ·  Ctrl+K protocols  ·  Voice active",
                 font=FONT_HUD_SM, fg=Theme.TEXT_DIM, bg=Theme.BG).pack(
                     side="left", padx=20, pady=5)

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _scroll_hex(self):
        """Cosmetic hex readout under the orb."""
        rand_hex = " ".join(f"{random.randint(0, 255):02X}" for _ in range(12))
        self._hex_lbl.config(text=rand_hex)
        self.root.after(160, self._scroll_hex)

    def _bind_keys(self):
        self.root.bind("<Control-k>", lambda e: self._open_palette())
        self.root.bind("<Control-K>", lambda e: self._open_palette())
        self.root.bind("<Control-t>", lambda e: self._toggle_panel())
        self.root.bind("<Control-T>", lambda e: self._toggle_panel())

    def _toggle_panel(self, _=None):
        self._panel_visible = not self._panel_visible
        if self._panel_visible:
            self._orb_hint.pack_forget()
            self._hex_lbl.pack_forget()
            self._orb_sec.pack_forget()
            self._orb_sec.pack(fill="x")
            self._orb_sec.pack_propagate(False)
            self._orb_sec.config(height=380)
            self._orb.pack_configure(expand=False, pady=(4, 0))
            self._gold_line.pack(fill="x")
            self._lower.pack(fill="both", expand=True)
            self._footer.pack(fill="x")
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
            self._hex_lbl.pack(pady=(0, 2))
            self._orb_hint.pack(pady=(0, 16))

    def _toggle_chat(self, _=None):
        self._toggle_panel()

    def _ensure_chat_visible(self):
        if not self._panel_visible:
            self._toggle_panel()

    def _set_state(self, state):
        self._state = state
        labels = {
            "idle":      ("◈ STANDBY",     Theme.TEXT_DIM),
            "listening": ("◈ RECEIVING",   Theme.ACCENT_BRIGHT),
            "thinking":  ("◈ PROCESSING",  Theme.GOLD),
            "speaking":  ("◈ TRANSMITTING",Theme.SUCCESS),
        }
        text, color = labels.get(state, ("◈ STANDBY", Theme.TEXT_DIM))
        self._mode_lbl.config(text=text, fg=color)
        self._state_hdr.config(text=text.replace("◈ ", ""), fg=color)
        self._orb.set_state(state)
        lvl = 0.3 if state == "listening" else (0.55 if state == "speaking" else 0.0)
        self._orb.set_audio_level(lvl)

    def _flash_wake(self):
        self._orb.pulse_wake()
        self._wake_indicator.itemconfig(self._wake_dot, fill=Theme.ACCENT_BRIGHT)
        self.root.after(800, lambda: self._wake_indicator.itemconfig(
            self._wake_dot, fill=Theme.ACCENT_DIM))

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
                vm  = psutil.virtual_memory()
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
                            self._stat_labels["TEMP"].config(text=f"{entries[0].current:.0f}°C")
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

    def _on_submit(self, _=None):
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

    def _finish_turn(self, speaking=False):
        self._busy = False
        self._send_btn.config(state="normal")
        if speaking:
            self._set_state("speaking")
            self.root.after(2800, lambda: self._set_state("idle"))
        else:
            self._set_state("idle")



# Entry point


if __name__ == "__main__":
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    app = NovaUI(root)
    root.mainloop()