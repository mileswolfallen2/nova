#!/usr/bin/env python3
"""NOVA V2 — AI agent with native Ollama tool calling."""

import json
import os
import sys

_clean_argv = [a for a in sys.argv if a not in ("--v2",)]
if "--ui" not in _clean_argv:
    _clean_argv.insert(1, "--ui")
sys.argv = _clean_argv

try:
    import jarvis
except Exception as e:
    print(f"[V2] Could not import jarvis: {e}")
    sys.exit(1)

OLLAMA_URL = jarvis.OLLAMA_URL
CHAT_MODEL = jarvis.CHAT_MODEL
WORKSPACE = jarvis.WORKSPACE_DIR


# ── Tool definitions (Ollama/OpenAI format) ──────────────────────────────

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or create a text file in the workspace folder. Only use when the user explicitly asks to save, write, create, or store something to a file. Do NOT use for casual chat or thanks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename (e.g. notes.txt)"},
                    "content": {"type": "string", "description": "The full text content to write"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "The filename to read (e.g. notes.txt)"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Only use for real-time data, news, or facts you genuinely don't know. Do NOT use for greetings, casual chat, weather, or system status — use the dedicated tools instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search question or query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for the configured location.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Get CPU, memory, and disk usage of this computer.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

def _unescape_content(s: str) -> str:
    return s.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r").replace("\\\"", "\"")

TOOL_MAP = {
    "write_file": lambda a: jarvis.command_write_file(a["filename"], _unescape_content(a["content"])),
    "read_file": lambda a: jarvis.command_read_file(a["filename"]),
    "web_search": lambda a: jarvis.web_search(a["query"]),
    "get_weather": lambda a: jarvis.get_weather(),
    "get_system_status": lambda a: jarvis.get_system_status(),
}

AGENT_SYSTEM_PROMPT = f"""You are NOVA V2, an AI agent on Miles Allen's computer.

# Available Tools

- web_search(query) — search the web for current info. Use ONLY for real-time data, news, or facts you don't know.
- write_file(filename, content) — save content to a file in the workspace.
- read_file(filename) — read a file from the workspace.
- get_system_status() — get CPU, RAM, and disk info.
- get_weather() — get current weather for the configured location.

# When to Use web_search

DO call web_search when the user asks about:
- Current news, events, or real-time information
- Facts you are uncertain about that need verification
- Specific questions requiring up-to-date data

DO NOT call web_search for:
- Greetings, salutations, or casual conversation — just respond directly
- Questions you can answer from your own knowledge
- Weather — use get_weather instead
- System status — use get_system_status instead

# Behavior Rules

- After a tool returns a result, incorporate it naturally into your response. Never echo the tool result verbatim — summarize it in your own words. Never say you couldn't find information when a tool already returned relevant results.
- Call only the minimum necessary tools. Do not chain extra tools.
- For greetings, thanks, or casual conversation — respond conversationally without calling any tools.
- Be concise and conversational. Workspace: {WORKSPACE}"""


# ── LLM call ─────────────────────────────────────────────────────────────

def call_llm(messages, tools=None):
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "options": {"temperature": 0.0},
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    try:
        r = jarvis.requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        return r.json()["message"]
    except Exception as e:
        return {"content": f"[LLM error: {e}]"}


# ── Agent loop ───────────────────────────────────────────────────────────

_CASUAL = frozenset({"thx", "thanks", "ty", "ok", "okay", "cool", "nice", "k", "kk", "np", "got it", "sure", "thanks!", "ty!", "k thanks", "ok thanks", "okay thanks"})

def agent_process(user_input: str, messages: list | None = None) -> tuple[str, list]:
    if messages is None:
        messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]

    stripped = user_input.lower().strip()
    if stripped in _CASUAL:
        reply = "You're welcome!" if stripped in ("thx", "thanks", "ty", "thanks!", "ty!", "k thanks", "ok thanks", "okay thanks") else "👍"
        messages.append({"role": "user", "content": user_input})
        messages.append({"role": "assistant", "content": reply})
        return reply, messages

    messages.append({"role": "user", "content": user_input})

    for step in range(10):
        msg = call_llm(messages, tools=TOOL_DEFS)
        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls")

        msg_entry = {"role": "assistant", "content": content}
        if tool_calls:
            msg_entry["tool_calls"] = tool_calls
        messages.append(msg_entry)

        if tool_calls:
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                if isinstance(raw_args, dict):
                    fn_args = raw_args
                else:
                    try:
                        fn_args = json.loads(raw_args)
                    except (json.JSONDecodeError, KeyError):
                        fn_args = {}

                handler = TOOL_MAP.get(fn_name)
                if not handler:
                    result = f"[Unknown tool: {fn_name}]"
                else:
                    try:
                        result = handler(fn_args)
                        if result is None:
                            result = "(no result)"
                    except Exception as e:
                        result = f"[Error: {e}]"

                messages.append({
                    "role": "tool",
                    "name": fn_name,
                    "content": str(result),
                })

                if fn_name == "write_file":
                    return result, messages

            continue

        if not content or content.isspace():
            return "(no response)", messages

        user_wants_file = any(k in user_input.lower() for k in ["save", "write", "create", "file"])
        has_written = any(m.get("role") == "tool" and m.get("name") == "write_file" for m in messages)

        if user_wants_file and not has_written:
            if content and any(name in content for name in TOOL_MAP):
                messages.append({"role": "user", "content": "Call the tool using the tool calling mechanism."})
                continue
            messages.append({"role": "user", "content": "Call write_file now to save the content."})
            continue

        return content, messages

    final = "I've completed everything I can. Let me know if you need anything else."
    messages.append({"role": "assistant", "content": final})
    return final, messages


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    print(f"\n  NOVA V2 — Native Tool Agent")
    print(f"  {'─' * 40}")
    print(f"  Model: {CHAT_MODEL}")
    tools = [t["function"]["name"] for t in TOOL_DEFS]
    print(f"  Tools: {', '.join(tools)}")
    print(f"  Workspace: {WORKSPACE}")
    print()

    messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]

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
