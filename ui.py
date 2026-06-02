#!/usr/bin/env python3
# NOVA — Graphical UI
# Run with: python ui.py
# Requires: pip install tkinter (usually built-in)
# Communicates with jarvis.py core via shared queue / direct import of logic

import tkinter as tk
import threading
import math
import time
import random
import json
import os
import sys
import requests
import re
import asyncio
import subprocess
import tempfile
import queue
import logging

from datetime import datetime

# ---------------------------------------------------------------------------
# Pull shared config + logic from jarvis.py without triggering its main loop.
# We monkey-patch sys.argv so argparse inside jarvis doesn't choke, then
# import only what we need.
# ---------------------------------------------------------------------------

_orig_argv = sys.argv
sys.argv = [sys.argv[0]]  # strip any ui.py args before jarvis parses

# Minimal stubs so jarvis.py top-level imports don't crash if vosk/sounddevice
# aren't needed here (they're for voice, not the UI).
import importlib, types

def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

for _stub in ["vosk", "sounddevice", "pyautogui"]:
    if _stub not in sys.modules:
        _stub_module(_stub)

# Give vosk stub enough surface area
sys.modules["vosk"].Model = lambda *a, **kw: None
sys.modules["vosk"].KaldiRecognizer = lambda *a, **kw: None
sys.modules["sounddevice"].RawInputStream = lambda **kw: None

# Now import the jarvis core (it won't start the main loop — that's guarded
# behind the STARTUP section at module level, but since we patched argv the
# argparse won't error and the STARTUP section still runs its print/check_ollama.
# To avoid that we import it slightly differently below.)

# Instead of importing jarvis directly (which runs startup code), we reproduce
# only the pieces we need: config constants, handle_user_input, ask_ollama,
# choose_command, run_command, speak, COMMANDS, etc.  We do this by exec-ing
# the file up to but not including the STARTUP block.

_JARVIS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis.py")

_jarvis_src = ""
if os.path.exists(_JARVIS_PATH):
    with open(_JARVIS_PATH, "r") as _f:
        _jarvis_src = _f.read()

# Chop off everything from the STARTUP comment onward so we don't re-run it
_CUT_MARKER = "# STARTUP"
_cut_idx = _jarvis_src.find(_CUT_MARKER)
if _cut_idx != -1:
    _jarvis_src = _jarvis_src[:_cut_idx]

_jarvis_ns = {"__name__": "__jarvis_core__", "__file__": _JARVIS_PATH}

try:
    exec(compile(_jarvis_src, _JARVIS_PATH, "exec"), _jarvis_ns)
    _core_loaded = True
except Exception as _e:
    _core_loaded = False
    print(f"[UI] Warning: could not load jarvis core: {_e}")

sys.argv = _orig_argv

# Pull symbols into this module's namespace
if _core_loaded:
    handle_user_input = _jarvis_ns.get("handle_user_input")
    ask_ollama        = _jarvis_ns.get("ask_ollama")
    choose_command    = _jarvis_ns.get("choose_command")
    obvious_action_decision = _jarvis_ns.get("obvious_action_decision")
    run_command       = _jarvis_ns.get("run_command")
    COMMANDS          = _jarvis_ns.get("COMMANDS", {})
    OLLAMA_URL        = _jarvis_ns.get("OLLAMA_URL", "http://localhost:11434")
    CHAT_MODEL        = _jarvis_ns.get("CHAT_MODEL", "llama3.2:latest")
    TTS_BACKEND       = _jarvis_ns.get("TTS_BACKEND", "edge")
    EDGE_TTS_VOICE    = _jarvis_ns.get("EDGE_TTS_VOICE", "en-GB-RyanNeural")
    synthesize_edge_tts = _jarvis_ns.get("synthesize_edge_tts")
    synthesize_piper  = _jarvis_ns.get("synthesize_piper")
    strip_sources     = _jarvis_ns.get("strip_sources", lambda t: t)
    memory            = _jarvis_ns.get("memory", {"memories": []})
else:
    # Fallback stubs so the UI still opens
    OLLAMA_URL  = "http://localhost:11434"
    CHAT_MODEL  = "llama3.2:latest"
    TTS_BACKEND = "edge"
    EDGE_TTS_VOICE = "en-GB-RyanNeural"
    COMMANDS    = {}
    memory      = {"memories": []}

    def handle_user_input(text): return "Core not loaded."
    def ask_ollama(text): return "Core not loaded."
    def strip_sources(t): return t


# ---------------------------------------------------------------------------
# UI response queue — jarvis worker thread posts results here
# ---------------------------------------------------------------------------
response_queue = queue.Queue()
speech_process = None


def ollama_online():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except:
        return False


def speak_text(text):
    global speech_process
    spoken = strip_sources(text)
    if not spoken:
        spoken = text

    suffix = ".mp3" if TTS_BACKEND == "edge" else ".wav"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            audio_path = f.name

        if TTS_BACKEND == "edge" and synthesize_edge_tts:
            asyncio.run(synthesize_edge_tts(spoken, audio_path))
        elif synthesize_piper:
            synthesize_piper(spoken, audio_path)
        else:
            return

        speech_process = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", audio_path]
        )
        speech_process.wait()
        try:
            os.remove(audio_path)
        except:
            pass
    except Exception as e:
        print(f"[UI TTS] {e}")


def process_input_threaded(text, on_start, on_done):
    """Run in a thread. Calls on_start(), processes, posts to queue, calls on_done()."""
    on_start()

    result_text = ""
    try:
        if _core_loaded and choose_command and obvious_action_decision and run_command and ask_ollama:
            decision = choose_command(text)
            decision = obvious_action_decision(text, decision)
            if decision.get("type") == "command":
                result_text = run_command(decision) or ""
            else:
                result_text = ask_ollama(text)
        else:
            # Minimal fallback: raw Ollama chat
            payload = {
                "model": CHAT_MODEL,
                "messages": [{"role": "user", "content": text}],
                "stream": False,
            }
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=30)
            result_text = r.json()["message"]["content"]
    except Exception as e:
        result_text = f"Error: {e}"

    result_text = result_text or "…"
    response_queue.put(result_text)
    on_done(result_text)

    # Speak in the same thread (non-blocking for UI since we're already threaded)
    speak_text(result_text)


# ---------------------------------------------------------------------------
# NOVA UI
# ---------------------------------------------------------------------------

class NovaUI:
    # ---- Palette -----------------------------------------------------------
    BG          = "#050A0F"
    PANEL       = "#080E14"
    ACCENT      = "#00CFFF"
    ACCENT2     = "#0066FF"
    ACCENT_DIM  = "#004466"
    TEXT        = "#C8E8F0"
    TEXT_DIM    = "#3A6070"
    DANGER      = "#FF3355"
    SUCCESS     = "#00FF99"
    RING_IDLE   = "#0A2030"
    RING_ACTIVE = "#00CFFF"

    def __init__(self, root):
        self.root = root
        self.root.title("NOVA")
        self.root.configure(bg=self.BG)
        self.root.geometry("900x700")
        self.root.minsize(700, 560)

        self._state   = "idle"   # idle | listening | thinking | speaking
        self._tick    = 0
        self._history = []       # list of (role, text)
        self._anim_id = None
        self._wave_offsets = [random.uniform(0, math.pi * 2) for _ in range(64)]

        self._build_layout()
        self._set_state("idle")
        self._animate()
        self._poll_queue()

        # Status check
        self.root.after(200, self._startup_check)

    # -----------------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------------
    def _build_layout(self):
        # Top bar
        top = tk.Frame(self.root, bg=self.BG, height=48)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)

        self._status_dot = tk.Canvas(top, width=12, height=12, bg=self.BG,
                                     highlightthickness=0)
        self._status_dot.pack(side="left", padx=(20, 6), pady=16)
        self._dot_oval = self._status_dot.create_oval(2, 2, 10, 10,
                                                       fill=self.TEXT_DIM,
                                                       outline="")

        tk.Label(top, text="N O V A", font=("Courier", 13, "bold"),
                 fg=self.ACCENT, bg=self.BG).pack(side="left")

        self._state_label = tk.Label(top, text="OFFLINE",
                                     font=("Courier", 9),
                                     fg=self.TEXT_DIM, bg=self.BG)
        self._state_label.pack(side="right", padx=20)

        self._time_label = tk.Label(top, text="",
                                    font=("Courier", 9),
                                    fg=self.TEXT_DIM, bg=self.BG)
        self._time_label.pack(side="right", padx=10)
        self._tick_clock()

        # Divider
        tk.Frame(self.root, bg=self.ACCENT_DIM, height=1).pack(fill="x")

        # Main area: sphere left, chat right
        main = tk.Frame(self.root, bg=self.BG)
        main.pack(fill="both", expand=True, padx=0, pady=0)

        # Left panel — sphere
        left = tk.Frame(main, bg=self.BG, width=300)
        left.pack(side="left", fill="y", padx=0)
        left.pack_propagate(False)

        self._sphere_canvas = tk.Canvas(left, width=300, height=300,
                                         bg=self.BG, highlightthickness=0)
        self._sphere_canvas.pack(pady=(30, 0))

        self._nova_label = tk.Label(left, text="NOVA",
                                    font=("Courier", 11, "bold"),
                                    fg=self.ACCENT, bg=self.BG)
        self._nova_label.pack(pady=(8, 0))

        self._mode_label = tk.Label(left, text="STANDBY",
                                    font=("Courier", 8),
                                    fg=self.TEXT_DIM, bg=self.BG)
        self._mode_label.pack()

        # Memory count
        self._mem_label = tk.Label(left, text="MEM: 0",
                                   font=("Courier", 8),
                                   fg=self.TEXT_DIM, bg=self.BG)
        self._mem_label.pack(pady=(20, 0))

        # Right panel — chat + input
        right = tk.Frame(main, bg=self.BG)
        right.pack(side="left", fill="both", expand=True, padx=(0, 0))

        # Vertical separator
        tk.Frame(main, bg=self.ACCENT_DIM, width=1).place(x=300, y=0,
                                                            relheight=1)

        # Chat scroll area
        chat_outer = tk.Frame(right, bg=self.BG)
        chat_outer.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        scrollbar = tk.Scrollbar(chat_outer, bg=self.BG,
                                  troughcolor=self.BG,
                                  activebackground=self.ACCENT_DIM,
                                  highlightthickness=0)
        scrollbar.pack(side="right", fill="y")

        self._chat_box = tk.Text(
            chat_outer,
            bg=self.PANEL,
            fg=self.TEXT,
            font=("Courier", 10),
            wrap="word",
            relief="flat",
            bd=0,
            padx=12, pady=10,
            state="disabled",
            yscrollcommand=scrollbar.set,
            selectbackground=self.ACCENT_DIM,
            insertbackground=self.ACCENT,
            highlightthickness=1,
            highlightbackground=self.ACCENT_DIM,
        )
        self._chat_box.pack(fill="both", expand=True)
        scrollbar.config(command=self._chat_box.yview)

        # Tags
        self._chat_box.tag_config("you",  foreground=self.ACCENT,
                                   font=("Courier", 10, "bold"))
        self._chat_box.tag_config("nova", foreground=self.SUCCESS,
                                   font=("Courier", 10, "bold"))
        self._chat_box.tag_config("you_text",  foreground=self.TEXT)
        self._chat_box.tag_config("nova_text", foreground=self.TEXT)
        self._chat_box.tag_config("sys",  foreground=self.TEXT_DIM,
                                   font=("Courier", 9, "italic"))
        self._chat_box.tag_config("err",  foreground=self.DANGER)

        # Input row
        input_row = tk.Frame(right, bg=self.BG)
        input_row.pack(fill="x", padx=12, pady=10)

        self._input = tk.Entry(
            input_row,
            bg=self.PANEL,
            fg=self.TEXT,
            font=("Courier", 11),
            relief="flat",
            bd=0,
            insertbackground=self.ACCENT,
            highlightthickness=1,
            highlightbackground=self.ACCENT_DIM,
            highlightcolor=self.ACCENT,
        )
        self._input.pack(side="left", fill="x", expand=True,
                          ipady=8, padx=(0, 8))
        self._input.bind("<Return>", self._on_submit)
        self._input.bind("<FocusIn>",
                          lambda e: self._input.config(
                              highlightbackground=self.ACCENT))
        self._input.bind("<FocusOut>",
                          lambda e: self._input.config(
                              highlightbackground=self.ACCENT_DIM))

        self._send_btn = tk.Button(
            input_row,
            text="SEND",
            font=("Courier", 10, "bold"),
            bg=self.ACCENT2,
            fg="#000000",
            activebackground=self.ACCENT,
            activeforeground="#000000",
            relief="flat",
            bd=0,
            padx=16, pady=8,
            cursor="hand2",
            command=self._on_submit,
        )
        self._send_btn.pack(side="left")

        # Bottom bar
        tk.Frame(self.root, bg=self.ACCENT_DIM, height=1).pack(fill="x")
        bottom = tk.Frame(self.root, bg=self.BG, height=28)
        bottom.pack(fill="x")
        bottom.pack_propagate(False)
        self._bottom_label = tk.Label(
            bottom, text="NOVA INTERFACE v1.0",
            font=("Courier", 8), fg=self.TEXT_DIM, bg=self.BG)
        self._bottom_label.pack(side="left", padx=20, pady=6)

    # -----------------------------------------------------------------------
    # State machine
    # -----------------------------------------------------------------------
    def _set_state(self, state):
        self._state = state
        labels = {
            "idle":      ("STANDBY",  self.TEXT_DIM, self.TEXT_DIM),
            "listening": ("LISTENING", self.ACCENT,   self.ACCENT),
            "thinking":  ("THINKING",  self.ACCENT2,  self.ACCENT2),
            "speaking":  ("SPEAKING",  self.SUCCESS,  self.SUCCESS),
        }
        mode_text, mode_color, dot_color = labels.get(
            state, ("STANDBY", self.TEXT_DIM, self.TEXT_DIM))

        self._mode_label.config(text=mode_text, fg=mode_color)
        self._state_label.config(text=mode_text)
        self._status_dot.itemconfig(self._dot_oval, fill=dot_color)

    # -----------------------------------------------------------------------
    # Sphere animation
    # -----------------------------------------------------------------------
    def _animate(self):
        self._tick += 1
        self._draw_sphere()
        self._anim_id = self.root.after(30, self._animate)

    def _draw_sphere(self):
        c = self._sphere_canvas
        c.delete("all")

        cx, cy, R = 150, 150, 90
        t = self._tick * 0.04

        state = self._state

        # Background glow
        if state in ("speaking", "listening"):
            glow_r = R + 28 + 8 * math.sin(t * 2)
            for i in range(5):
                alpha = int(30 - i * 5)
                gr = glow_r + i * 7
                col = self._lerp_color("#003050", self.BG, i / 5)
                c.create_oval(cx - gr, cy - gr, cx + gr, cy + gr,
                              outline=col, width=1)

        # Draw latitude arcs (horizontal rings)
        n_rings = 7
        for i in range(n_rings):
            lat = -1 + 2 * i / (n_rings - 1)  # -1 to 1
            y_pos = cy + lat * R
            r_ring = R * math.sqrt(max(0, 1 - lat * lat))
            if r_ring < 2:
                continue

            phase = t + i * 0.3
            if state == "thinking":
                squish = 0.85 + 0.15 * math.sin(phase * 1.7 + i)
            elif state in ("speaking", "listening"):
                squish = 0.7 + 0.3 * abs(math.sin(phase * 3 + i * 0.5))
            else:
                squish = 0.88 + 0.12 * math.sin(phase)

            rx = r_ring
            ry = r_ring * squish * 0.38

            dist_from_eq = abs(lat)
            brightness = 1.0 - dist_from_eq * 0.6
            if state == "speaking":
                brightness *= 0.7 + 0.3 * abs(math.sin(t * 4 + i))
            elif state == "thinking":
                brightness *= 0.6 + 0.4 * math.sin(t * 2 + i * 0.8)

            col = self._ring_color(brightness, state)
            lw = 1 + brightness * 1.5

            c.create_oval(cx - rx, y_pos - ry,
                          cx + rx, y_pos + ry,
                          outline=col, width=lw)

        # Draw longitude arcs (vertical)
        n_long = 8
        for i in range(n_long):
            angle = math.pi * i / n_long + t * 0.15
            points = []
            steps = 40
            for s in range(steps + 1):
                phi = math.pi * s / steps
                x3 = R * math.sin(phi) * math.cos(angle)
                y3 = -R * math.cos(phi)
                # Only draw front-facing part
                if math.cos(angle) >= -0.1 or True:
                    px = cx + x3
                    py = cy + y3
                    points.append((px, py))

            if len(points) > 2:
                dist = abs(math.cos(angle))
                brightness = 0.2 + 0.5 * dist
                if state == "speaking":
                    brightness += 0.3 * abs(math.sin(t * 3 + i))
                col = self._ring_color(brightness * 0.7, state)
                flat = [coord for pt in points for coord in pt]
                if len(flat) >= 4:
                    c.create_line(*flat, fill=col, width=1, smooth=True)

        # Core sphere fill (gradient simulation via concentric ovals)
        for i in range(12, 0, -1):
            frac = i / 12
            r2 = R * frac * 0.95
            if state == "speaking":
                col = self._lerp_color("#001520", "#003040", 1 - frac)
            elif state == "thinking":
                col = self._lerp_color("#001020", "#002535", 1 - frac)
            elif state == "listening":
                col = self._lerp_color("#001828", "#002840", 1 - frac)
            else:
                col = self._lerp_color("#000810", "#001520", 1 - frac)
            c.create_oval(cx - r2, cy - r2, cx + r2, cy + r2,
                          fill=col, outline="")

        # Redraw rings on top (front half)
        for i in range(n_rings):
            lat = -1 + 2 * i / (n_rings - 1)
            y_pos = cy + lat * R
            r_ring = R * math.sqrt(max(0, 1 - lat * lat))
            if r_ring < 2:
                continue
            phase = t + i * 0.3
            if state == "thinking":
                squish = 0.85 + 0.15 * math.sin(phase * 1.7 + i)
            elif state in ("speaking", "listening"):
                squish = 0.7 + 0.3 * abs(math.sin(phase * 3 + i * 0.5))
            else:
                squish = 0.88 + 0.12 * math.sin(phase)
            rx = r_ring
            ry = r_ring * squish * 0.38
            dist_from_eq = abs(lat)
            brightness = 1.0 - dist_from_eq * 0.6
            if state == "speaking":
                brightness *= 0.7 + 0.3 * abs(math.sin(t * 4 + i))
            col = self._ring_color(brightness, state)
            lw = 1 + brightness * 1.5
            c.create_arc(cx - rx, y_pos - ry, cx + rx, y_pos + ry,
                         start=0, extent=180,
                         outline=col, width=lw, style="arc")

        # Specular highlight
        hx, hy, hr = cx - R * 0.28, cy - R * 0.28, R * 0.18
        c.create_oval(hx - hr, hy - hr * 0.6,
                      hx + hr, hy + hr * 0.6,
                      fill="#0A3040", outline="")

        # Outer ring
        ring_col = self.RING_ACTIVE if state != "idle" else self.RING_IDLE
        lw = 2 if state != "idle" else 1
        if state == "speaking":
            pulse = R + 4 + 3 * math.sin(t * 5)
        else:
            pulse = R + 4
        c.create_oval(cx - pulse, cy - pulse, cx + pulse, cy + pulse,
                      outline=ring_col, width=lw)

        # Update memory label
        mem_count = len(memory.get("memories", []))
        self._mem_label.config(
            text=f"MEM: {mem_count}  |  {datetime.now().strftime('%H:%M')}",
            fg=self.TEXT_DIM)

    def _ring_color(self, brightness, state):
        if state == "speaking":
            base = (0, 255, 153)
        elif state == "thinking":
            base = (0, 102, 255)
        elif state == "listening":
            base = (0, 207, 255)
        else:
            base = (0, 100, 140)
        r = int(base[0] * brightness)
        g = int(base[1] * brightness)
        b = int(base[2] * brightness)
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _lerp_color(c1, c2, t):
        def parse(c):
            c = c.lstrip("#")
            return tuple(int(c[i:i+2], 16) for i in (0, 2, 4))
        r1, g1, b1 = parse(c1)
        r2, g2, b2 = parse(c2)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    # -----------------------------------------------------------------------
    # Clock
    # -----------------------------------------------------------------------
    def _tick_clock(self):
        self._time_label.config(text=datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    # -----------------------------------------------------------------------
    # Startup check
    # -----------------------------------------------------------------------
    def _startup_check(self):
        if ollama_online():
            self._append_chat("sys", "NOVA online. Ollama connected.\n")
            self._set_state("idle")
            self._status_dot.itemconfig(self._dot_oval, fill=self.SUCCESS)
        else:
            self._append_chat("err",
                "⚠  Ollama is offline. Start Ollama and restart.\n")
            self._set_state("idle")

    # -----------------------------------------------------------------------
    # Chat log helpers
    # -----------------------------------------------------------------------
    def _append_chat(self, kind, text):
        self._chat_box.config(state="normal")
        if kind == "you":
            self._chat_box.insert("end", "YOU  ", "you")
            self._chat_box.insert("end", text + "\n", "you_text")
        elif kind == "nova":
            self._chat_box.insert("end", "NOVA ", "nova")
            self._chat_box.insert("end", text + "\n", "nova_text")
        elif kind == "err":
            self._chat_box.insert("end", text + "\n", "err")
        else:
            self._chat_box.insert("end", text, "sys")
        self._chat_box.config(state="disabled")
        self._chat_box.see("end")

    # -----------------------------------------------------------------------
    # Input handling
    # -----------------------------------------------------------------------
    def _on_submit(self, event=None):
        text = self._input.get().strip()
        if not text:
            return
        if self._state in ("thinking", "speaking"):
            return  # busy

        self._input.delete(0, "end")
        self._append_chat("you", text)
        self._set_state("thinking")
        self._send_btn.config(state="disabled")

        t = threading.Thread(
            target=process_input_threaded,
            args=(
                text,
                lambda: None,
                lambda result: self.root.after(0, self._on_response_ready),
            ),
            daemon=True,
        )
        t.start()

    def _on_response_ready(self):
        # The actual text comes via response_queue
        pass

    # -----------------------------------------------------------------------
    # Queue polling — picks up results from the worker thread
    # -----------------------------------------------------------------------
    def _poll_queue(self):
        try:
            result = response_queue.get_nowait()
            self._append_chat("nova", result)
            self._set_state("speaking")
            self._send_btn.config(state="normal")
            # After a couple seconds flip back to idle
            self.root.after(2500, lambda: self._set_state("idle"))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = NovaUI(root)
    root.mainloop()