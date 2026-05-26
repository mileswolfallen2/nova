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
from datetime import datetime, timezone
from html.parser import HTMLParser

import argparse
import vosk
from PIL import Image

# =========================
# DEBUG FLAG
# =========================

_parser = argparse.ArgumentParser(description="NOVA Voice Assistant")
_parser.add_argument(
    "-d", "--debug",
    action="store_true",
    help="Enable debug output (web search results, memory saves, TTS sentences, etc.)"
)
_args = _parser.parse_args()
DEBUG = _args.debug

def dbg(tag: str, msg: str):
    """Print a debug line — only when -d is passed."""
    if DEBUG:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n  \033[90m[{timestamp}] [{tag}] {msg}\033[0m")

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

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nova_memory.json")

# How many days before a memory is considered stale (0 = never prune)
MEMORY_STALE_DAYS = 90

# Max conversation messages to keep (excluding system prompt)
MAX_MESSAGES = 20

# Keywords that suggest a web search is needed
SEARCH_KEYWORDS = [
    "today", "latest", "current", "news", "weather",
    "who won", "what happened", "price of", "how much is",
    "when is", "score", "stock", "update", "recent",
]

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

You are speaking to a user named Miles Allen.

You have persistent memory.

Only use memory when relevant.
"""

# =========================
# MEMORY
# =========================

VALID_CATEGORIES = ["preference", "fact", "task", "person", "general"]

def load_memory():
    default = {"memories": []}
    if not os.path.exists(MEMORY_FILE):
        dbg("MEMORY", f"No memory file at {MEMORY_FILE} — starting fresh")
        return default
    try:
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        if "memories" not in data:
            data["memories"] = []
        # Migrate old flat string entries
        migrated = []
        migrated_count = 0
        for item in data["memories"]:
            if isinstance(item, str):
                migrated.append({
                    "text": item,
                    "category": "general",
                    "created": datetime.now(timezone.utc).isoformat(),
                    "accessed": datetime.now(timezone.utc).isoformat(),
                    "access_count": 0,
                })
                migrated_count += 1
            else:
                migrated.append(item)
        data["memories"] = migrated
        dbg("MEMORY", f"Loaded {len(migrated)} memories from {MEMORY_FILE}"
            + (f" ({migrated_count} migrated from old format)" if migrated_count else ""))
        return data
    except Exception as e:
        print(f"[Memory] Load error: {e}")
        return default

def save_memory(mem):
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(mem, f, indent=2)
        dbg("MEMORY", f"Saved {len(mem.get('memories', []))} memories to {MEMORY_FILE}")
    except Exception as e:
        print(f"[Memory] Save error: {e}")

memory = load_memory()

def _prune_stale():
    """Remove memories older than MEMORY_STALE_DAYS that have never been accessed."""
    if MEMORY_STALE_DAYS <= 0:
        return
    cutoff = datetime.now(timezone.utc).timestamp() - (MEMORY_STALE_DAYS * 86400)
    before = len(memory["memories"])
    memory["memories"] = [
        m for m in memory["memories"]
        if (
            m.get("access_count", 0) > 0
            or datetime.fromisoformat(m["created"]).timestamp() > cutoff
        )
    ]
    pruned = before - len(memory["memories"])
    if pruned:
        print(f"[Memory] Pruned {pruned} stale memories.")
        dbg("MEMORY", f"Pruned {pruned} memories older than {MEMORY_STALE_DAYS} days with 0 accesses")
        save_memory(memory)

def remember(text, category="general"):
    text = text.strip()
    if not text:
        return False
    if category not in VALID_CATEGORIES:
        category = "general"
    # Dedup — case-insensitive
    for item in memory["memories"]:
        if item["text"].lower() == text.lower():
            return False
    entry = {
        "text": text,
        "category": category,
        "created": datetime.now(timezone.utc).isoformat(),
        "accessed": datetime.now(timezone.utc).isoformat(),
        "access_count": 0,
    }
    memory["memories"].append(entry)
    dbg("MEMORY", f"Storing [{category}]: '{text}'")
    save_memory(memory)
    return True

def forget(text):
    before = len(memory["memories"])
    memory["memories"] = [
        m for m in memory["memories"]
        if text.lower() not in m["text"].lower()
    ]
    removed = len(memory["memories"]) < before
    if removed:
        dbg("MEMORY", f"Forgot memories matching: '{text}'")
        save_memory(memory)
    return removed

def touch_memory(text):
    """Mark a memory as accessed (call when NOVA uses it in a response)."""
    for item in memory["memories"]:
        if text.lower() in item["text"].lower():
            item["accessed"] = datetime.now(timezone.utc).isoformat()
            item["access_count"] = item.get("access_count", 0) + 1
    save_memory(memory)

def build_system_prompt():
    _prune_stale()
    now = datetime.now()
    date_str = now.strftime("%A, %B %-d, %Y")   # e.g. "Sunday, May 24, 2026"
    time_str = now.strftime("%-I:%M %p")          # e.g. "11:35 PM"
    datetime_line = f"\nCurrent date and time: {date_str}, {time_str}\n"
    mem_text = datetime_line
    if memory.get("memories"):
        # Group by category
        grouped = {}
        for item in memory["memories"]:
            cat = item.get("category", "general")
            grouped.setdefault(cat, []).append(item["text"])
        mem_text += "\nKNOWN USER FACTS:\n"
        for cat, items in grouped.items():
            mem_text += f"\n[{cat.upper()}]\n"
            for i, text in enumerate(items, 1):
                mem_text += f"  {i}. {text}\n"
    return SYSTEM_PROMPT + mem_text

def auto_extract_memory(reply_text):
    """
    Ask the LLM to pull out any facts worth remembering from its own reply.
    Runs in background — does not block the main loop.
    """
    def _run():
        prompt = f"""You are a memory extraction assistant.

Given the following text (which may be from either the user or the assistant), extract any specific facts about the user that are worth remembering long-term (preferences, personal details, plans, names, specific words/items they want saved, etc.)

Reply with a JSON array of objects like:
[{{"text": "...", "category": "preference|fact|task|person|general"}}]

If there is nothing worth remembering, reply with an empty array: []

Do NOT include generic statements. Only concrete, user-specific facts.

REPLY:
{reply_text}
"""
        try:
            payload = {
                "model": CHAT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            }
            r = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=15,
            )
            raw = r.json().get("message", {}).get("content", "[]")
            # Strip markdown fences if present
            raw = re.sub(r"```[a-z]*", "", raw).replace("```", "").strip()
            facts = json.loads(raw)
            dbg("MEMORY", f"Auto-extract raw LLM response: {raw}")
            if not facts:
                dbg("MEMORY", "Auto-extract: nothing worth remembering in this reply")
            for fact in facts:
                if isinstance(fact, dict) and "text" in fact:
                    added = remember(fact["text"], fact.get("category", "general"))
                    if added:
                        print(f"[Memory] Auto-stored: {fact['text']}")
                    else:
                        dbg("MEMORY", f"Auto-extract: duplicate: '{fact['text']}'")
        except Exception as e:
            print(f"[Memory] Auto-extract error: {e}")
            dbg("MEMORY", f"Auto-extract full exception: {e}")

    threading.Thread(target=_run, daemon=True).start()

# =========================
# CONVERSATION HISTORY
# =========================

messages = [
    {"role": "system", "content": build_system_prompt()}
]

def trim_messages():
    """Keep system prompt + last MAX_MESSAGES messages."""
    global messages
    if len(messages) > MAX_MESSAGES + 1:
        messages = [messages[0]] + messages[-(MAX_MESSAGES):]

# =========================
# AUDIO
# =========================

audio_queue = queue.Queue()
speech_process = None
stop_speaking_flag = False

model_vosk = vosk.Model(VOSK_MODEL_PATH)
recognizer = vosk.KaldiRecognizer(model_vosk, 16000)

def audio_callback(indata, frames, time_info, status):
    if status:
        print(status)
    audio_queue.put(bytes(indata))

# =========================
# CHIME
# =========================

def play_chime():
    subprocess.run(["afplay", "/System/Library/Sounds/Hero.aiff"])

# =========================
# SPEAK (STREAMED TTS)
# =========================

tts_queue = queue.Queue()
_tts_worker_running = False

def _tts_worker():
    """Background thread: pulls sentences from tts_queue and speaks them in order."""
    global speech_process, stop_speaking_flag
    while True:
        sentence = tts_queue.get()
        if sentence is None:  # Poison pill — stop worker
            break
        if stop_speaking_flag:
            tts_queue.task_done()
            continue
        _speak_sentence(sentence)
        tts_queue.task_done()

def _speak_sentence(text):
    global speech_process, stop_speaking_flag
    text = text.replace("*", "").replace("#", "").strip()
    if not text:
        return
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    subprocess.run(
        [
            "piper",
            "--model", VOICE_MODEL,
            "--length_scale", "1.15",
            "--output_file", wav_path,
        ],
        input=text.encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if stop_speaking_flag:
        os.remove(wav_path)
        return
    speech_process = subprocess.Popen([
        "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
        "-af", "highpass=f=90,lowpass=f=8000,volume=1.15",
        wav_path,
    ])
    speech_process.wait()
    try:
        os.remove(wav_path)
    except Exception:
        pass
    time.sleep(0.1)

_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()

def _split_sentences(text):
    """Split text into speakable sentences."""
    # Split on . ! ? followed by space or end, but keep abbreviations somewhat intact
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]

def speak_streamed(stream_generator):
    """
    Accepts a generator that yields tokens.
    Buffers tokens into sentences and queues each for TTS as soon as it's complete,
    so audio starts before the full response is done generating.
    """
    global stop_speaking_flag
    stop_speaking_flag = False

    buffer = ""
    full_text = ""

    sentence_end = re.compile(r'[.!?](\s|$)')

    for token in stream_generator:
        if stop_speaking_flag:
            break
        buffer += token
        full_text += token

        # Check if we have at least one complete sentence in the buffer
        while sentence_end.search(buffer):
            match = sentence_end.search(buffer)
            end_idx = match.end()
            sentence = buffer[:end_idx].strip()
            buffer = buffer[end_idx:]
            if sentence:
                dbg("TTS", f"Queuing sentence: '{sentence}'")
                tts_queue.put(sentence)

    # Speak any remaining text
    if buffer.strip() and not stop_speaking_flag:
        dbg("TTS", f"Queuing remainder: '{buffer.strip()}'")
        tts_queue.put(buffer.strip())

    return full_text

def speak(text):
    """Speak a static string (for short canned responses)."""
    global stop_speaking_flag
    stop_speaking_flag = False
    print(f"\nNOVA: {text}\n")
    tts_queue.put(text)
    tts_queue.join()  # Wait until spoken

# =========================
# WEB SEARCH (fixed)
# =========================

class _DDGParser(HTMLParser):
    """Minimal HTML parser to extract DuckDuckGo result snippets."""
    def __init__(self):
        super().__init__()
        self.results = []
        self._in_result = False
        self._current = {}
        self._capture_title = False
        self._capture_body = False
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        classes = attr_dict.get("class", "")
        if "result__title" in classes:
            self._capture_title = True
        if "result__snippet" in classes:
            self._capture_body = True

    def handle_endtag(self, tag):
        if self._capture_title and tag in ("a", "h2"):
            self._capture_title = False
        if self._capture_body and tag == "a":
            self._capture_body = False
            if self._current:
                self.results.append(dict(self._current))
                self._current = {}

    def handle_data(self, data):
        data = data.strip()
        if not data:
            return
        if self._capture_title:
            self._current["title"] = self._current.get("title", "") + data
        if self._capture_body:
            self._current["body"] = self._current.get("body", "") + data

def web_search(query):
    """
    Fetch DuckDuckGo results via direct HTTP — no third-party library needed.
    Falls back to a simple news search if HTML parsing yields nothing.
    """
    results_text = ""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        parser = _DDGParser()
        parser.feed(html)
        for r in parser.results[:5]:
            title = r.get("title", "")
            body = r.get("body", "")
            if title or body:
                results_text += f"{title}\n{body}\n\n"
    except Exception as e:
        results_text = f"Search error: {e}"

    # Fallback: if parsing got nothing, return the raw snippet via a different approach
    if not results_text.strip():
        try:
            # Try the DuckDuckGo Instant Answer API (no auth needed)
            ia_url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
            req2 = urllib.request.Request(ia_url, headers=headers)
            with urllib.request.urlopen(req2, timeout=8) as resp2:
                data = json.loads(resp2.read().decode())
            abstract = data.get("AbstractText", "")
            answer = data.get("Answer", "")
            related = " ".join(
                r.get("Text", "") for r in data.get("RelatedTopics", [])[:3]
                if isinstance(r, dict)
            )
            results_text = "\n".join(filter(None, [abstract, answer, related]))
        except Exception as e2:
            results_text = f"Fallback search error: {e2}"

    final = results_text.strip() or "No results found."
    dbg("SEARCH", f"Results ({len(final)} chars):\n{final[:800]}{'...' if len(final) > 800 else ''}")
    return final

def _should_search(text):
    """Heuristic: does this query likely need live web data?"""
    text_lower = text.lower()
    matched = [kw for kw in SEARCH_KEYWORDS if kw in text_lower]
    if matched:
        dbg("SEARCH", f"Auto-search triggered by keywords: {matched}")
    return bool(matched)

# =========================
# SCREENSHOT + VISION
# =========================

def take_screenshot(path="screen.png"):
    subprocess.run(["screencapture", "-x", path])
    img = Image.open(path)
    img.thumbnail((1280, 720))
    img.save(path)

def ask_vision_streamed(prompt, image_path="screen.png"):
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": prompt, "images": [image_b64]},
        ],
        "stream": True,
    }
    print("\nNOVA:", end=" ", flush=True)

    def _gen():
        with requests.post(
            f"{OLLAMA_URL}/api/chat", json=payload, stream=True
        ) as r:
            for line in r.iter_lines():
                if line:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        print(token, end="", flush=True)
                        yield token
        print("\n")

    return speak_streamed(_gen())

# =========================
# CHAT (STREAMED)
# =========================

def ask_ollama_streamed():
    trim_messages()
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": True,
    }
    print("\nNOVA:", end=" ", flush=True)

    def _gen():
        with requests.post(
            f"{OLLAMA_URL}/api/chat", json=payload, stream=True
        ) as r:
            for line in r.iter_lines():
                if line:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        print(token, end="", flush=True)
                        yield token
        print("\n")

    return speak_streamed(_gen())

# =========================
# LISTEN LOOP
# =========================

def listen_loop():
    print("\n🟢 Say 'Hey Nova' to begin...")
    with sd.RawInputStream(
        samplerate=16000,
        blocksize=4000,
        dtype="int16",
        channels=1,
        callback=audio_callback,
    ):
        active = False
        while True:
            try:
                data = audio_queue.get()
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "").lower().strip()
                    if not text:
                        continue
                    if not active:
                        if "hey nova" in text or "he nova" in text:
                            print("\n🟢 Wake word detected")
                            play_chime()
                            active = True
                        continue
                    print(f"\nYOU: {text}")
                    yield text
                    active = False
                    print("\n🟢 Say 'Hey Nova' to begin...")
            except Exception as e:
                print(f"\nAudio error: {e}")
                time.sleep(1)

# =========================
# VISION TRIGGERS
# =========================

VISION_TRIGGERS = [
    "what's on my screen",
    "whats on my screen",
    "look at my screen",
    "describe my screen",
    "analyze my screen",
    "what do you see",
]

# =========================
# MAIN
# =========================

print("\nNOVA ONLINE (VISION + STREAMED TTS ENABLED)")
if DEBUG:
    print("\n  \033[90m[DEBUG MODE ON] -d flag active. You will see search results, memory operations, and TTS sentences.\033[0m")
    dbg("MEMORY", f"Memory file location: {MEMORY_FILE}")
    dbg("MEMORY", f"Current memories loaded: {len(memory.get('memories', []))}")
    if memory.get("memories"):
        for i, m in enumerate(memory["memories"], 1):
            dbg("MEMORY", f"  {i}. [{m.get('category','?')}] {m['text']}")

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
            # Drain the TTS queue
            while not tts_queue.empty():
                try:
                    tts_queue.get_nowait()
                    tts_queue.task_done()
                except Exception:
                    break
            print("\n🛑 Stopped speaking")
            continue

        # =====================
        # REMEMBER
        # =====================
        if user_input.startswith("remember ") or "remember that" in user_input:
            memory_text = (
                user_input
                .replace("remember that", "")
                .replace("remember", "")
                .strip()
            )
            # Check for category hint e.g. "remember that I prefer dark mode as preference"
            category = "general"
            for cat in VALID_CATEGORIES:
                if f"as {cat}" in memory_text:
                    memory_text = memory_text.replace(f"as {cat}", "").strip()
                    category = cat
                    break
            success = remember(memory_text, category)
            if success:
                dbg("MEMORY", f"User explicitly stored: '{memory_text}' [{category}]")
                # Let NOVA confirm naturally via the chat model instead of a canned line
                messages[0] = {"role": "system", "content": build_system_prompt()}
                messages.append({
                    "role": "user",
                    "content": f"Please confirm you have remembered: {memory_text}"
                })
                reply = ask_ollama_streamed()
                messages.append({"role": "assistant", "content": reply})
                messages[0] = {"role": "system", "content": build_system_prompt()}
            else:
                speak("I already have that stored.")
            continue

        # =====================
        # FORGET
        # =====================
        if user_input.startswith("forget ") or "forget that" in user_input:
            forget_text = (
                user_input
                .replace("forget that", "")
                .replace("forget", "")
                .strip()
            )
            removed = forget(forget_text)
            speak("I've forgotten it." if removed else "I couldn't find that memory.")
            messages[0] = {"role": "system", "content": build_system_prompt()}
            continue

        # =====================
        # LIST MEMORIES
        # =====================
        if "what do you remember" in user_input or "list memories" in user_input:
            if not memory["memories"]:
                speak("I don't currently have any stored memories.")
            else:
                grouped = {}
                for item in memory["memories"]:
                    cat = item.get("category", "general")
                    grouped.setdefault(cat, []).append(item["text"])
                parts = []
                for cat, items in grouped.items():
                    parts.append(f"{cat}: " + ". ".join(items))
                speak("Here's what I remember. " + ". ".join(parts))
            continue

        # =====================
        # VISION
        # =====================
        if any(t in user_input for t in VISION_TRIGGERS):
            print("\n📸 Capturing screen...\n")
            take_screenshot()
            reply = ask_vision_streamed(
                f"User asked: {user_input}. Analyze screen."
            )
            messages.append({"role": "assistant", "content": reply})
            auto_extract_memory(reply)
            continue

        # =====================
        # WEB SEARCH
        # =====================
        do_search = (
            user_input.startswith("/search")
            or _should_search(user_input)
        )

        if do_search:
            query = user_input.replace("/search", "", 1).strip()
            print("\n🔍 Searching web...\n")
            search_results = web_search(query)
            dbg("SEARCH", f"Query sent to model: {query}")
            messages.append({
                "role": "user",
                "content": (
                    f"WEB SEARCH RESULTS FOR: {query}\n\n"
                    f"{search_results}\n\n"
                    f"Using the above results, answer: {query}"
                ),
            })
        else:
            messages.append({"role": "user", "content": user_input})

        # =====================
        # CHAT
        # =====================
        reply = ask_ollama_streamed()
        messages.append({"role": "assistant", "content": reply})

        # Refresh system prompt with latest memories after each turn
        messages[0] = {"role": "system", "content": build_system_prompt()}

        # Auto-extract from both the user's message and NOVA's reply (background)
        auto_extract_memory(user_input)
        auto_extract_memory(reply)