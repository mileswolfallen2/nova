#!/usr/bin/env python3
# NOVA Voice Assistant

import requests
import asyncio
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


# ARGUMENTS

# Simple command-line arguments for debug mode and text mode (no TTS, just print responses)DO NOT REMOVE THIS I NEED IT FOR TESTING THE NEW FEATURES WITHOUT HAVING TO SPEAK THEM OUT LOUD EVERY TIME I EM GOING TO LOOS MY SANITY IF I HAVE TO KEEP SPEAKING OUT LOUD EVERY TIME I WANT TO TEST A CHANGE PLEASE JUST LET ME TYPE IT OUT INSTEAD THANK YOU
_parser = argparse.ArgumentParser(description="NOVA Voice Assistant")

_parser.add_argument(
    "-d", "--debug", action="store_true", help="Enable debug output"
)

_parser.add_argument(
    "-t", "--text", action="store_true", help="Run NOVA in text mode"
)

_args = _parser.parse_args()

DEBUG = _args.debug
TEXT_MODE = _args.text


# DEBUG


def dbg(tag, msg):
    if DEBUG:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{timestamp}] [{tag}] {msg}")


# CONFIG
# need a ui to chage this stuff will do later but for now just edit the variables here

OLLAMA_URL = "http://localhost:11434"

CHAT_MODEL = "llama3.2:latest"
VISION_MODEL = "llava:7b"

TTS_BACKEND = "edge"  # "edge" or "piper"
EDGE_TTS_VOICE = "en-GB-RyanNeural"

VOICE_MODEL = os.path.expanduser("~/jarvis/voices/en_US-lessac-high.onnx")

VOSK_MODEL_PATH = os.path.expanduser(
    "~/jarvis/stt/vosk-model-small-en-us-0.15"
)

MEMORY_FILE = "nova_memory.json"

LOG_FILE = "nova.log"

WEATHER_LOCATION = "Toronto"

SAFE_MODE = True

WAKE_TIMEOUT = 10

WAKE_WORDS = ["hey nova", "nova", "computer", "jarvis"]


  
# LOGGING
  

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


  
# SYSTEM PROMPT
  

SYSTEM_PROMPT = """
You are NOVA.

You are a system assistant.
You are a refined British-style computer assistant.
Speak calmly, intelligently, and with dry wit.
Be concise, composed, and slightly formal.
Never claim you performed an action unless a command actually did it.
Be concise.

Never mention being an AI.

You are speaking to Miles Allen.
When the user asks for an action, the command router will handle it before chat.
If you are chatting, do not claim that you opened apps, controlled websites,
sent messages, played music, changed settings, or performed system actions.
"""


  
# MEMORY
  

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
        m for m in memory["memories"] if text.lower() not in m.lower()
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


  
# OLLAMA CHECK
  
# for my sanity to not see 100000000 erres and lose my mind every time I try to test a change without having ollama running which is like 90% of the time when im developing new features why do i do this to my self
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


  
# SYSTEM STATUS
  


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


  
# WEATHER
  


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


  
# AUDIO
  

audio_queue = queue.Queue()

model_vosk = vosk.Model(VOSK_MODEL_PATH)

recognizer = vosk.KaldiRecognizer(model_vosk, 16000)

speech_process = None


def audio_callback(indata, frames, time_info, status):
    audio_queue.put(bytes(indata))


  
# CHIME
  
# need to replace this with a custom chime sound eventually but for now this is fine and it works so im not gonna mess with it but if i whant this on windos i need to chang it
def play_chime():
    subprocess.run(["afplay", "/System/Library/Sounds/Hero.aiff"])


  
# TTS
  

async def synthesize_edge_tts(text, audio_path):
    import edge_tts

    communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
    await communicate.save(audio_path)


def synthesize_piper(text, audio_path):
    subprocess.run(
        [
            "piper",
            "--model",
            VOICE_MODEL,
            "--output_file",
            audio_path,
        ],
        input=text.encode(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def speak(text):
    global speech_process

    print(f"\nNOVA: {text}\n")

    if TEXT_MODE:
        return

    suffix = ".mp3" if TTS_BACKEND == "edge" else ".wav"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        audio_path = f.name

    try:
        if TTS_BACKEND == "edge":
            asyncio.run(synthesize_edge_tts(text, audio_path))
        else:
            synthesize_piper(text, audio_path)
    except Exception as e:
        dbg("TTS", f"{TTS_BACKEND} failed: {e}")
        try:
            synthesize_piper(text, audio_path)
        except Exception as fallback_error:
            dbg("TTS", f"piper fallback failed: {fallback_error}")
            try:
                os.remove(audio_path)
            except:
                pass
            return

    speech_process = subprocess.Popen(
        [
            "ffplay",
            "-nodisp",
            "-autoexit",
            "-loglevel",
            "quiet",
            audio_path,
        ]
    )

    speech_process.wait()

    try:
        os.remove(audio_path)
    except:
        pass


  
# BROWSER — INIT
  

playwright_instance = None
browser = None
page = None


def init_browser():
    global playwright_instance, browser, page

    if browser:
        return

    playwright_instance = sync_playwright().start()
    browser = playwright_instance.chromium.launch(headless=False)
    page = browser.new_page()
    print("🌐 Browser ready")


  
# BROWSER — BASIC HELPERS
  


def open_website(url):
    try:
        init_browser()
        if not url.startswith("http"):
            url = "https://" + url
        page.goto(url, wait_until="domcontentloaded")
        return f"Opened {url}"
    except Exception as e:
        return str(e)


def google_search(query):
    try:
        init_browser()
        encoded = urllib.parse.quote_plus(query)
        page.goto(
            f"https://www.google.com/search?q={encoded}",
            wait_until="domcontentloaded",
        )
        return f"Searching Google for {query}"
    except Exception as e:
        return str(e)


def youtube_search(query):
    try:
        init_browser()
        encoded = urllib.parse.quote_plus(query)
        page.goto(
            f"https://www.youtube.com/results?search_query={encoded}",
            wait_until="domcontentloaded",
        )
        return f"Searching YouTube for {query}"
    except Exception as e:
        return str(e)


def play_youtube_music(query):
    try:
        init_browser()
        encoded = urllib.parse.quote_plus(query or "music")
        page.goto(
            f"https://www.youtube.com/results?search_query={encoded}",
            wait_until="domcontentloaded",
        )
        time.sleep(2)

        for text in ["Accept all", "I agree", "No thanks"]:
            try:
                page.get_by_text(text, exact=True).click(timeout=1500)
                time.sleep(1)
                break
            except:
                pass

        selectors = [
            "ytd-video-renderer a#video-title",
            "a#video-title",
            "ytd-rich-grid-media a#video-title-link",
        ]

        for selector in selectors:
            try:
                first_video = page.locator(selector).first
                first_video.wait_for(state="visible", timeout=10000)
                title = first_video.inner_text().strip()
                first_video.click()
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                return f"Playing {title or query} on YouTube."
            except Exception as e:
                dbg("YOUTUBE", f"{selector} failed: {e}")

        return "I opened YouTube, but I couldn't start the first video."

    except Exception as e:
        return str(e)


def browser_click(selector):
    try:
        init_browser()

        click_attempts = [
            lambda: page.click(selector, timeout=3000),
            lambda: page.get_by_role("button", name=selector).click(timeout=3000),
            lambda: page.get_by_role("link", name=selector).click(timeout=3000),
            lambda: page.get_by_label(selector).click(timeout=3000),
            lambda: page.get_by_text(selector, exact=True).first.click(timeout=3000),
            lambda: page.get_by_text(selector).first.click(timeout=3000),
        ]

        last_error = None
        for attempt in click_attempts:
            try:
                attempt()
                return f"Clicked '{selector}'"
            except Exception as e:
                last_error = e

        raise last_error
    except Exception as e:
        return str(e)


def browser_type(selector, text):
    try:
        init_browser()

        type_attempts = [
            lambda: page.fill(selector, text, timeout=3000),
            lambda: page.get_by_placeholder(selector).fill(text, timeout=3000),
            lambda: page.get_by_label(selector).fill(text, timeout=3000),
            lambda: page.get_by_role("textbox", name=selector).fill(text, timeout=3000),
        ]

        last_error = None
        for attempt in type_attempts:
            try:
                attempt()
                return f"Typed into '{selector}'"
            except Exception as e:
                last_error = e

        raise last_error
    except Exception as e:
        return str(e)


def browser_read_page():
    try:
        init_browser()
        title = page.title()
        url = page.url
        content = page.evaluate(
            """() => {
            const clone = document.body.cloneNode(true);
            clone.querySelectorAll('script, style, noscript, svg').forEach(el => el.remove());
            return clone.innerText.replace(/\\s+/g, ' ').trim().slice(0, 3000);
        }"""
        )
        return f"Page: {title} ({url})\n\n{content}"
    except Exception as e:
        return str(e)


def browser_interactive_snapshot():
    try:
        return page.evaluate(
            """() => {
            const items = [];
            const candidates = Array.from(document.querySelectorAll(
                'a, button, input, textarea, select, [role="button"], [role="link"], [role="textbox"]'
            ));

            for (const el of candidates.slice(0, 80)) {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                if (
                    rect.width < 1 ||
                    rect.height < 1 ||
                    style.visibility === 'hidden' ||
                    style.display === 'none'
                ) {
                    continue;
                }

                const label = (
                    el.innerText ||
                    el.value ||
                    el.getAttribute('aria-label') ||
                    el.getAttribute('placeholder') ||
                    el.getAttribute('name') ||
                    el.getAttribute('title') ||
                    ''
                ).replace(/\\s+/g, ' ').trim().slice(0, 100);

                const tag = el.tagName.toLowerCase();
                const role = el.getAttribute('role') || '';
                const type = el.getAttribute('type') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const name = el.getAttribute('name') || '';
                const id = el.id || '';

                items.push({ tag, role, type, label, placeholder, name, id });
            }

            return JSON.stringify(items.slice(0, 40), null, 2);
        }"""
        )
    except Exception as e:
        dbg("BROWSER", f"Interactive snapshot failed: {e}")
        return "[]"


  
# BROWSER — AGENTIC LOOP
  


def extract_url(text):
    match = re.search(r"https?://\S+", text)
    if match:
        return match.group(0).rstrip(".,)")
    return None


def ask_form_model(prompt):
    payload = {
        "model": CHAT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer form questions accurately and briefly. "
                    "Return only the answer text. No explanation."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0},
    }

    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=20)
        answer = r.json()["message"]["content"].strip()
        answer = re.sub(r"^['\"]|['\"]$", "", answer)
        return answer
    except Exception as e:
        dbg("FORM", f"Answer model failed: {e}")
        return ""


def default_form_answer(label):
    lower_label = label.lower()
    if "email" in lower_label:
        return "miles@example.com"
    if "name" in lower_label:
        return "Miles Allen"
    if "phone" in lower_label:
        return "555-555-5555"
    if "age" in lower_label:
        return "18"
    if "date" in lower_label:
        return datetime.now().strftime("%m/%d/%Y")

    answer = ask_form_model(
        f"Question: {label}\nGive the shortest accurate answer that should go in the form."
    )

    if answer:
        return answer

    return "I don't know"


def choose_form_option(label, options):
    if not options:
        return None

    option_list = "\n".join(f"- {option}" for option in options)
    answer = ask_form_model(
        "Choose the best option for this form question.\n\n"
        f"Question: {label}\n"
        f"Options:\n{option_list}\n\n"
        "Return exactly one option from the list."
    )

    for option in options:
        if answer.lower().strip() == option.lower().strip():
            return option

    for option in options:
        if option.lower().strip() in answer.lower():
            return option

    return options[0]


def fill_google_form(goal):
    url = extract_url(goal)
    if not url:
        return None

    init_browser()
    page.goto(url, wait_until="domcontentloaded")
    time.sleep(2)

    if "docs.google.com/forms" not in page.url:
        return None

    filled = 0
    selected = 0
    questions = page.locator('div[role="listitem"]')
    question_count = questions.count()

    for i in range(question_count):
        question = questions.nth(i)
        try:
            label = question.inner_text(timeout=2000).splitlines()[0]
        except:
            label = "question"

        fields = question.locator(
            'input[type="text"], input[type="email"], '
            'input[type="number"], textarea'
        )

        for j in range(fields.count()):
            field = fields.nth(j)
            try:
                if field.is_visible() and field.input_value() == "":
                    field.fill(default_form_answer(label))
                    filled += 1
            except Exception as e:
                dbg("FORM", f"Fill failed: {e}")

        choices = question.locator(
            'div[role="radio"]:not([aria-disabled="true"]), '
            'div[role="checkbox"]:not([aria-disabled="true"])'
        )

        try:
            choice_count = choices.count()
            if choice_count and choices.first.is_visible():
                options = []
                for j in range(choice_count):
                    choice = choices.nth(j)
                    option = (
                        choice.get_attribute("aria-label")
                        or choice.inner_text(timeout=1000)
                    )
                    option = re.sub(r"\s+", " ", option).strip()
                    if option:
                        options.append(option)

                selected_option = choose_form_option(label, options)
                selected_index = 0
                if selected_option in options:
                    selected_index = options.index(selected_option)

                choice = choices.nth(selected_index)
                checked = choice.get_attribute("aria-checked")
                if checked != "true":
                    choice.click()
                    selected += 1
        except Exception as e:
            dbg("FORM", f"Choice failed: {e}")

    should_submit = any(
        word in goal.lower()
        for word in ["submit", "send the form", "turn it in"]
    )

    if should_submit:
        try:
            page.get_by_text("Submit", exact=True).click(timeout=5000)
            return (
                "Filled the form and submitted it. "
                f"Filled {filled} fields and selected {selected} choices."
            )
        except Exception as e:
            dbg("FORM", f"Submit failed: {e}")
            return (
                "Filled the form, but I could not submit it. "
                f"Filled {filled} fields and selected {selected} choices."
            )

    if filled or selected:
        return (
            "Filled the form. "
            f"Filled {filled} fields and selected {selected} choices. "
            "I did not submit it."
        )

    return "I opened the form, but I could not find fillable questions."


def run_browser_agent(goal):
    """
    Multi-step browser agent. The LLM decides actions one at a time
    until it returns 'done' or max_steps is reached.
    Handles goals like 'go to YouTube and play lofi music'.
    """
    try:
        init_browser()
        form_result = fill_google_form(goal)
        if form_result:
            return form_result

        max_steps = 10
        step = 0

        while step < max_steps:
            step += 1

            current_url = page.url if page else "about:blank"
            current_title = page.title() if page else ""

            # Grab a brief snapshot of visible text for context
            try:
                snapshot = page.evaluate(
                    """() => {
                    const clone = document.body.cloneNode(true);
                    clone.querySelectorAll('script,style,noscript,svg').forEach(el => el.remove());
                    return clone.innerText.replace(/\\s+/g, ' ').trim().slice(0, 1500);
                }"""
                )
            except:
                snapshot = ""

            interactive = browser_interactive_snapshot()

            prompt = f"""You are controlling a real web browser to accomplish this goal: "{goal}"

Current page: "{current_title}" at {current_url}
Visible page text (first 1500 chars):
{snapshot}

Visible interactive elements:
{interactive}

Decide the single best next action. Respond ONLY with one JSON object from the options below:
  {{"action": "navigate", "url": "https://..."}}
  {{"action": "click", "selector": "CSS selector or exact visible button/link text"}}
  {{"action": "type", "selector": "CSS selector or placeholder text", "text": "text to type"}}
  {{"action": "press", "key": "Enter"}}
  {{"action": "scroll", "direction": "down"}}
  {{"action": "back"}}
  {{"action": "forward"}}
  {{"action": "wait", "seconds": 2}}
  {{"action": "done", "summary": "brief description of what was accomplished"}}

Tips:
- If the user did not provide a URL, work on the current page.
- Prefer exact visible button/link/input text from the interactive elements list.
- On YouTube, click the video title text to play it (e.g. the first search result title).
- After navigating to a new page, issue a wait action to let it load before interacting.
- If a cookie/consent banner appears, click the accept or dismiss button first.
- When the goal is fully complete, return done.

Return raw JSON only. No explanation. No markdown fences."""

            payload = {
                "model": CHAT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "format": "json",
                "options": {"temperature": 0},
                "stream": False,
            }

            r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload)
            raw = r.json()["message"]["content"].strip()

            # Strip markdown fences if the model wraps the JSON
            raw = re.sub(
                r"^```json|^```|```$", "", raw, flags=re.MULTILINE
            ).strip()

            dbg("AGENT", f"Step {step}: {raw}")

            try:
                action = json.loads(clean_json(raw))
            except json.JSONDecodeError:
                dbg("AGENT", f"Bad JSON on step {step}, skipping")
                continue

            a = action.get("action")

            if a == "navigate":
                url = action.get("url", "")
                if not url.startswith("http"):
                    url = "https://" + url
                page.goto(url, wait_until="domcontentloaded")

            elif a == "click":
                sel = action.get("selector", "")
                try:
                    page.click(sel, timeout=5000)
                except:
                    try:
                        page.get_by_text(sel).first.click()
                    except Exception as e:
                        dbg("AGENT", f"Click failed: {e}")

            elif a == "type":
                sel = action.get("selector", "")
                text = action.get("text", "")
                try:
                    page.fill(sel, text)
                except:
                    try:
                        page.get_by_placeholder(sel).fill(text)
                    except Exception as e:
                        dbg("AGENT", f"Type failed: {e}")

            elif a == "press":
                page.keyboard.press(action.get("key", "Enter"))

            elif a == "scroll":
                direction = action.get("direction", "down")
                page.keyboard.press(
                    "PageDown" if direction == "down" else "PageUp"
                )

            elif a == "back":
                page.go_back(wait_until="domcontentloaded")

            elif a == "forward":
                page.go_forward(wait_until="domcontentloaded")

            elif a == "wait":
                secs = min(action.get("seconds", 2), 5)  # cap at 5s
                time.sleep(secs)

            elif a == "done":
                return action.get("summary", "Done.")

            else:
                return f"Unknown action: {a}"

            # Small pause between steps so pages can settle
            time.sleep(1)

        return "Reached the maximum number of steps."

    except Exception as e:
        dbg("AGENT", f"run_browser_agent failed: {e}")
        return str(e)


  
# DISCORD AUTOMATION
  


def open_discord():
    subprocess.Popen(["open", "-a", "Discord"])


# Holds a pending discord message waiting for confirmation
pending_discord = {"recipient": None, "message": None}


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
                f"Message to {user} ready. Say send to confirm or cancel to abort."
            )
            pending_discord["recipient"] = user
            pending_discord["message"] = message
            return None  # Signal: waiting for confirmation

        pyautogui.press("enter")
        return f"Message sent to {user}"

    except Exception as e:
        return str(e)


def confirm_discord_send():
    pending_discord["recipient"] = None
    pending_discord["message"] = None
    pyautogui.press("enter")
    return "Message sent."


def cancel_discord_send():
    pending_discord["recipient"] = None
    pending_discord["message"] = None
    pyautogui.press("escape")
    return "Message cancelled."


  
# SPOTIFY CONTROL
  


def spotify_play():
    script = 'tell application "Spotify" to play'
    subprocess.run(["osascript", "-e", script])
    return "Spotify resumed"


def spotify_pause():
    script = 'tell application "Spotify" to pause'
    subprocess.run(["osascript", "-e", script])
    return "Spotify paused"


def spotify_next():
    script = 'tell application "Spotify" to next track'
    subprocess.run(["osascript", "-e", script])
    return "Skipping track"


  
# COMMAND ROUTER
  

def command_stop_speaking():
    if speech_process:
        speech_process.terminate()
    return None


def command_send_discord_message(recipient, message):
    return send_discord_message(recipient, message)


def command_confirm_discord_send():
    if not pending_discord["recipient"]:
        return "No Discord message is waiting for confirmation."
    return confirm_discord_send()


def command_cancel_discord_send():
    if not pending_discord["recipient"]:
        return "No Discord message is waiting for cancellation."
    return cancel_discord_send()


def command_remember(text):
    remember(text)
    return "Memory stored"


def command_forget(text):
    forget(text)
    return "Forgotten"


def command_edit_memory(old, new):
    if edit_memory(old, new):
        return "Memory updated"
    return "Memory not found"


COMMANDS = {
    "stop_speaking": {
        "description": "Stop NOVA's current spoken response or audio playback.",
        "args": {},
        "function": command_stop_speaking,
    },
    "get_weather": {
        "description": "Get the current weather for the configured location.",
        "args": {},
        "function": get_weather,
    },
    "get_system_status": {
        "description": "Report CPU, memory, and disk usage.",
        "args": {},
        "function": get_system_status,
    },
    "spotify_play": {
        "description": "Resume or play Spotify.",
        "args": {},
        "function": spotify_play,
    },
    "spotify_pause": {
        "description": "Pause Spotify.",
        "args": {},
        "function": spotify_pause,
    },
    "spotify_next": {
        "description": "Skip to the next Spotify track.",
        "args": {},
        "function": spotify_next,
    },
    "google_search": {
        "description": "Search Google for a query.",
        "args": {"query": "The search query."},
        "function": google_search,
    },
    "youtube_search": {
        "description": "Search YouTube for a query.",
        "args": {"query": "The search query."},
        "function": youtube_search,
    },
    "play_youtube_music": {
        "description": "Search YouTube and start playing the first music/video result.",
        "args": {
            "query": "What to play on YouTube, like '80s music' or 'lofi beats'.",
        },
        "function": play_youtube_music,
        "pre_response": "On it.",
    },
    "open_website": {
        "description": "Open a website URL in the browser.",
        "args": {"url": "The website domain or URL."},
        "function": open_website,
    },
    "browser_click": {
        "description": "Click an element on the current browser page.",
        "args": {
            "selector": "A CSS selector or exact visible button/link text.",
        },
        "function": browser_click,
    },
    "browser_type": {
        "description": "Type text into an input on the current browser page.",
        "args": {
            "selector": "A CSS selector or input placeholder.",
            "text": "The text to type.",
        },
        "function": browser_type,
    },
    "browser_read_page": {
        "description": "Read the title, URL, and visible text from the current browser page.",
        "args": {},
        "function": browser_read_page,
    },
    "run_browser_agent": {
        "description": (
            "Use the browser agent for multi-step browser tasks like "
            "clicking, scrolling, reading pages, navigating, or playing media."
        ),
        "args": {"goal": "The full browser task the user wants done."},
        "function": run_browser_agent,
        "pre_response": "On it.",
    },
    "send_discord_message": {
        "description": "Prepare a Discord message to a recipient.",
        "args": {
            "recipient": "The Discord user or channel to message.",
            "message": "The message text to send.",
        },
        "function": command_send_discord_message,
    },
    "confirm_discord_send": {
        "description": "Confirm and send the pending Discord message.",
        "args": {},
        "function": command_confirm_discord_send,
    },
    "cancel_discord_send": {
        "description": "Cancel the pending Discord message.",
        "args": {},
        "function": command_cancel_discord_send,
    },
    "remember": {
        "description": "Store something in NOVA's memory for later.",
        "args": {"text": "The memory to store."},
        "function": command_remember,
    },
    "forget": {
        "description": "Remove memories containing this text.",
        "args": {"text": "The text to remove from memory."},
        "function": command_forget,
    },
    "edit_memory": {
        "description": "Replace an existing memory with a new memory.",
        "args": {
            "old": "Text to find in the existing memory.",
            "new": "The replacement memory text.",
        },
        "function": command_edit_memory,
    },
}


def command_specs():
    specs = []
    for name, command in COMMANDS.items():
        specs.append(
            {
                "name": name,
                "description": command["description"],
                "args": command["args"],
            }
        )
    return specs


def clean_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        return match.group(0)
    return raw


def first_url(text):
    match = re.search(r"https?://\S+", text)
    if match:
        return match.group(0).rstrip(".,)")
    return None


def extract_music_query(text):
    lowered = text.lower()
    match = re.search(r"\bplay\s+(.+)", text, flags=re.IGNORECASE)
    query = match.group(1).strip() if match else "music"

    query = re.sub(
        r"\b(on|in)\s+(youtube|youtueb|yt|a browser|the browser)\b",
        "",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"\b(open|launch|start|a|the|browser|please|can you|could you)\b",
        "",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\s+", " ", query).strip(" .")

    if not query or query == lowered:
        query = "music"

    return query


def extract_google_query(text):
    query = re.sub(
        r"\b(thanks|thenks|thank you|please|plz)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r".*?\b(?:google|search google|search for|look up|find)\b",
        "",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"\b(open|launch|go to|and|for|on|the|a|browser)\b",
        "",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"\s+", " ", query).strip(" .")
    return query


def obvious_action_decision(user_input, decision):
    text = user_input.lower()
    url = first_url(user_input)
    is_command = decision.get("type") == "command"

    greetings = ["hi", "hello", "hey", "yo", "sup"]
    if text.strip(" .!?") in greetings:
        return {"type": "chat"}

    chat_question_words = [
        "what time",
        "what itme",
        "tell me",
        "explain",
        "why",
        "how",
        "who",
        "when",
        "where",
    ]
    if any(phrase in text for phrase in chat_question_words) and not url:
        command_name = decision.get("command")
        if command_name in [
            "get_system_status",
            "get_weather",
            "spotify_play",
            "spotify_pause",
            "spotify_next",
            "stop_speaking",
        ]:
            return {"type": "chat"}

    if decision.get("command") == "get_system_status":
        status_words = [
            "system status",
            "cpu",
            "ram",
            "memory usage",
            "disk usage",
            "computer status",
            "performance",
        ]
        if not any(word in text for word in status_words):
            return {"type": "chat"}

    if decision.get("command") == "get_weather":
        if "weather" not in text and "temperature" not in text:
            return {"type": "chat"}

    music_words = ["music", "song", "songs", "playlist", "video"]
    browser_words = ["browser", "youtube", "youtueb", "yt"]
    google_words = ["google", "search google", "search for", "look up"]
    current_page_action_words = [
        "click",
        "press",
        "type",
        "fill",
        "scroll",
        "read the page",
        "what is on this page",
        "what's on this page",
        "open this",
        "select",
        "choose",
        "search",
        "log in",
        "login",
        "sign in",
        "submit",
        "go back",
        "go forward",
    ]

    if "google" in text and "search" in text:
        query = extract_google_query(user_input)
        if query:
            return {
                "type": "command",
                "command": "google_search",
                "args": {"query": query},
            }

    if "play" in text and any(word in text for word in music_words):
        if any(word in text for word in browser_words) or "youtube" not in text:
            return {
                "type": "command",
                "command": "play_youtube_music",
                "args": {"query": extract_music_query(user_input)},
            }

    if url:
        agent_words = [
            "fill",
            "form",
            "click",
            "type",
            "submit",
            "read",
            "answer",
            "complete",
        ]
        if any(word in text for word in agent_words):
            return {
                "type": "command",
                "command": "run_browser_agent",
                "args": {"goal": user_input},
            }

        if not is_command:
            return {
                "type": "command",
                "command": "open_website",
                "args": {"url": url},
            }

    if (
        not is_command
        and "open" in text
        and any(word in text for word in browser_words)
    ):
        return {
            "type": "command",
            "command": "run_browser_agent",
            "args": {"goal": user_input},
        }

    if not is_command and any(word in text for word in google_words):
        query = extract_google_query(user_input)
        if query:
            return {
                "type": "command",
                "command": "google_search",
                "args": {"query": query},
            }

    if any(word in text for word in current_page_action_words):
        return {
            "type": "command",
            "command": "run_browser_agent",
            "args": {"goal": user_input},
        }

    return decision


def choose_command(user_input):
    pending = pending_discord["recipient"] is not None
    pending_note = "No Discord message is pending."
    if pending:
        pending_note = (
            "A Discord message is waiting for confirmation. "
            "Use confirm_discord_send for yes/send/confirm, and "
            "cancel_discord_send for no/cancel/anything that rejects it."
        )

    prompt = f"""
You are NOVA's command router.

Pick exactly one of these options:
1. Return a command call when the user wants NOVA to perform an available action.
2. Return chat when the user is just talking, asking a general question, or no command fits.

The user may make typos, speak casually, or start with words like "no" or
"actually". Ignore that filler if an action request follows it.

Available commands:
{json.dumps(command_specs(), indent=2)}

Context:
{pending_note}

Return ONLY raw JSON in one of these forms:
{{"type": "command", "command": "command_name", "args": {{}}}}
{{"type": "chat"}}

Rules:
- For greetings like "hi", "hello", and "hey", return chat.
- For normal questions, return chat unless the user clearly requests one of the
  available commands.
- Only choose get_system_status if the user asks for system status, CPU, RAM,
  memory usage, disk usage, computer status, or performance.
- Only choose get_weather if the user asks for weather or temperature.
- Use only command names from the available commands list.
- Extract all required args from the user's words.
- For run_browser_agent, pass the full user request as goal.
- If the user asks to play music, songs, or a video on YouTube, choose
  play_youtube_music and extract the requested style/song as query.
- If the user asks to open a browser and play music but does not name a site,
  choose play_youtube_music.
- If the user asks to open a browser and play/search/watch/navigate/click/read,
  choose run_browser_agent instead of chat.
- If the user asks to open Google and search for something, choose
  google_search and extract the search terms.
- If the user asks to click, type, fill, scroll, read, select, search, log in,
  sign in, or submit without giving a URL, choose run_browser_agent and use the
  current browser page.
- If the user asks for YouTube plus playing music or a video, choose
  play_youtube_music, even if YouTube is misspelled.
- If the user only asks to search YouTube, choose youtube_search.
- If the user only asks to open a specific website, choose open_website.
- If the user asks what you can do or how commands/tools work, return chat.
- If a required arg is missing, return chat.
- Do not explain your choice.

Examples:
User input: hi can you open youtueb and play music
Output: {{"type": "command", "command": "play_youtube_music", "args": {{"query": "music"}}}}

User input: no open a browser and play music on youtube
Output: {{"type": "command", "command": "play_youtube_music", "args": {{"query": "music"}}}}

User input: can you open a browser and play 80s music
Output: {{"type": "command", "command": "play_youtube_music", "args": {{"query": "80s music"}}}}

User input: youtube woodworking
Output: {{"type": "command", "command": "youtube_search", "args": {{"query": "woodworking"}}}}

User input: thenks open google and search for phots
Output: {{"type": "command", "command": "google_search", "args": {{"query": "phots"}}}}

User input: go to https://example.com/form and fill out the form
Output: {{"type": "command", "command": "run_browser_agent", "args": {{"goal": "go to https://example.com/form and fill out the form"}}}}

User input: click sign in
Output: {{"type": "command", "command": "run_browser_agent", "args": {{"goal": "click sign in"}}}}

User input: type miles into the username box
Output: {{"type": "command", "command": "run_browser_agent", "args": {{"goal": "type miles into the username box"}}}}

User input: can you tell me why you do not use your skills?
Output: {{"type": "chat"}}

User input: hi
Output: {{"type": "chat"}}

User input: can you tell me whut itme it is in alstaley if it is 10:53 in minasota
Output: {{"type": "chat"}}

User input: {user_input}
"""

    payload = {
        "model": CHAT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "options": {"temperature": 0},
        "stream": False,
    }

    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload)
        raw = r.json()["message"]["content"]
        decision = json.loads(clean_json(raw))
        if decision.get("type") == "command":
            if decision.get("command") not in COMMANDS:
                return {"type": "chat"}
        dbg("ROUTER", json.dumps(decision))
        return decision
    except Exception as e:
        dbg("ROUTER", f"Failed: {e}")
        return {"type": "chat"}


def run_command(decision):
    name = decision.get("command")
    command = COMMANDS.get(name)

    if not command:
        return "I don't know how to do that yet."

    args = decision.get("args") or {}
    allowed_args = command["args"].keys()
    clean_args = {k: v for k, v in args.items() if k in allowed_args}

    missing_args = [
        arg for arg in allowed_args
        if arg not in clean_args or clean_args[arg] in [None, ""]
    ]

    if missing_args:
        return "I need a little more information for that."

    if command.get("pre_response"):
        speak(command["pre_response"])

    try:
        return command["function"](**clean_args)
    except Exception as e:
        dbg("COMMAND", f"{name} failed: {e}")
        return str(e)


def handle_user_input(user_input):
    decision = choose_command(user_input)
    decision = obvious_action_decision(user_input, decision)
    dbg("ROUTER_FINAL", json.dumps(decision))

    if decision.get("type") == "command":
        result = run_command(decision)
        if result:
            logging.info(f"NOVA: {result}")
            speak(result)
        return

    reply = ask_ollama(user_input)
    logging.info(f"NOVA: {reply}")
    speak(reply)


  
# CHAT
  

messages = [{"role": "system", "content": SYSTEM_PROMPT}]


def ask_ollama(user_input):
    # Inject current memories into context if any exist
    if memory["memories"]:
        mem_block = "Memories:\n" + "\n".join(
            f"- {m}" for m in memory["memories"]
        )
        full_input = f"{mem_block}\n\n{user_input}"
    else:
        full_input = user_input

    messages.append({"role": "user", "content": full_input})

    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": False,
    }

    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload)
    reply = r.json()["message"]["content"]

    messages.append({"role": "assistant", "content": reply})

    return reply


  
# VOICE LOOP
  


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
                result = json.loads(recognizer.Result())
                text = result.get("text", "").lower().strip()

                if not text:
                    continue

                if active and (time.time() - wake_time > WAKE_TIMEOUT):
                    active = False
                    print("⏳ Wake timeout")

                if not active:
                    if any(w in text for w in WAKE_WORDS):
                        print("🟢 Wake word detected")
                        play_chime()
                        active = True
                        wake_time = time.time()
                    continue

                yield text
                active = False


  
# TEXT LOOP
  


def text_loop():
    print("\n💬 TEXT MODE ENABLED")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("YOU: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                print("\n👋 Goodbye")
                break

            yield user_input

        except KeyboardInterrupt:
            print("\n👋 Goodbye")
            break


  
# STARTUP
  

print("\nNOVA ONLINE")

if TEXT_MODE:
    print("⌨️  Running in TEXT MODE (-t)")

if not check_ollama():
    exit(1)


# MAIN LOOP
  

input_source = text_loop() if TEXT_MODE else listen_loop()

try:
    for user_input in input_source:

        print(f"\nYOU: {user_input}")
        logging.info(f"USER: {user_input}")
        handle_user_input(user_input)
except KeyboardInterrupt:
    print("\n👋 Goodbye")
