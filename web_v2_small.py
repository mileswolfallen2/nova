#!/usr/bin/env python3
"""NOVA V2 Small Web Server — JSON-mode agent for small models, accessible from your phone."""

import os
import sys
import asyncio
import ssl
from pathlib import Path

if "--ui" not in sys.argv:
    sys.argv.insert(1, "--ui")

try:
    import jarvis_v2_small
except Exception as e:
    print(f"[WEBV2-SMALL] Could not import jarvis_v2_small.py: {e}")
    sys.exit(1)

from aiohttp import web

HOST = os.environ.get("NOVA_HOST", "0.0.0.0")
PORT = int(os.environ.get("NOVA_PORT", "9091"))

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<title>NOVA V2 Small</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0a0f;color:#e0e0e0;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.hdr{padding:10px 14px;border-bottom:1px solid #2a2a3a;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;background:#0a0a0f}
.hdr .ttl{font-size:16px;font-weight:700;background:linear-gradient(90deg,#22c55e,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:2px}
.hdr .st{display:flex;align-items:center;gap:5px;font-size:11px;color:#6b7280}
.hdr .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.hdr .dot.on{background:#22c55e;box-shadow:0 0 8px #22c55e}
.hdr .dot.off{background:#ef4444}
.hdr .badge{font-size:9px;background:#1a3a1a;color:#22c55e;padding:2px 6px;border-radius:4px}
.chat{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:8px;scroll-behavior:smooth}
.msg{max-width:90%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.5;word-wrap:break-word}
.msg.u{background:#1a1a2e;border:1px solid #22c55e;color:#e0e0e0;align-self:flex-end}
.msg.a{background:#111827;border:1px solid #06b6d4;color:#e0e0e0;align-self:flex-start}
.msg.tool{padding:6px 10px;font-size:11px;border-radius:6px;align-self:center;background:#1a1a2e;border:1px solid #374151;color:#9ca3af;font-family:monospace;max-width:100%}
.msg.tool .name{color:#22c55e;font-weight:600}
.msg.tool .res{color:#06b6d4}
.msg.err{padding:6px 10px;font-size:11px;border-radius:6px;align-self:center;background:#2a0a0a;border:1px solid #ef4444;color:#fca5a5;font-family:monospace;max-width:100%}
.ld{text-align:center;padding:12px;color:#6b7280;font-size:12px;align-self:center}
.ld .sp{display:inline-block;width:18px;height:18px;border:2px solid #374151;border-top-color:#22c55e;border-radius:50%;animation:s .8s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
.inp{padding:10px 12px;border-top:1px solid #2a2a3a;display:flex;gap:8px;flex-shrink:0;background:#0a0a0f}
.inp input{flex:1;padding:11px 16px;border-radius:22px;border:1px solid #374151;background:#111827;color:#e0e0e0;font-size:15px;outline:0}
.inp input:focus{border-color:#22c55e}
.inp button{width:42px;height:42px;border-radius:50%;border:0;background:linear-gradient(135deg,#22c55e,#06b6d4);color:#fff;font-size:18px;cursor:pointer;flex-shrink:0}
.inp button:disabled{opacity:.35}
</style>
</head>
<body>
<div class="hdr">
  <div class="ttl">NOVA V2 Small</div>
  <div style="display:flex;align-items:center;gap:8px">
    <span class="badge">JSON</span>
    <div class="st"><span class="dot off" id="dot"></span><span id="stText">offline</span></div>
  </div>
</div>
<div class="chat" id="chat"></div>
<div class="inp">
  <input type="text" id="input" placeholder="Ask NOVA..." autofocus>
  <button id="sendBtn">→</button>
</div>
<script>
const chat=document.getElementById('chat'),inp=document.getElementById('input'),sendBtn=document.getElementById('sendBtn'),dot=document.getElementById('dot'),stText=document.getElementById('stText');
const STORAGE_KEY='nova_v2_small_chat';
let busy=!1;
function save(){
  const msgs=[];
  for(const el of chat.children){
    if(el.id==='ld')continue;
    let role='a',text='';
    if(el.classList.contains('u'))role='u';
    else if(el.classList.contains('tool')){role='tool';text=el.innerHTML}
    else if(el.classList.contains('err')){role='err';text=el.innerHTML}
    else text=el.textContent;
    if(!text&&role!=='a')continue;
    msgs.push({r:role,t:text||el.textContent});
  }
  try{localStorage.setItem(STORAGE_KEY,JSON.stringify(msgs))}catch{}
}
function addMsg(t,role,saveMsg=!0){
  const d=document.createElement('div');
  if(role==='tool'||role==='err'){
    d.className='msg '+role;
    d.innerHTML=t;
  }else{
    d.className='msg '+(role==='u'?'u':'a');
    d.textContent=t;
  }
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
  if(saveMsg)save();
  return d;
}
// restore saved messages
try{
  const saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||'[]');
  if(saved.length){
    for(const m of saved){
      if(m.r==='tool'||m.r==='err')addMsg(m.t,m.r,!1);
      else addMsg(m.t,m.r,!1);
    }
  }else{
    addMsg('NOVA V2 Small ready (JSON-mode). Model: qwen2.5:1.5b','a',!1);
  }
}catch{addMsg('NOVA V2 Small ready (JSON-mode). Model: qwen2.5:1.5b','a',!1)}
function ld(on){
  const e=document.getElementById('ld');
  if(e)e.remove();
  if(on){
    const d=document.createElement('div');d.id='ld';d.className='ld';
    d.innerHTML='<span class="sp"></span>thinking...';
    chat.appendChild(d);chat.scrollTop=chat.scrollHeight;
  }
}
async function send(){
  const t=inp.value.trim();if(!t||busy)return;
  inp.value='';busy=!0;sendBtn.disabled=!0;
  addMsg(t,'u');ld(!0);
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
    const d=await r.json();
    ld(!1);
    if(d.steps)for(const s of d.steps){
      if(s.type==='tool')addMsg('<span class="name">⟐ '+s.tool+'</span> '+esc(s.args),'tool');
      else if(s.type==='result')addMsg('<span class="res">▸ result:</span> '+esc(s.result),'tool');
      else if(s.type==='error')addMsg('⚠ '+esc(s.msg),'err');
    }
    addMsg(d.reply||'No response','a');
  }catch(e){ld(!1);addMsg('Connection error','err')}
  busy=!1;sendBtn.disabled=!1;inp.focus();
}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML}
sendBtn.addEventListener('click',send);
inp.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
async function st(){try{const r=await fetch('/api/status');const d=await r.json();dot.className='dot '+(d.ollama?'on':'off');stText.textContent=d.ollama?'online':'offline'}catch{dot.className='dot off';stText.textContent='offline'}}
st();setInterval(st,15000);
</script>
</body>
</html>"""


chat_sessions: dict[str, dict] = {}


async def handle_index(request):
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def handle_status(request):
    try:
        online = jarvis_v2_small.jarvis.check_ollama()
    except Exception:
        online = False
    return web.json_response({"ollama": online})


async def handle_chat(request):
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        session_id = data.get("session", "default")
        if not text:
            return web.json_response({"error": "empty message"}, status=400)

        if session_id not in chat_sessions:
            chat_sessions[session_id] = {
                "messages": [{"role": "system", "content": jarvis_v2_small.SYSTEM_PROMPT}]
            }

        session = chat_sessions[session_id]
        original_count = len(session["messages"])

        loop = asyncio.get_event_loop()

        def run():
            reply, messages = jarvis_v2_small.agent_process(text, session["messages"])
            session["messages"] = messages
            new_msgs = messages[original_count:]
            steps = []
            for m in new_msgs:
                role = m["role"]
                content = m.get("content", "")
                if role == "assistant":
                    parsed = jarvis_v2_small.parse_json(content)
                    if parsed and parsed.get("action") and parsed["action"] != "chat":
                        action = parsed["action"]
                        args = parsed.get("args", {}) or parsed
                        steps.append({"type": "tool", "tool": action, "args": str(args)[:200]})
                elif role == "user" and content.startswith("Tool result from "):
                    rest = content[len("Tool result from "):]
                    idx = rest.find(": ")
                    if idx != -1:
                        steps.append({"type": "result", "result": rest[idx+2:][:300]})
            return {"reply": reply, "steps": steps}

        result = await loop.run_in_executor(None, run)
        return web.json_response(result)

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def ensure_self_signed_cert(cert_dir):
    cert_path = cert_dir / "cert.pem"
    key_path = cert_dir / "key.pem"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    cert_dir.mkdir(parents=True, exist_ok=True)
    import subprocess
    try:
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(key_path),
             "-out", str(cert_path), "-days", "3650", "-nodes",
             "-subj", "/CN=nova.local", "-addext", "subjectAltName=DNS:nova.local"],
            check=True, capture_output=True,
        )
        print("  Self-signed certificate created")
        return cert_path, key_path
    except Exception as e:
        print(f"  Could not generate certificate ({e}), falling back to HTTP")
        return None, None


def main():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", handle_status)
    app.router.add_post("/api/chat", handle_chat)

    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    cert_dir = Path(__file__).parent / ".certs"
    cert_path, key_path = ensure_self_signed_cert(cert_dir)

    if cert_path and key_path:
        ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_ctx.load_cert_chain(cert_path, key_path)
        scheme = "https"
    else:
        ssl_ctx = None
        scheme = "http"

    print(f"\n  NOVA V2 Small Web Server (JSON-mode)")
    print(f"  {'─' * 40}")
    print(f"  Model:   {jarvis_v2_small.CHAT_MODEL}")
    print(f"  Local:   {scheme}://localhost:{PORT}")
    print(f"  Network: {scheme}://{local_ip}:{PORT}")
    print(f"  Phone:   {scheme}://{local_ip}:{PORT}")
    print()

    web.run_app(app, host=HOST, port=PORT, ssl_context=ssl_ctx, print=lambda _: None)


if __name__ == "__main__":
    main()
