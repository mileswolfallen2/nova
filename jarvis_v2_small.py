#!/usr/bin/env python3
"""NOVA V2 Small — JSON-mode agent for small models (3B-7B, Raspberry Pi, etc.).
Uses structured JSON output instead of native tool_calls for reliability on weaker hardware."""

import json
import re
import sys

_clean_argv = [a for a in sys.argv if a not in ("--v2",)]
if "--ui" not in _clean_argv:
    _clean_argv.insert(1, "--ui")
sys.argv = _clean_argv

try:
    import jarvis
except Exception as e:
    print(f"[V2-SMALL] Could not import jarvis: {e}")
    sys.exit(1)

OLLAMA_URL = jarvis.OLLAMA_URL
CHAT_MODEL = "qwen2.5:1.5b"  # default for small models; override with env NOVA_MODEL or edit jarvis.py
WORKSPACE = jarvis.WORKSPACE_DIR


TOOL_DEFS = {
    "web_search": {"query": "search query — use for current news, facts, or info you don't know"},
    "write_file": {"filename": "output filename", "content": "full text content to write"},
    "read_file": {"filename": "file to read"},
    "get_weather": {},
    "get_system_status": {},
}

TOOL_MAP = {
    "web_search": lambda a: jarvis.web_search(a.get("query", "")),
    "write_file": lambda a: jarvis.command_write_file(
        a.get("filename", ""),
        a.get("content", "").replace("\\n", "\n").replace("\\t", "\t"),
    ),
    "read_file": lambda a: jarvis.command_read_file(a.get("filename", "")),
    "get_weather": lambda a: jarvis.get_weather(),
    "get_system_status": lambda a: jarvis.get_system_status(),
}

SYSTEM_PROMPT = f"""You are NOVA V2 (Small), an AI agent on Miles Allen's computer.

Respond ONLY in JSON. Choose one action:

1. chat — normal reply. Use for greetings, thanks, or after getting a tool result.
   {{"action": "chat", "response": "your reply"}}

2. web_search — search the web. Use for current news, facts you don't know.
   {{"action": "web_search", "args": {{"query": "search question"}}}}

3. write_file — save content to workspace.
   {{"action": "write_file", "args": {{"filename": "name.txt", "content": "text here"}}}}

4. read_file — read from workspace.
   {{"action": "read_file", "args": {{"filename": "name.txt"}}}}

5. get_weather — current weather.
   {{"action": "get_weather", "args": {{}}}}

6. get_system_status — CPU, RAM, disk.
   {{"action": "get_system_status", "args": {{}}}}

Rules:
- Use chat action for greetings, thanks, casual talk — never call a tool.
- Call a tool only when the user asks for info or an action.
- After a tool runs you'll get the result. Then use chat action to reply naturally.
- Be concise.
Workspace: {WORKSPACE}"""


def call_llm(messages):
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "format": "json",
        "options": {"temperature": 0.0},
        "stream": False,
    }
    try:
        r = jarvis.requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        return r.json()["message"]["content"]
    except Exception as e:
        return json.dumps({"action": "chat", "response": f"[Error: {e}]"})


def parse_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass
    return None


def normalize_args(parsed):
    args = parsed.get("args")
    if isinstance(args, dict):
        return args
    result = {}
    for key in ("query", "filename", "content"):
        if key in parsed:
            result[key] = parsed[key]
    return result


_CASUAL = frozenset({
    "thx", "thanks", "ty", "ok", "okay", "cool", "nice",
    "k", "kk", "np", "got it", "sure",
    "thanks!", "ty!", "k thanks", "ok thanks", "okay thanks",
})


def agent_process(user_input, messages=None):
    if messages is None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    stripped = user_input.lower().strip()
    if stripped in _CASUAL:
        reply = "You're welcome!" if any(
            stripped.startswith(w) for w in ("thx", "thanks", "ty")
        ) else "Got it!"
        messages.append({"role": "user", "content": user_input})
        messages.append({"role": "assistant", "content": reply})
        return reply, messages

    messages.append({"role": "user", "content": user_input})

    for _ in range(8):
        raw = call_llm(messages)
        parsed = parse_json(raw)

        if parsed is None:
            msg = raw[:200] if raw.strip() else "I couldn't process that."
            messages.append({"role": "assistant", "content": msg})
            return msg, messages

        action = parsed.get("action", "chat")
        response = parsed.get("response", "")

        if action == "chat":
            reply = response or "OK."
            messages.append({"role": "assistant", "content": reply})
            return reply, messages

        args = normalize_args(parsed)
        handler = TOOL_MAP.get(action)

        if not handler:
            result = f"Unknown action '{action}'."
        else:
            try:
                result = handler(args)
                if result is None:
                    result = "(done)"
            except Exception as e:
                result = f"[Error: {e}]"

        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": f"Tool result from {action}: {result}",
        })

        if action == "write_file":
            return result, messages

    return "I've finished what I can.", messages


def main():
    print(f"\n  NOVA V2 Small — JSON-mode agent")
    print(f"  {'─' * 40}")
    print(f"  Model: {CHAT_MODEL}")
    print(f"  Tools: {', '.join(sorted(TOOL_MAP))}")
    print(f"  Workspace: {WORKSPACE}")
    print()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("YOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye.")
            break

        reply, messages = agent_process(user_input, messages)
        print(f"\nNOVA: {reply}\n")


if __name__ == "__main__":
    main()
