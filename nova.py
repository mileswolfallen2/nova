#!/usr/bin/env python3

import requests
import json
import subprocess
import tempfile
import os
import queue
import sounddevice as sd
import base64
import time
import re
import threading
import urllib.parse
import urllib.request
import logging
import pyautogui
import psutil
import argparse
import vosk

from datetime import datetime
from PIL import Image
from playwright.sync_api import sync_playwright

# =========================
# ARGUMENTS
# =========================

_parser = argparse.ArgumentParser(description="NOVA Voice Assistant")

_parser.add_argument(
    "-d", "--debug",
    action="store_true",
    help="Enable debug output"
)

_parser.add_argument(
    "-t", "--text",
    action="store_true",
    help="Run NOVA in text mode"
)

_args = _parser.parse_args()

DEBUG = _args.debug
TEXT_MODE = _args.text

# =========================
# DEBUG
# =========================

def dbg(tag, msg):
    if DEBUG:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{timestamp}] [{tag}] {msg}")

# =========================
# CONFIG
# =========================

OLLAMA_URL = "http://localhost:11434"

CHAT_MODEL = "llama3.2:latest"
VISION_MODEL = "llava:7b"

VOICE_MODEL = os.path.expanduser(
    "~/jarvis/voices/en_US-lessac-high.onnx"
)

VOSK_MODEL_PATH = os.path.expanduser(
    "~/jarvis/stt/vosk-model-small-en-us-0.15"
)

MEMORY_FILE = "nova_memory.json"

LOG_FILE = "nova.log"

WEATHER_LOCATION = "Toronto"

SAFE_MODE = True

WAKE_TIMEOUT = 10

WAKE_WORDS = [
    "hey nova",
    "nova",
    "computer",
    "jarvis"
]

# =========================
# LOGGING
# =========================

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = """
You are NOVA.

You are a futuristic operating system assistant.

Be concise.

Never mention being an AI.

You are speaking to Miles Allen.
"""

# =========================
# MEMORY
# =========================

memory = {"memories": []}

def load_memory():
    global memory

    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                memory = json.load(f)
        except:
            memory = {"memories": []}

def save_memory():
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

def remember(text):
    memory["memories"].append(text)
    save_memory()

def forget(text):
    memory["memories"] = [
        m for m in memory["memories"]
        if text.lower() not in m.lower()
    ]
    save_memory()

def edit_memory(old, new):
    for i, m in enumerate(memory["memories"]):
        if old.lower() in m.lower():
            memory["memories"][i] = new
            save_memory()
            return True
    return False

load_memory()

# =========================
# OLLAMA CHECK
# =========================

def check_ollama():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)

        if r.status_code == 200:
            print("🟢 Ollama online")
            return True

    except:
        pass

    print("🔴 Ollama offline")
    return False

# =========================
# SYSTEM STATUS
# =========================

def get_system_status():
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent

        return (
            f"CPU usage is {cpu} percent. "
            f"Memory usage is {ram} percent. "
            f"Disk usage is {disk} percent."
        )

    except Exception as e:
        return str(e)

# =========================
# WEATHER
# =========================

def get_weather():
    try:
        url = f"https://wttr.in/{WEATHER_LOCATION}?format=j1"

        r = requests.get(url, timeout=5)

        data = r.json()

        current = data["current_condition"][0]

        temp = current["temp_C"]
        desc = current["weatherDesc"][0]["value"]

        return f"It is currently {temp} degrees Celsius with {desc}."

    except Exception as e:
        return str(e)

# =========================
# AUDIO
# =========================

audio_queue = queue.Queue()

model_vosk = vosk.Model(VOSK_MODEL_PATH)

recognizer = vosk.KaldiRecognizer(
    model_vosk,
    16000
)

speech_process = None

def audio_callback(indata, frames, time_info, status):
    audio_queue.put(bytes(indata))

# =========================
# CHIME
# =========================

def play_chime():
    subprocess.run([
        "afplay",
        "/System/Library/Sounds/Hero.aiff"
    ])

# =========================
# TTS
# =========================

def speak(text):
    global speech_process

    print(f"\nNOVA: {text}\n")

    if TEXT_MODE:
        return

    with tempfile.NamedTemporaryFile(
        suffix=".wav",
        delete=False
    ) as f:
        wav_path = f.name

    subprocess.run(
        [
            "piper",
            "--model",
            VOICE_MODEL,
            "--output_file",
            wav_path,
        ],
        input=text.encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    speech_process = subprocess.Popen([
        "ffplay",
        "-nodisp",
        "-autoexit",
        "-loglevel",
        "quiet",
        wav_path,
    ])

    speech_process.wait()

    try:
        os.remove(wav_path)
    except:
        pass

# =========================
# BROWSER AUTOMATION
# =========================

playwright_instance = None
browser = None
page = None

def init_browser():
    global playwright_instance
    global browser
    global page

    if browser:
        return

    playwright_instance = sync_playwright().start()

    browser = playwright_instance.chromium.launch(
        headless=False
    )

    page = browser.new_page()

def open_website(url):
    try:
        init_browser()

        if not url.startswith("http"):
            url = "https://" + url

        page.goto(url)

        return f"Opened {url}"

    except Exception as e:
        return str(e)

def google_search(query):
    try:
        init_browser()

        encoded = urllib.parse.quote_plus(query)

        page.goto(
            f"https://www.google.com/search?q={encoded}"
        )

        return f"Searching Google for {query}"

    except Exception as e:
        return str(e)

def youtube_search(query):
    try:
        init_browser()

        encoded = urllib.parse.quote_plus(query)

        page.goto(
            f"https://www.youtube.com/results?search_query={encoded}"
        )

        return f"Searching YouTube for {query}"

    except Exception as e:
        return str(e)

# =========================
# DISCORD AUTOMATION
# =========================

def open_discord():
    subprocess.Popen([
        "open",
        "-a",
        "Discord"
    ])

def send_discord_message(user, message):
    try:
        open_discord()

        time.sleep(3)

        pyautogui.hotkey("command", "k")

        time.sleep(1)

        pyautogui.write(user)

        pyautogui.press("enter")

        time.sleep(1)

        pyautogui.write(message)

        if SAFE_MODE:
            speak(
                f"Message prepared for {user}. Type or say send to confirm."
            )

            if TEXT_MODE:
                confirmation = input("CONFIRM: ").lower()
            else:
                confirmation = next(listen_loop())

            if "send" not in confirmation:
                pyautogui.press("esc")
                return "Cancelled"

        pyautogui.press("enter")

        return f"Message sent to {user}"

    except Exception as e:
        return str(e)

# =========================
# DISCORD INTENT INFERENCE
# =========================

DISCORD_INTENT_PROMPT = """
Extract a Discord message intent from the user input.
Return ONLY a JSON object with keys "recipient" and "message".
If the input does not describe sending a message to someone, return: {"recipient": null, "message": null}

Examples:
  "send a message to Griffin saying hey what's up" -> {"recipient": "Griffin", "message": "hey what's up"}
  "tell Sarah happy birthday" -> {"recipient": "Sarah", "message": "happy birthday"}
  "message Alex saying the meeting is at 3" -> {"recipient": "Alex", "message": "the meeting is at 3"}
  "what's the weather" -> {"recipient": null, "message": null}

Return raw JSON only. No explanation.
"""

def infer_discord_intent(user_input):
    try:
        payload = {
            "model": CHAT_MODEL,
            "messages": [
                {"role": "system", "content": DISCORD_INTENT_PROMPT},
                {"role": "user", "content": user_input}
            ],
            "stream": False,
        }

        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
        )

        raw = r.json()["message"]["content"].strip()
        data = json.loads(raw)

        recipient = data.get("recipient")
        message = data.get("message")

        if recipient and message:
            dbg("DISCORD_INFER", f"recipient={recipient} message={message}")
            return recipient, message

    except Exception as e:
        dbg("DISCORD_INFER", f"Failed: {e}")

    return None, None

# =========================
# SPOTIFY CONTROL
# =========================

def spotify_play():
    script = '''
    tell application "Spotify"
        play
    end tell
    '''

    subprocess.run([
        "osascript",
        "-e",
        script
    ])

    return "Spotify resumed"

def spotify_pause():
    script = '''
    tell application "Spotify"
        pause
    end tell
    '''

    subprocess.run([
        "osascript",
        "-e",
        script
    ])

    return "Spotify paused"

def spotify_next():
    script = '''
    tell application "Spotify"
        next track
    end tell
    '''

    subprocess.run([
        "osascript",
        "-e",
        script
    ])

    return "Skipping track"

# =========================
# CHAT
# =========================

messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT
    }
]

def ask_ollama(user_input):
    messages.append({
        "role": "user",
        "content": user_input
    })

    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": False,
    }

    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json=payload,
    )

    reply = r.json()["message"]["content"]

    messages.append({
        "role": "assistant",
        "content": reply
    })

    return reply

# =========================
# VOICE LOOP
# =========================

def listen_loop():
    print("\n🟢 Say wake word...")

    with sd.RawInputStream(
        samplerate=16000,
        blocksize=4000,
        dtype="int16",
        channels=1,
        callback=audio_callback,
    ):

        active = False
        wake_time = 0

        while True:
            data = audio_queue.get()

            if recognizer.AcceptWaveform(data):
                result = json.loads(
                    recognizer.Result()
                )

                text = result.get(
                    "text",
                    ""
                ).lower().strip()

                if not text:
                    continue

                if active and (
                    time.time() - wake_time > WAKE_TIMEOUT
                ):
                    active = False
                    print("⏳ Wake timeout")

                if not active:
                    if any(
                        w in text
                        for w in WAKE_WORDS
                    ):
                        print("🟢 Wake word detected")
                        play_chime()
                        active = True
                        wake_time = time.time()

                    continue

                yield text

                active = False

# =========================
# TEXT LOOP
# =========================

def text_loop():
    print("\n💬 TEXT MODE ENABLED")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input(
                "YOU: "
            ).strip().lower()

            if not user_input:
                continue

            if user_input in [
                "exit",
                "quit"
            ]:
                print("\n👋 Goodbye")
                break

            yield user_input

        except KeyboardInterrupt:
            print("\n👋 Goodbye")
            break

# =========================
# STARTUP
# =========================

print("\nNOVA ONLINE")

if TEXT_MODE:
    print("⌨️ Running in TEXT MODE (-t)")

if not check_ollama():
    exit(1)

# =========================
# MAIN LOOP
# =========================

input_source = (
    text_loop()
    if TEXT_MODE
    else listen_loop()
)

DISCORD_KEYWORDS = [
    "send a message to",
    "send discord message",
    "tell ",
    "message ",
    "discord ",
]

while True:
    for user_input in input_source:

        print(f"\nYOU: {user_input}")

        logging.info(
            f"USER: {user_input}"
        )

        # STOP

        if "stop" in user_input:
            if speech_process:
                speech_process.terminate()

            continue

        # WEATHER

        if "weather" in user_input:
            speak(get_weather())
            continue

        # STATUS

        if "system status" in user_input:
            speak(get_system_status())
            continue

        # SPOTIFY

        if "pause spotify" in user_input:
            speak(spotify_pause())
            continue

        if "play spotify" in user_input:
            speak(spotify_play())
            continue

        if "next song" in user_input:
            speak(spotify_next())
            continue

        # GOOGLE

        if user_input.startswith("google "):
            query = user_input.replace(
                "google ",
                ""
            )

            speak(
                google_search(query)
            )

            continue

        # YOUTUBE

        if user_input.startswith("youtube "):
            query = user_input.replace(
                "youtube ",
                ""
            )

            speak(
                youtube_search(query)
            )

            continue

        # WEBSITE

        if user_input.startswith(
            "open website "
        ):
            url = user_input.replace(
                "open website ",
                ""
            )

            speak(
                open_website(url)
            )

            continue

        # DISCORD

        if any(kw in user_input for kw in DISCORD_KEYWORDS):
            recipient, msg = infer_discord_intent(user_input)

            if recipient and msg:
                result = send_discord_message(recipient, msg)
                speak(result)
            else:
                speak("I couldn't figure out who to message or what to say.")

            continue

        # MEMORY

        if user_input.startswith(
            "remember "
        ):
            remember(
                user_input.replace(
                    "remember ",
                    ""
                )
            )

            speak("Memory stored")

            continue

        if user_input.startswith(
            "forget "
        ):
            forget(
                user_input.replace(
                    "forget ",
                    ""
                )
            )

            speak("Forgotten")

            continue

        if user_input.startswith(
            "edit memory"
        ):

            try:
                parts = user_input.replace(
                    "edit memory",
                    ""
                ).split(" to ")

                old = parts[0].strip()
                new = parts[1].strip()

                if edit_memory(old, new):
                    speak("Memory updated")
                else:
                    speak("Memory not found")

            except:
                speak("Could not edit memory")

            continue

        # CHAT

        reply = ask_ollama(user_input)

        logging.info(
            f"NOVA: {reply}"
        )

        speak(reply)