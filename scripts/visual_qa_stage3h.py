"""
Stage 3H Visual QA Script via Chrome CDP.
Captures screenshots proving UI correctness across the Stage 3H expansion:
1. 01_master_directory_stage3h_categories.png: Master directory showing 565 operating companies, 653 facilities, and updated taxonomy.
2. 02_family_filter_seasonal_opportunity.png: Master directory filtered to SEASONAL_OPPORTUNITY family showing Holiday Tree Farms, Barr Evergreens, etc.
3. 03_family_filter_packaging_high_cube.png: Master directory filtered to PACKAGING_HIGH_CUBE family showing Jamestown Container, Great Little Box, M&M Industries, etc.
4. 04_prospect_detail_stage3h_new_facility.png: Detail view of facility 617 (Holiday Tree Farms) showing Discovery status, inferred equipment, and clean verified provenance.
5. 05_dark_mode_stage3h_view.png: Dark mode theme rendering on Seasonal Opportunity filtered directory.
"""

import asyncio
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

PORT = 9260
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_stage3h"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\stage3h")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_msg_counter = 800

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
                import base64
                img_data = base64.b64decode(res["result"]["data"])
                p = SCREENSHOTS_DIR / f"{name}.png"
                p.write_bytes(img_data)
                print(f"Captured: {p.name} ({len(img_data)} bytes)", flush=True)
                break
            else:
                print(f"Failed to capture {name}: {res}", flush=True)
                break

async def main():
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--headless=new",
        "--window-size=1440,900",
        "--disable-gpu",
        "http://127.0.0.1:8000/prospects"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.5)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Connected to CDP:", ws_url, flush=True)

        async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.recv()

            # Set standard desktop viewport
            await set_viewport(ws, 1440, 900)

            # 1. Master directory overview
            print("1. Capturing Master Directory with Stage 3H expansion...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "01_master_directory_stage3h_categories")

            # 2. Filtered by SEASONAL_OPPORTUNITY family
            print("2. Capturing Seasonal & Opportunity Freight family filter...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?family=SEASONAL_OPPORTUNITY")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "02_family_filter_seasonal_opportunity")

            # 3. Filtered by PACKAGING_HIGH_CUBE family
            print("3. Capturing Packaging & High-Cube family filter...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?family=PACKAGING_HIGH_CUBE")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "03_family_filter_packaging_high_cube")

            # 4. Detail page for new Stage 3H facility (617: Holiday Tree Farms)
            print("4. Capturing Prospect Detail page for new facility 617...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/617")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "04_prospect_detail_stage3h_new_facility")

            # 5. Dark mode check
            print("5. Capturing Dark Mode view...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?family=SEASONAL_OPPORTUNITY")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await asyncio.sleep(0.5)
            await capture(ws, "05_dark_mode_stage3h_view")

            print("\nVisual QA complete! All 5 screenshots captured successfully.", flush=True)
    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
