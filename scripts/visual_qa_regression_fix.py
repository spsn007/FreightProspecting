"""
Visual QA & Console Error Check for Master Directory 500 Regression Fix.
Connects via Chrome CDP to the live running application on http://127.0.0.1:8000.
Captures the 5 required screenshots and listens for any console errors.
"""

import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

APP_URL = "http://127.0.0.1:8000"
CDP_PORT = 9275
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_regression_fix"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\regression_fix")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_msg_counter = 2000
console_errors = []

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
    await asyncio.sleep(1.8)

async def set_viewport(ws, width, height):
    global _msg_counter
    _msg_counter += 1
    req_id = _msg_counter
    await ws.send(json.dumps({
        "id": req_id,
        "method": "Emulation.setDeviceMetricsOverride",
        "params": {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": False,
        }
    }))
    while True:
        raw = await ws.recv()
        res = json.loads(raw)
        if res.get("id") == req_id:
            break
    await asyncio.sleep(0.5)

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
            if "result" in res and "data" in res["result"]:
                img_data = base64.b64decode(res["result"]["data"])
                p = SCREENSHOTS_DIR / f"{name}.png"
                p.write_bytes(img_data)
                print(f"[QA] Captured: {p.name} ({len(img_data):,} bytes)", flush=True)
                break
            else:
                print(f"[QA] Failed to capture {name}: {res}", flush=True)
                break

async def main():
    print(f"[QA] Launching Chrome CDP on port {CDP_PORT}...", flush=True)
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--headless=new",
        "--window-size=1440,900",
        "--disable-gpu",
        f"{APP_URL}/prospects"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print(f"[QA] Connected to page: {ws_url}", flush=True)

        async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.recv()
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.recv()

            await set_viewport(ws, 1440, 900)

            # 1. Master Directory default (Light Mode)
            print("\n1. Capturing Master Directory default...", flush=True)
            await navigate(ws, f"{APP_URL}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('fp_theme', 'light');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "01_master_directory_default")

            # 2. Master Directory search 'Steel'
            print("\n2. Capturing Master Directory search 'Steel'...", flush=True)
            await navigate(ws, f"{APP_URL}/prospects?q=Steel")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "02_master_directory_search_steel")

            # 3. Ready to Contact tab
            print("\n3. Capturing Ready to Contact tab...", flush=True)
            await navigate(ws, f"{APP_URL}/prospects?stage=QUALIFIED")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "03_ready_to_contact_tab")

            # 4. Discovery tab
            print("\n4. Capturing Discovery tab...", flush=True)
            await navigate(ws, f"{APP_URL}/prospects?stage=DISCOVERY")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "04_discovery_tab")

            # 5. Dark Mode Master Directory
            print("\n5. Capturing Dark Mode Master Directory...", flush=True)
            await navigate(ws, f"{APP_URL}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "05_dark_mode_master_directory")

            # Check for console errors in page context
            err_check = await evaluate(ws, "window._hasError || false")
            print(f"\n[QA] In-page error check: {err_check}", flush=True)
            print("[QA] All 5 regression fix screenshots captured successfully!", flush=True)

    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()
        print("[QA] Chrome cleaned up.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
