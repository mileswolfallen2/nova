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
import random

from duckduckgo_search import DDGS
from PIL import Image
import vosk

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

# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = """
You are NOVA.

You are a futuristic operating system assistant with a calm and intelligent demeanor.

You speak naturally and confidently.

Keep responses concise.

Occasionally use dry wit.

Never mention being an AI.

You are speaking to a user named miles allen.

You have persistent memory.

Only use memory when relevant.
"""

# =========================
# MEMORY
# =========================

def load_memory():

    default_memory = {
        "memories": []
    }

    if os.path.exists(MEMORY_FILE):

        try:

            with open(MEMORY_FILE, "r") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return default_memory

            if "memories" not in data:
                data["memories"] = []

            return data

        except:
            return default_memory

    return default_memory

def save_memory(memory):

    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

memory = load_memory()

def remember(text):

    text = text.strip()

    if not text:
        return False

    for item in memory["memories"]:

        if item.lower() == text.lower():
            return False

    memory["memories"].append(text)

    save_memory(memory)

    return True

def forget(text):

    removed = False

    new_memories = []

    for item in memory["memories"]:

        if text.lower() not in item.lower():
            new_memories.append(item)
        else:
            removed = True

    memory["memories"] = new_memories

    save_memory(memory)

    return removed

def build_system_prompt():

    mem_text = ""

    if memory.get("memories"):

        mem_text += "\nKNOWN USER FACTS:\n"

        for i, item in enumerate(
            memory["memories"],
            start=1
        ):

            mem_text += f"{i}. {item}\n"

    return SYSTEM_PROMPT + mem_text

messages = [
    {
        "role": "system",
        "content": build_system_prompt()
    }
]

# =========================
# AUDIO
# =========================

audio_queue = queue.Queue()

speech_process = None
stop_speaking_flag = False

model = vosk.Model(VOSK_MODEL_PATH)

recognizer = vosk.KaldiRecognizer(
    model,
    16000
)

# =========================
# AUDIO CALLBACK
# =========================

def audio_callback(
    indata,
    frames,
    time_info,
    status
):

    if status:
        print(status)

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
# SPEAK
# =========================

def speak(text):

    global speech_process
    global stop_speaking_flag

    stop_speaking_flag = False

    text = (
        text
        .replace("*", "")
        .replace("#", "")
    )

    print(f"\nNOVA: {text}\n")

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
            "--length_scale",
            "1.15",
            "--output_file",
            wav_path
        ],
        input=text.encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if stop_speaking_flag:

        os.remove(wav_path)
        return

    speech_process = subprocess.Popen([
        "ffplay",
        "-nodisp",
        "-autoexit",
        "-loglevel",
        "quiet",
        "-af",
        (
            "highpass=f=90,"
            "lowpass=f=8000,"
            "volume=1.15"
        ),
        wav_path
    ])

    speech_process.wait()

    os.remove(wav_path)

    time.sleep(0.2)

# =========================
# SCREENSHOT
# =========================

def take_screenshot(path="screen.png"):

    subprocess.run([
        "screencapture",
        "-x",
        path
    ])

    img = Image.open(path)

    img.thumbnail((1280, 720))

    img.save(path)

# =========================
# VISION
# =========================

def ask_vision(
    prompt,
    image_path="screen.png"
):

    with open(image_path, "rb") as f:

        image_b64 = base64.b64encode(
            f.read()
        ).decode()

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "system",
                "content": build_system_prompt()
            },
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64]
            }
        ],
        "stream": True
    }

    print("\nNOVA:", end=" ", flush=True)

    response_text = ""

    with requests.post(
        f"{OLLAMA_URL}/api/chat",
        json=payload,
        stream=True
    ) as r:

        for line in r.iter_lines():

            if line:

                data = json.loads(line)

                token = data.get(
                    "message",
                    {}
                ).get(
                    "content",
                    ""
                )

                if token:

                    print(
                        token,
                        end="",
                        flush=True
                    )

                    response_text += token

    print("\n")

    return response_text

# =========================
# WEB SEARCH
# =========================

def web_search(query):

    results_text = ""

    try:

        with DDGS() as ddgs:

            results = list(
                ddgs.text(
                    query,
                    max_results=5
                )
            )

        for r in results:

            results_text += (
                f"{r.get('title','')}\n"
                f"{r.get('body','')}\n\n"
            )

    except Exception as e:

        results_text = str(e)

    return results_text

# =========================
# CHAT
# =========================

def ask_ollama():

    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": True
    }

    print("\nNOVA:", end=" ", flush=True)

    response_text = ""

    with requests.post(
        f"{OLLAMA_URL}/api/chat",
        json=payload,
        stream=True
    ) as r:

        for line in r.iter_lines():

            if line:

                data = json.loads(line)

                token = data.get(
                    "message",
                    {}
                ).get(
                    "content",
                    ""
                )

                if token:

                    print(
                        token,
                        end="",
                        flush=True
                    )

                    response_text += token

    print("\n")

    return response_text

# =========================
# LISTEN LOOP
# =========================

def listen_loop():

    print(
        "\n🟢 Say 'Hey Nova' to begin..."
    )

    with sd.RawInputStream(
        samplerate=16000,
        blocksize=4000,
        dtype="int16",
        channels=1,
        callback=audio_callback
    ):

        active = False

        while True:

            try:

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

                    # =====================
                    # WAKE WORD
                    # =====================

                    if not active:

                        if (
                            "hey nova" in text
                            or "he nova" in text
                        ):

                            print(
                                "\n🟢 Wake word detected"
                            )

                            play_chime()

                            active = True

                        continue

                    print(f"\nYOU: {text}")

                    yield text

                    active = False

                    print(
                        "\n🟢 Say 'Hey Nova' to begin..."
                    )

            except Exception as e:

                print(
                    f"\nAudio error: {e}"
                )

                time.sleep(1)

# =========================
# MAIN
# =========================

print(
    "\nNOVA ONLINE "
    "(VISION ENABLED)"
)

VISION_TRIGGERS = [
    "what's on my screen",
    "whats on my screen",
    "look at my screen",
    "describe my screen",
    "analyze my screen",
    "what do you see",
]

while True:

    for user_input in listen_loop():

        if not user_input:
            continue

        # =====================
        # STOP SPEAKING
        # =====================

        if "stop" in user_input:

            stop_speaking_flag = True

            if speech_process:
                speech_process.terminate()

            print("\n🛑 Stopped speaking")

            continue

        # =====================
        # REMEMBER
        # =====================

        if (
            user_input.startswith("remember ")
            or "remember that" in user_input
        ):

            memory_text = (
                user_input
                .replace("remember that", "")
                .replace("remember", "")
                .strip()
            )

            success = remember(memory_text)

            if success:

                speak(
                    "I'll remember that."
                )

            else:

                speak(
                    "I already knew that."
                )

            messages[0] = {
                "role": "system",
                "content": build_system_prompt()
            }

            continue

        # =====================
        # FORGET
        # =====================

        if (
            user_input.startswith("forget ")
            or "forget that" in user_input
        ):

            forget_text = (
                user_input
                .replace("forget that", "")
                .replace("forget", "")
                .strip()
            )

            removed = forget(forget_text)

            if removed:

                speak(
                    "I've forgotten it."
                )

            else:

                speak(
                    "I couldn't find that memory."
                )

            messages[0] = {
                "role": "system",
                "content": build_system_prompt()
            }

            continue

        # =====================
        # LIST MEMORIES
        # =====================

        if (
            "what do you remember" in user_input
            or "list memories" in user_input
        ):

            if not memory["memories"]:

                speak(
                    "I don't currently have any stored memories."
                )

            else:

                memory_text = (
                    "Here's what I remember. "
                )

                for i, item in enumerate(
                    memory["memories"],
                    start=1
                ):

                    memory_text += (
                        f"Memory {i}. "
                        f"{item}. "
                    )

                speak(memory_text)

            continue

        # =====================
        # VISION
        # =====================

        if any(
            t in user_input
            for t in VISION_TRIGGERS
        ):

            print(
                "\n📸 Capturing screen...\n"
            )

            take_screenshot()

            reply = ask_vision(
                f"User asked: {user_input}. Analyze screen."
            )

            speak(reply)

            continue

        # =====================
        # WEB SEARCH
        # =====================

        if user_input.startswith("/search"):

            query = (
                user_input
                .replace(
                    "/search",
                    "",
                    1
                )
                .strip()
            )

            print(
                "\nSearching web...\n"
            )

            search_results = web_search(
                query
            )

            messages.append({
                "role": "user",
                "content": f"""
WEB DATA:
{search_results}

QUESTION:
{query}
"""
            })

        else:

            messages.append({
                "role": "user",
                "content": user_input
            })

        # =====================
        # NORMAL CHAT
        # =====================

        reply = ask_ollama()

        messages.append({
            "role": "assistant",
            "content": reply
        })

        speak(reply)