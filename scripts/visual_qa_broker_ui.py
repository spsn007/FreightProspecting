"""
Visual QA Script for FreightProspecting Broker-First UI/UX Simplification via Chrome CDP.
Spawns a clean local Uvicorn instance on port 8008 and executes Chrome CDP automation
to capture all 11 required screenshots into the artifact directory:

1. 01_master_directory_dark_mode_default.png:
   Master directory in dark mode showing universe totals (565 companies, 653 facilities),
   tab pill badges, high-contrast active tab, and broker cards (WHO, STATUS, WHY, CONTACT, ACTIONS).
2. 02_master_directory_light_mode_default.png:
   Master directory in light mode default view showing clean card surfaces and contrast.
3. 03_search_single_char_s.png:
   Server-side search with single-character "S" showing full universe search and filtered counts.
4. 04_search_steel.png:
   Server-side search for "Steel" showing cross-universe matching companies.
5. 05_ready_to_contact_tab.png:
   "Ready to Contact" (QUALIFIED) lifecycle tab showing 91 companies.
6. 06_discovery_tab.png:
   "Still Being Researched" (DISCOVERY) lifecycle tab showing 445 companies with What We Know / Still Checking.
7. 07_simplified_qualified_card.png:
   Focused view of a simplified Qualified card with why bullets, phone card, and actions.
8. 08_simplified_shortlisted_card.png:
   Focused view of a simplified Shortlisted (Priority Prospect) card.
9. 09_simplified_discovery_card.png:
   Focused view of a simplified Discovery card with research action.
10. 10_cockpit_dark_mode.png:
    Cockpit page in dark mode showing styled .hero-banner (#1e293b surface, #334155 border, high contrast text).
11. 11_mobile_375px_view.png:
    Master directory on 375px mobile viewport showing responsive stacking and tap targets.
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

APP_PORT = 8008
CDP_PORT = 9270
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_broker_ui"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\broker_ui")
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
            "mobile": width <= 768,
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
    # 1. Start clean uvicorn server on port APP_PORT
    print(f"[QA] Starting Uvicorn server on port {APP_PORT}...", flush=True)
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.backend.main:app", "--port", str(APP_PORT), "--host", "127.0.0.1"],
        cwd=r"D:\FreightProspecting",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Poll until server is ready
    server_ready = False
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/prospects", timeout=1) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.5)

    if not server_ready:
        print("[QA] ERROR: Server failed to start!", flush=True)
        server_proc.terminate()
        return

    print("[QA] Server is responsive on port 8008.", flush=True)

    # 2. Start Chrome with remote debugging
    print(f"[QA] Starting Chrome on debug port {CDP_PORT}...", flush=True)
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--headless=new",
        "--window-size=1440,900",
        "--disable-gpu",
        f"http://127.0.0.1:{APP_PORT}/prospects"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page" and f"127.0.0.1:{APP_PORT}" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("[QA] Connected to Chrome CDP:", ws_url, flush=True)

        async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.recv()

            # Set standard desktop viewport
            await set_viewport(ws, 1440, 900)

            # -------------------------------------------------------------
            # 1. 01_master_directory_dark_mode_default
            # -------------------------------------------------------------
            print("\n1. Capturing Master Directory in Dark Mode...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "01_master_directory_dark_mode_default")

            # -------------------------------------------------------------
            # 2. 02_master_directory_light_mode_default
            # -------------------------------------------------------------
            print("\n2. Capturing Master Directory in Light Mode...", flush=True)
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('fp_theme', 'light');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "02_master_directory_light_mode_default")

            # Reset back to dark mode for consistent broker viewing
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")

            # -------------------------------------------------------------
            # 3. 03_search_single_char_s
            # -------------------------------------------------------------
            print("\n3. Capturing Single-Char Search 'S'...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?q=S")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "03_search_single_char_s")

            # -------------------------------------------------------------
            # 4. 04_search_steel
            # -------------------------------------------------------------
            print("\n4. Capturing Full Search 'Steel'...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?q=Steel")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "04_search_steel")

            # -------------------------------------------------------------
            # 5. 05_ready_to_contact_tab
            # -------------------------------------------------------------
            print("\n5. Capturing 'Ready to Contact' (QUALIFIED) Tab...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?stage=QUALIFIED")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "05_ready_to_contact_tab")

            # -------------------------------------------------------------
            # 6. 06_discovery_tab
            # -------------------------------------------------------------
            print("\n6. Capturing 'Still Being Researched' (DISCOVERY) Tab...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?stage=DISCOVERY")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "06_discovery_tab")

            # -------------------------------------------------------------
            # 7. 07_simplified_qualified_card
            # -------------------------------------------------------------
            print("\n7. Capturing Simplified Qualified Card Close-up...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?stage=QUALIFIED")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 420);")
            await asyncio.sleep(0.8)
            await capture(ws, "07_simplified_qualified_card")

            # -------------------------------------------------------------
            # 8. 08_simplified_shortlisted_card
            # -------------------------------------------------------------
            print("\n8. Capturing Simplified Shortlisted (Priority Prospect) Card Close-up...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?stage=SHORTLISTED")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 420);")
            await asyncio.sleep(0.8)
            await capture(ws, "08_simplified_shortlisted_card")

            # -------------------------------------------------------------
            # 9. 09_simplified_discovery_card
            # -------------------------------------------------------------
            print("\n9. Capturing Simplified Discovery Card Close-up...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?stage=DISCOVERY")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 420);")
            await asyncio.sleep(0.8)
            await capture(ws, "09_simplified_discovery_card")

            # -------------------------------------------------------------
            # 10. 10_cockpit_dark_mode
            # -------------------------------------------------------------
            print("\n10. Capturing Cockpit in Dark Mode...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "10_cockpit_dark_mode")

            # -------------------------------------------------------------
            # 11. 11_mobile_375px_view
            # -------------------------------------------------------------
            print("\n11. Capturing Mobile 375px View...", flush=True)
            await set_viewport(ws, 375, 812)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 700);")
            await asyncio.sleep(1.0)
            await capture(ws, "11_mobile_375px_view")

            print("\n[QA] All 11 visual QA screenshots successfully captured!", flush=True)

    finally:
        print("[QA] Cleaning up Chrome and Uvicorn...", flush=True)
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()

        server_proc.terminate()
        try:
            server_proc.wait(timeout=3)
        except Exception:
            server_proc.kill()
        print("[QA] Clean shutdown complete.", flush=True)

if __name__ == "__main__":
    asyncio.run(run_qa())
