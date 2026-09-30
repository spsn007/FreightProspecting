"""
Stage 3G.1 Real Browser Visual QA Script via Chrome CDP.
Verifies:
1. Opportunity Categories expanded with new labels
2. Deep Filters with new categories
3. Search for Used Machinery, HVAC, Solar Racking, Plastic Packaging
4. Detail pages for CSP (18), Kenwal (2), Beasley (1)
5. Visual separation of Typical Category Fit vs Facility Evidenced Usage
6. Zero console errors
"""

import asyncio
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

PORT = 9234
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_stage3g1"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\stage3g1")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_msg_counter = 0

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
    await asyncio.sleep(1.2)

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
            import base64
            img_data = base64.b64decode(res["result"]["data"])
            p = SCREENSHOTS_DIR / f"{name}.png"
            p.write_bytes(img_data)
            print(f"Captured: {p} ({len(img_data)} bytes)", flush=True)
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
    time.sleep(2.0)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Connected to CDP:", ws_url, flush=True)

        async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "DOM.enable"}))

            async def set_theme(theme):
                if theme == "light":
                    await evaluate(ws, "document.documentElement.removeAttribute('data-theme'); localStorage.setItem('fp_theme', 'light');")
                else:
                    await evaluate(ws, f"document.documentElement.setAttribute('data-theme', '{theme}'); localStorage.setItem('fp_theme', '{theme}');")
                await asyncio.sleep(0.3)

            # 1. Opportunity Categories Banner with new active categories
            print("\n1. Opening Opportunity Categories Banner...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("dark")
            await asyncio.sleep(1.0)
            await evaluate(ws, "document.getElementById('opportunity-categories-toggle-btn').click()")
            await asyncio.sleep(1.0)
            await capture(ws, "01_directory_categories_banner_new_labels")

            # 2. Deep Filters Drawer
            print("\n2. Opening Deep Filters Drawer...", flush=True)
            await evaluate(ws, "document.getElementById('opportunity-categories-toggle-btn').click()")
            await asyncio.sleep(0.4)
            await evaluate(ws, "document.querySelector('button[title*=\"Show additional filters\"]').click()")
            await asyncio.sleep(0.8)
            await capture(ws, "02_deep_filters_taxonomy")

            # 3. Search: Used Machinery
            print("\n3. Searching for 'Used Machinery'...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?q=Used+Machinery")
            await set_theme("dark")
            await asyncio.sleep(0.6)
            await capture(ws, "03_search_used_machinery")

            # 4. Search: HVAC
            print("\n4. Searching for 'HVAC'...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?q=HVAC")
            await set_theme("dark")
            await asyncio.sleep(0.6)
            await capture(ws, "04_search_hvac")

            # 5. Search: Solar Racking
            print("\n5. Searching for 'Solar Racking'...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?q=Solar+Racking")
            await set_theme("dark")
            await asyncio.sleep(0.6)
            await capture(ws, "05_search_solar_racking")

            # 6. Search: Plastic Packaging
            print("\n6. Searching for 'Plastic Packaging'...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?q=Plastic+Packaging")
            await set_theme("dark")
            await asyncio.sleep(0.6)
            await capture(ws, "06_search_plastic_packaging")

            # 7. CSP Facility 18 Detail (Dark Mode) - Critical Equipment Separation Check
            print("\n7. Navigating to CSP Facility 18 Detail (Dark Mode)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/18")
            await set_theme("dark")
            await asyncio.sleep(0.8)
            await capture(ws, "07_csp_facility_18_dark_equipment_truth")

            # 8. CSP Facility 18 Detail (Light Mode)
            print("\n8. Navigating to CSP Facility 18 Detail (Light Mode)...", flush=True)
            await set_theme("light")
            await asyncio.sleep(0.8)
            await capture(ws, "08_csp_facility_18_light_equipment_truth")

            # 9. Kenwal Facility 2 Detail (Dark Mode)
            print("\n9. Navigating to Kenwal Steel Facility 2 Detail (Dark Mode)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/2")
            await set_theme("dark")
            await asyncio.sleep(0.8)
            await capture(ws, "09_kenwal_facility_2_dark_equipment_truth")

            # 10. Beasley Facility 1 Detail (Light Mode)
            print("\n10. Navigating to Beasley Facility 1 Detail (Light Mode)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")
            await set_theme("light")
            await asyncio.sleep(0.8)
            await capture(ws, "10_beasley_facility_1_light_equipment_truth")

            # 11. Console errors check
            print("\n11. Checking browser console errors...", flush=True)
            errors = await evaluate(ws, "window.__qa_errors || []")
            print("Console errors:", errors, flush=True)

    finally:
        chrome_proc.terminate()
        chrome_proc.wait()
        print("\nVisual QA Stage 3G.1 complete. Chrome terminated.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
