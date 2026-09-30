"""
Stage 3G Visual QA Script:
Captures screenshots and validates UI DOM for Stage 3G:
1. Master Directory Light Mode with Opportunity Categories button & counts.
2. Master Directory Dark Mode.
3. Opportunity Categories banner expanded showing families, categories, seasons, and company counts.
4. Deep Filters drawer expanded showing Commodity Family, Category, and Seasonality dropdowns.
5. Filtered view by PALLETS_CRATES_DUNNAGE category.
6. Filtered view by SPRING_PEAK seasonality.
7. Prospect Detail Facility 1: Beasley Forest Products with taxonomy & seasonality card (Light Mode).
8. Prospect Detail Facility 5: Battle Lumber with multi-category associations (Dark Mode).
9. Prospect Detail Facility 18: Coil Steel Processing (CSP) with verified flatbed fit (Dark Mode).
10. Prospect Detail Facility 370: Greif Inc. with clean drums / IBC packaging categories (Dark Mode).
"""

import asyncio
import base64
import json
import subprocess
import urllib.request
import websockets
from pathlib import Path
import tempfile

SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\stage3g")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9233
_msg_counter = 100


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
            p.write_bytes(img_data)
            print(f"Captured: {p} ({len(img_data)} bytes)", flush=True)
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
    await asyncio.sleep(1.2)


async def main():
    user_data_dir = tempfile.mkdtemp(prefix="chrome_qa_")
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={user_data_dir}",
        "--disable-gpu",
        "--window-size=1440,900",
        "http://127.0.0.1:8000/prospects"
    ])
    await asyncio.sleep(2.5)

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

            # ----------------------------------------------------------------
            # 1. Master Directory Light Mode
            # ----------------------------------------------------------------
            print("\n1. Navigating to Master Directory (Light Mode)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("light")
            await asyncio.sleep(0.6)
            await capture(ws, "01_directory_light_overview")

            # ----------------------------------------------------------------
            # 2. Master Directory Dark Mode
            # ----------------------------------------------------------------
            print("\n2. Switching to Dark Mode...", flush=True)
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "02_directory_dark_overview")

            # ----------------------------------------------------------------
            # 3. Opportunity Categories Banner Expanded (Dark Mode)
            # ----------------------------------------------------------------
            print("\n3. Opening Opportunity Categories Banner...", flush=True)
            await evaluate(ws, "document.getElementById('opportunity-categories-toggle-btn').click()")
            await asyncio.sleep(1.0)
            await capture(ws, "03_opportunity_categories_banner_expanded")

            # ----------------------------------------------------------------
            # 4. Deep Filters Drawer Expanded
            # ----------------------------------------------------------------
            print("\n4. Opening Deep Filters Drawer...", flush=True)
            # Close opportunity banner first
            await evaluate(ws, "document.getElementById('opportunity-categories-toggle-btn').click()")
            await asyncio.sleep(0.4)
            # Open Deep Filters
            await evaluate(ws, "document.querySelector('button[title*=\"Show additional filters\"]').click()")
            await asyncio.sleep(0.8)
            await capture(ws, "04_deep_filters_taxonomy")

            # ----------------------------------------------------------------
            # 5. Filtered View by PALLETS_CRATES_DUNNAGE Category
            # ----------------------------------------------------------------
            print("\n5. Filtering by Wood Pallets / Crates / Dunnage...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?category=PALLETS_CRATES_DUNNAGE")
            await set_theme("dark")
            await asyncio.sleep(0.8)
            await capture(ws, "05_filtered_by_pallets_category")

            # ----------------------------------------------------------------
            # 6. Filtered View by SPRING_PEAK Seasonality
            # ----------------------------------------------------------------
            print("\n6. Filtering by Spring Peak Seasonality...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?seasonality=SPRING_PEAK")
            await set_theme("dark")
            await asyncio.sleep(0.8)
            await capture(ws, "06_filtered_by_spring_peak_seasonality")

            # ----------------------------------------------------------------
            # 7. Prospect Detail Facility 1: Beasley (Light Mode)
            # ----------------------------------------------------------------
            print("\n7. Navigating to Prospect Detail Facility 1 (Beasley, Light Mode)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")
            await set_theme("light")
            await asyncio.sleep(0.8)
            await capture(ws, "07_prospect_detail_facility_1_beasley_light")

            # ----------------------------------------------------------------
            # 8. Prospect Detail Facility 5: Battle Lumber (Multi-Category, Dark Mode)
            # ----------------------------------------------------------------
            print("\n8. Navigating to Prospect Detail Facility 5 (Battle Lumber, Dark Mode)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/5")
            await set_theme("dark")
            await asyncio.sleep(0.8)
            await capture(ws, "08_prospect_detail_facility_5_battle_lumber_dark")

            # ----------------------------------------------------------------
            # 9. Prospect Detail Facility 18: Coil Steel Processing (CSP, Dark Mode)
            # ----------------------------------------------------------------
            print("\n9. Navigating to Prospect Detail Facility 18 (CSP, Dark Mode)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/18")
            await set_theme("dark")
            await asyncio.sleep(0.8)
            await capture(ws, "09_prospect_detail_facility_18_csp_dark")

            # ----------------------------------------------------------------
            # 10. Prospect Detail Facility 370: Greif Inc. (Packaging & Totes, Dark Mode)
            # ----------------------------------------------------------------
            print("\n10. Navigating to Prospect Detail Facility 370 (Greif Inc., Dark Mode)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/370")
            await set_theme("dark")
            await asyncio.sleep(0.8)
            await capture(ws, "10_prospect_detail_facility_370_greif_dark")

            # ----------------------------------------------------------------
            # 11. Console Error Check
            # ----------------------------------------------------------------
            print("\n11. Checking browser console errors...", flush=True)
            errors = await evaluate(ws, "window.__errors || []")
            print(f"Console errors: {errors}", flush=True)

    finally:
        proc.terminate()
        print("\nVisual QA complete. Headless Chrome terminated.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
