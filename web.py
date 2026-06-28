#!/usr/bin/env python3
"""NOVA Web Server — mobile-friendly web interface for jarvis.py"""

import os
import sys
import json
import time
import asyncio
import mimetypes

if "--ui" not in sys.argv:
    sys.argv.insert(1, "--ui")

try:
    import jarvis
except Exception as e:
    print(f"[WEB] Could not import jarvis.py: {e}")
    sys.exit(1)

from aiohttp import web

HOST = os.environ.get("NOVA_HOST", "0.0.0.0")
PORT = int(os.environ.get("NOVA_PORT", "8080"))

WORKSPACE = jarvis.WORKSPACE_DIR
os.makedirs(WORKSPACE, exist_ok=True)

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,user-scalable=no">
<title>NOVA</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#010508;color:#C5E8F7;height:100vh;display:flex;flex-direction:column;overflow:hidden}
.hdr{padding:10px 14px;border-bottom:1px solid #1A4A6E;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;background:#010508}
.hdr .ttl{font-size:17px;font-weight:700;color:#8FE8FF;letter-spacing:3px}
.hdr .st{display:flex;align-items:center;gap:5px;font-size:11px;color:#5A8AA8}
.hdr .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.hdr .dot.on{background:#5CE1FF;box-shadow:0 0 8px #5CE1FF}
.hdr .dot.off{background:#FF5566}
.hdr .ws-btn{background:0;border:1px solid #2A6A8F;color:#8FE8FF;border-radius:4px;padding:3px 8px;font-size:10px;cursor:pointer}
.chat{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth;-webkit-overflow-scrolling:touch}
.msg{max-width:88%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.5;word-wrap:break-word}
.msg.u{align-self:flex-end;background:#061018;border:1px solid #D4AF37;color:#C5E8F7}
.msg.n{background:#040E18;border:1px solid #4FC3F7;color:#C5E8F7}
.msg.sys{align-self:center;background:0;border:0;color:#5A8AA8;font-size:12px;padding:4px 8px}
.inp{padding:10px 12px;border-top:1px solid #1A4A6E;display:flex;gap:8px;flex-shrink:0;background:#010508}
.inp input{flex:1;padding:11px 16px;border-radius:22px;border:1px solid #2A6A8F;background:#040C14;color:#C5E8F7;font-size:15px;outline:0;-webkit-appearance:none}
.inp input:focus{border-color:#4FC3F7}
.inp button{width:42px;height:42px;border-radius:50%;border:0;background:#4FC3F7;color:#010508;font-size:16px;cursor:pointer;flex-shrink:0;display:flex;align-items:center;justify-content:center}
.inp button:disabled{opacity:.35}
.ld{text-align:center;padding:10px;color:#5A8AA8;font-size:13px}
.ty{display:flex;gap:5px;justify-content:center;align-items:center}
.ty s{width:6px;height:6px;border-radius:50%;background:#4FC3F7;animation:b 1.4s infinite}
.ty s:nth-child(2){animation-delay:.2s}
.ty s:nth-child(3){animation-delay:.4s}
@keyframes b{0%,80%,100%{transform:scale(0)}50%{transform:scale(1)}}

/* File panel */
.file-panel{display:none;flex-direction:column;flex:1;overflow:hidden;border-top:1px solid #1A4A6E}
.file-panel.on{display:flex}
.file-panel .head{padding:8px 14px;font-size:11px;color:#D4AF37;border-bottom:1px solid #1A4A6E;display:flex;justify-content:space-between}
.file-panel .list{flex:1;overflow-y:auto;padding:8px 14px}
.file-item{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #0A1A2A;font-size:13px}
.file-item a{color:#4FC3F7;text-decoration:none}
.file-item a:active{color:#8FE8FF}
.file-item .sz{color:#5A8AA8;font-size:11px}
.upload-form{display:flex;gap:6px;padding:8px 14px;border-top:1px solid #1A4A6E;align-items:center}
.upload-form input[type=file]{flex:1;font-size:12px;color:#C5E8F7}
.upload-form input[type=file]::file-selector-button{background:#0A1A2A;border:1px solid #2A6A8F;color:#8FE8FF;border-radius:4px;padding:4px 10px;font-size:11px;cursor:pointer}
.upload-form button{background:#4FC3F7;border:0;color:#010508;border-radius:4px;padding:5px 12px;font-size:12px;cursor:pointer}
.tab-bar{display:flex;border-top:1px solid #1A4A6E;flex-shrink:0}
.tab-bar button{flex:1;padding:8px;background:#040C14;border:0;color:#5A8AA8;font-size:12px;cursor:pointer;border-top:2px solid transparent}
.tab-bar button.on{color:#8FE8FF;border-top-color:#4FC3F7;background:#010508}
.tab-bar button:active{background:#0A1A2A}
</style>
</head>
<body>
<div class="hdr">
  <div class="ttl">N O V A</div>
  <div style="display:flex;align-items:center;gap:8px">
    <button class="ws-btn" id="filesBtn">FILES</button>
    <div class="st"><span class="dot off" id="dot"></span><span id="stText">offline</span></div>
  </div>
</div>
<div class="chat" id="chat"></div>
<div id="filePanel" class="file-panel">
  <div class="head"><span>WORKSPACE</span><span id="fileCount">0 files</span></div>
  <div class="list" id="fileList"></div>
  <div class="upload-form">
    <input type="file" id="fileInput" multiple>
    <button id="uploadBtn">UP</button>
  </div>
</div>
<div class="inp" id="inputArea">
  <input type="text" id="input" placeholder="Message NOVA..." autofocus>
  <button id="sendBtn">→</button>
</div>
<div class="tab-bar">
  <button id="tabChat" class="on">CHAT</button>
  <button id="tabFiles">FILES</button>
</div>
<script>
const chat=document.getElementById('chat'),inp=document.getElementById('input'),sendBtn=document.getElementById('sendBtn'),dot=document.getElementById('dot'),stText=document.getElementById('stText');
const filePanel=document.getElementById('filePanel'),fileList=document.getElementById('fileList'),fileInput=document.getElementById('fileInput'),uploadBtn=document.getElementById('uploadBtn'),fileCount=document.getElementById('fileCount'),filesBtn=document.getElementById('filesBtn');
const tabChat=document.getElementById('tabChat'),tabFiles=document.getElementById('tabFiles'),inputArea=document.getElementById('inputArea');
let busy=!1,showFiles=!1,statusInterval;
function addMsg(t,r){const d=document.createElement('div');d.className='msg '+r;d.textContent=t;chat.appendChild(d);chat.scrollTop=chat.scrollHeight}
function ld(on){const e=document.getElementById('ld');if(e)e.remove();if(on){const d=document.createElement('div');d.id='ld';d.className='ld';d.innerHTML='<div class="ty"><s></s><s></s><s></s></div>';chat.appendChild(d);chat.scrollTop=chat.scrollHeight}}
async function send(){const t=inp.value.trim();if(!t||busy)return;inp.value='';busy=!0;sendBtn.disabled=!0;addMsg(t,'u');ld(!0);try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});const d=await r.json();ld(!1);addMsg(d.text||d.error||'No response','n')}catch{ld(!1);addMsg('Connection error','n')}busy=!1;sendBtn.disabled=!1;inp.focus()}
async function st(){try{const r=await fetch('/api/status');const d=await r.json();dot.className='dot '+(d.ollama?'on':'off');stText.textContent=d.ollama?'online':'offline'}catch{dot.className='dot off';stText.textContent='offline'}}
async function loadFiles(){try{const r=await fetch('/api/files');const d=await r.json();fileList.innerHTML='';fileCount.textContent=d.files.length+' files';if(!d.files.length){fileList.innerHTML='<div style="color:#5A8AA8;padding:20px;text-align:center;font-size:13px">empty workspace</div>';return}d.files.forEach(f=>{const row=document.createElement('div');row.className='file-item';const sz=f.size<1024?f.size+'B':(f.size/1024).toFixed(1)+'KB';row.innerHTML='<a href="/api/files/'+encodeURIComponent(f.name)+'" download>'+f.name+'</a><span class="sz">'+sz+'</span>';fileList.appendChild(row)})}catch{fileList.innerHTML='<div style="color:#FF5566;padding:20px;text-align:center">error loading files</div>'}}
async function uploadFiles(){const files=fileInput.files;if(!files.length)return;const fd=new FormData();for(const f of files)fd.append('files',f);uploadBtn.textContent='...';uploadBtn.disabled=!0;try{await fetch('/api/files',{method:'POST',body:fd});fileInput.value='';loadFiles()}finally{uploadBtn.textContent='UP';uploadBtn.disabled=!1}}
function toggleFiles(on){showFiles=on;filePanel.classList.toggle('on',on);inputArea.style.display=on?'none':'flex';tabChat.classList.toggle('on',!on);tabFiles.classList.toggle('on',on);if(on)loadFiles()}
sendBtn.addEventListener('click',send);inp.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
filesBtn.addEventListener('click',()=>toggleFiles(!showFiles));
tabChat.addEventListener('click',()=>toggleFiles(0));
tabFiles.addEventListener('click',()=>toggleFiles(1));
uploadBtn.addEventListener('click',uploadFiles);
document.getElementById('fileInput').addEventListener('change',uploadFiles);
st();statusInterval=setInterval(st,15000);
addMsg('NOVA web interface ready. Say "NOVA" or type a message.','sys');
</script>
</body>
</html>"""


async def handle_index(request):
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def handle_status(request):
    online = jarvis.check_ollama()
    return web.json_response({"ollama": online})


async def handle_chat(request):
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        if not text:
            return web.json_response({"error": "empty message"}, status=400)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, jarvis.process_input, text)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_list_files(request):
    try:
        files = []
        for name in os.listdir(WORKSPACE):
            path = os.path.join(WORKSPACE, name)
            if os.path.isfile(path):
                stat = os.stat(path)
                files.append({"name": name, "size": stat.st_size, "mtime": stat.st_mtime})
        files.sort(key=lambda f: f["mtime"], reverse=True)
        return web.json_response({"files": files})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_download(request):
    name = request.match_info.get("name", "")
    safe = os.path.basename(name)
    path = os.path.join(WORKSPACE, safe)
    if not os.path.exists(path) or not os.path.isfile(path):
        raise web.HTTPNotFound()
    ct, _ = mimetypes.guess_type(safe)
    return web.FileResponse(path, headers={"Content-Disposition": f'attachment; filename="{safe}"'})


async def handle_upload(request):
    try:
        reader = await request.multipart()
        count = 0
        while True:
            part = await reader.next()
            if part is None:
                break
            filename = part.filename or f"upload_{int(time.time())}"
            safe = os.path.basename(filename)
            path = os.path.join(WORKSPACE, safe)
            with open(path, "wb") as f:
                while True:
                    chunk = await part.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)
            count += 1
        return web.json_response({"uploaded": count})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def main():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", handle_status)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/files", handle_list_files)
    app.router.add_get("/api/files/{name:.+}", handle_download)
    app.router.add_post("/api/files", handle_upload)

    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)

    print(f"\n  NOVA Web Server")
    print(f"  {'─' * 40}")
    print(f"  Local:    http://localhost:{PORT}")
    print(f"  Network:  http://{local_ip}:{PORT}")
    print(f"  Phone:    http://{local_ip}:{PORT}  ← open on your phone")
    print(f"  Workspace: {WORKSPACE}")
    print()

    web.run_app(app, host=HOST, port=PORT, print=lambda _: None)


if __name__ == "__main__":
    main()
