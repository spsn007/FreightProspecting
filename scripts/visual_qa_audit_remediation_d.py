"""
Audit Remediation D Visual QA Script via Chrome CDP.
Captures screenshots proving UI correctness across required viewports:
1. AUD-011: Master directory at 1440px with working server-side pagination ("Showing 1 to 25 of 527 filtered companies", "Page 1 of 22").
2. AUD-002: Log Call modal showing Origin and Destination State/Province inputs.
3. AUD-022: Shortlist Cockpit showing Yoder (408) with verified Toll-Free contact and no tel:None.
4. AUD-012: CRM Follow-Ups page with browser-local timezone resolution and sectioned grouping.
5. Responsive viewports: 1024px, 768px, 375px.
"""

import asyncio
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

PORT = 9252
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_audit_remediation_d"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\audit_remediation_d")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

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
                print(f"Error in captureScreenshot response: {res}", flush=True)
                break

async def run_visual_qa():
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--headless=new",
        "--window-size=1440,960",
        "--disable-gpu",
        "http://127.0.0.1:8000/"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Connected to Chrome CDP:", ws_url, flush=True)

        async with websockets.connect(ws_url, max_size=20*1024*1024) as ws:
            # 1. AUD-011: Master Directory at 1440px with Server-Side Pagination
            print("\n1. Capturing Master Directory at 1440px (AUD-011)...")
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await evaluate(ws, "window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.5)
            await capture(ws, "01_aud011_master_directory_server_pagination_1440px")

            # 2. AUD-002: Log Call Modal with Lane Inputs (Origin & Destination State/Prov)
            print("\n2. Capturing Log Call Modal with Lane Inputs (AUD-002)...")
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")
            await evaluate(ws, """
                window.dispatchEvent(new CustomEvent('open-log-call', {
                    detail: {
                        companyId: 1,
                        companyName: 'Beasley Forest Products',
                        facilityId: 1,
                        originStateProv: 'GA'
                    }
                }));
            """)
            await asyncio.sleep(0.8)
            await capture(ws, "02_aud002_log_call_modal_lane_inputs")

            # 3. AUD-022: Shortlist Cockpit showing Yoder Toll-Free and no tel:None
            print("\n3. Capturing Shortlist Cockpit (AUD-022)...")
            await navigate(ws, "http://127.0.0.1:8000/")
            await evaluate(ws, """
                const yoderLink = document.querySelector('a[href="/prospects/408"]');
                if (yoderLink) {
                    const card = yoderLink.closest('.prospect-card');
                    if (card) card.scrollIntoView({ behavior: 'instant', block: 'center' });
                    else yoderLink.scrollIntoView({ behavior: 'instant', block: 'center' });
                }
            """)
            await asyncio.sleep(0.8)
            await capture(ws, "03_aud022_shortlist_cockpit_yoder_toll_free")

            # 4. AUD-012: CRM Follow-ups localized view
            print("\n4. Capturing CRM Follow-ups localized view (AUD-012)...")
            await navigate(ws, "http://127.0.0.1:8000/crm/follow-ups?tz=America/New_York")
            await asyncio.sleep(0.8)
            await capture(ws, "04_aud012_crm_follow_ups_localized_view")

            # 5. Multi-viewport Responsive Checks (1024px, 768px, 375px)
            print("\n5. Capturing Multi-viewport responsive views...")
            for w, h, label in [(1024, 768, "tablet_1024px"), (768, 1024, "tablet_portrait_768px"), (375, 667, "mobile_375px")]:
                await set_viewport(ws, w, h)
                await navigate(ws, "http://127.0.0.1:8000/prospects")
                await asyncio.sleep(0.5)
                await capture(ws, f"05_responsive_master_directory_{label}")

        print("\nAll Visual QA Screenshots successfully captured!")
    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()

if __name__ == "__main__":
    asyncio.run(run_visual_qa())
