"""
Audit script: Captures screenshots of all key screens in Light and Dark Mode
"""
import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.request
import websockets
from pathlib import Path

SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\audit")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9224
_msg_counter = 500

async def evaluate(ws, expr):
    global _msg_counter
    _msg_counter += 1
    req_id = _msg_counter
    await ws.send(json.dumps({
        "id": req_id,
        "method": "Runtime.evaluate",
        "params": {"expression": expr, "returnByValue": True}
    }))
    while True:
        raw = await ws.recv()
        res = json.loads(raw)
        if res.get("id") == req_id:
            return res.get("result", {}).get("result", {}).get("value")

async def capture(ws, name):
    global _msg_counter
    _msg_counter += 1
    req_id = _msg_counter
    await ws.send(json.dumps({
        "id": req_id,
        "method": "Page.captureScreenshot",
        "params": {"format": "png"}
    }))
    while True:
        raw = await ws.recv()
        res = json.loads(raw)
        if res.get("id") == req_id:
            img_data = base64.b64decode(res["result"]["data"])
            p = SCREENSHOTS_DIR / f"{name}.png"
            with open(p, "wb") as f:
                f.write(img_data)
            print(f"Captured: {p.name}", flush=True)
            break

async def navigate(ws, url):
    global _msg_counter
    _msg_counter += 1
    req_id = _msg_counter
    await ws.send(json.dumps({
        "id": req_id,
        "method": "Page.navigate",
        "params": {"url": url}
    }))
    while True:
        raw = await ws.recv()
        res = json.loads(raw)
        if res.get("id") == req_id:
            break
    await asyncio.sleep(0.8)

async def run_audit():
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        "--disable-gpu",
        "--window-size=1440,900",
        "http://127.0.0.1:8000/"
    ])
    await asyncio.sleep(2.5)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Connected to CDP:", ws_url, flush=True)

        pages = [
            ("/", "cockpit"),
            ("/prospects", "prospects_companies"),
            ("/prospects/1", "prospect_detail_beasley"),
            ("/crm/interested", "crm_interested"),
            ("/crm/follow-ups", "crm_follow_ups"),
            ("/crm/no-answer", "crm_no_answer"),
            ("/crm/not-interested", "crm_not_interested"),
            ("/loads", "loads"),
            ("/carriers", "carriers"),
            ("/research", "research"),
            ("/settings", "settings"),
        ]

        async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "DOM.enable"}))

            # 1. Light Mode pass
            print("\n=== LIGHT MODE AUDIT ===", flush=True)
            for path, name in pages:
                await navigate(ws, f"http://127.0.0.1:8000{path}")
                await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('fp_theme', 'light')")
                await asyncio.sleep(0.4)
                await capture(ws, f"before_{name}_light")

            # 2. Dark Mode pass
            print("\n=== DARK MODE AUDIT ===", flush=True)
            for path, name in pages:
                await navigate(ws, f"http://127.0.0.1:8000{path}")
                await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark')")
                await asyncio.sleep(0.4)
                await capture(ws, f"before_{name}_dark")

            print("\nALL AUDIT SCREENSHOTS CAPTURED!", flush=True)
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    asyncio.run(run_audit())
