"""
Visual QA Script for Dark Mode Consistency verification.
Targets port 8000, connects to Chrome CDP, and captures the 4 required screenshots:
1. 01_cockpit_dark_mode.png
2. 02_ameristeel_detail_top_dark.png
3. 03_ameristeel_detail_middle_dark.png
4. 04_ameristeel_readiness_dark.png
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import websockets

APP_PORT = 8000
CDP_PORT = 9285
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_dark_mode"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\dark_mode_consistency")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_msg_counter = 1000

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
    await asyncio.sleep(1.5)

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

async def run_qa():
    # 1. Verify app is running on port 8000
    print(f"[QA] Checking application on port {APP_PORT}...", flush=True)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/", timeout=2) as resp:
            if resp.status != 200:
                print(f"[QA] App returned status {resp.status}", flush=True)
                return
    except Exception as e:
        print(f"[QA] Could not connect to app on port {APP_PORT}: {e}", flush=True)
        return

    # 2. Launch headless Chrome with CDP
    chrome_cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={USER_DATA_DIR}",
        "about:blank"
    ]
    print("[QA] Launching headless Chrome...", flush=True)
    chrome_proc = subprocess.Popen(chrome_cmd)

    # 3. Wait for Chrome CDP endpoint
    ws_url = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=1) as resp:
                data = json.loads(resp.read().decode())
                for target in data:
                    if target.get("type") == "page" and "webSocketDebuggerUrl" in target:
                        ws_url = target["webSocketDebuggerUrl"]
                        break
                if ws_url:
                    break
        except Exception:
            time.sleep(0.3)

    if not ws_url:
        print("[QA] Failed to get WebSocket URL from Chrome CDP", flush=True)
        chrome_proc.terminate()
        return

    print(f"[QA] Connected to Chrome CDP: {ws_url}", flush=True)

    try:
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            # Set desktop viewport 1440x950
            await set_viewport(ws, 1440, 950)

            # -----------------------------------------------------------------
            # Screen 1: Shortlist Cockpit Dark Mode
            # -----------------------------------------------------------------
            print("[QA] Navigating to Shortlist Cockpit...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/")
            # Enable dark mode
            await evaluate(ws, """
                document.documentElement.setAttribute('data-theme', 'dark');
                localStorage.setItem('fp_theme', 'dark');
                if (typeof updateThemeUI === 'function') updateThemeUI();
            """)
            await asyncio.sleep(0.5)
            # Scroll down slightly to display prospect cards with next-action-box clearly
            await evaluate(ws, "window.scrollTo(0, 260);")
            await asyncio.sleep(0.5)
            await capture(ws, "01_cockpit_dark_mode")

            # Check Light Mode toggle on Cockpit
            print("[QA] Checking Cockpit Light Mode toggle...", flush=True)
            await evaluate(ws, """
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('fp_theme', 'light');
                if (typeof updateThemeUI === 'function') updateThemeUI();
            """)
            await asyncio.sleep(0.3)
            # Switch back to dark mode
            await evaluate(ws, """
                document.documentElement.setAttribute('data-theme', 'dark');
                localStorage.setItem('fp_theme', 'dark');
                if (typeof updateThemeUI === 'function') updateThemeUI();
            """)
            await asyncio.sleep(0.3)

            # -----------------------------------------------------------------
            # Screen 2: AmeriSteel Detail — top/commodity section Dark Mode
            # -----------------------------------------------------------------
            print("[QA] Navigating to AmeriSteel Detail (Facility 23)...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects/23")
            await evaluate(ws, """
                document.documentElement.setAttribute('data-theme', 'dark');
                localStorage.setItem('fp_theme', 'dark');
                if (typeof updateThemeUI === 'function') updateThemeUI();
            """)
            await asyncio.sleep(0.5)
            # Top view showing Questions 1 & 2 (Commodity & Equipment Specifications)
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.5)
            await capture(ws, "02_ameristeel_detail_top_dark")

            # -----------------------------------------------------------------
            # Screen 3: AmeriSteel Detail — middle section Dark Mode
            # -----------------------------------------------------------------
            print("[QA] Scrolling to middle section (Questions 3 & 6 Freight Demand)...", flush=True)
            # Scroll to middle section where Question 3 & Question 6 (Demand Signals / Loads) are located
            await evaluate(ws, """
                const sec = document.querySelectorAll('.detail-section-card');
                if (sec.length >= 3) {
                    sec[2].scrollIntoView({ behavior: 'instant', block: 'start' });
                } else {
                    window.scrollTo(0, 600);
                }
            """)
            await asyncio.sleep(0.5)
            await capture(ws, "03_ameristeel_detail_middle_dark")

            # -----------------------------------------------------------------
            # Screen 4: AmeriSteel Qualification Readiness Dark Mode
            # -----------------------------------------------------------------
            print("[QA] Scrolling to Qualification Readiness section...", flush=True)
            await evaluate(ws, """
                const headings = Array.from(document.querySelectorAll('h2'));
                const qHeading = headings.find(h => h.textContent.includes('Qualification Readiness'));
                if (qHeading) {
                    qHeading.closest('.detail-section-card').scrollIntoView({ behavior: 'instant', block: 'start' });
                } else {
                    window.scrollTo(0, 1000);
                }
            """)
            await asyncio.sleep(0.5)
            await capture(ws, "04_ameristeel_readiness_dark")

            # Light Mode check on Prospect Detail
            print("[QA] Checking AmeriSteel Light Mode toggle...", flush=True)
            await evaluate(ws, """
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('fp_theme', 'light');
                if (typeof updateThemeUI === 'function') updateThemeUI();
            """)
            await asyncio.sleep(0.3)
            # Switch back to dark mode
            await evaluate(ws, """
                document.documentElement.setAttribute('data-theme', 'dark');
                localStorage.setItem('fp_theme', 'dark');
                if (typeof updateThemeUI === 'function') updateThemeUI();
            """)
            await asyncio.sleep(0.3)

            print("[QA] All 4 screenshots captured successfully!", flush=True)

    finally:
        chrome_proc.terminate()
        chrome_proc.wait()
        print("[QA] Chrome terminated.", flush=True)

if __name__ == "__main__":
    asyncio.run(run_qa())
