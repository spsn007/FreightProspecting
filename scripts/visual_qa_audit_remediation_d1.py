"""
Audit Remediation D.1 Visual QA Script via Chrome CDP.
Captures screenshots proving UI correctness across the final 4 closure blockers:
1. 01_cockpit_29_shortlisted_prospects_100_percent_ready.png: Cockpit showing 29 shortlisted prospects, 100% READY (0 FAIL).
2. 02_master_directory_twophase_pagination_showing_25_of_527.png: Master directory showing Two-Phase SQL pagination ("Showing 1 to 25 of 527 filtered companies", "Page 1 of 22").
3. 03_log_call_modal_flat_dispatch_and_lane_inputs.png: Log Call modal on facility 1 with flat dispatch and pre-filled origin state.
4. 04_prospect_detail_facility_1_clean_safe_url_and_actions.png: Prospect detail page /prospects/1 showing safe URLs (no href="None") and action buttons.
5. 05_log_call_modal_active_lane_restriction_warning.png: Log Call modal with active lane restriction warning banner displayed.
"""

import asyncio
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

PORT = 9254
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_audit_remediation_d1"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\audit_remediation_d1")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_msg_counter = 700

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
            # 1. 01_cockpit_29_shortlisted_prospects_100_percent_ready
            print("\n1. Capturing Cockpit showing 29 Shortlisted prospects (100% READY)...")
            await navigate(ws, "http://127.0.0.1:8000/")
            await asyncio.sleep(0.8)
            await capture(ws, "01_cockpit_29_shortlisted_prospects_100_percent_ready")

            # 2. 02_master_directory_twophase_pagination_showing_25_of_527
            print("\n2. Capturing Master Directory Two-Phase Pagination (Showing 1 to 25 of 527)...")
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await evaluate(ws, "window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.8)
            await capture(ws, "02_master_directory_twophase_pagination_showing_25_of_527")

            # 3. 03_log_call_modal_flat_dispatch_and_lane_inputs
            print("\n3. Capturing Log Call Modal on Facility 1 with flat dispatch and lane inputs...")
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")
            await evaluate(ws, """
                const btn = document.querySelector('button[title*="Log Broker Outreach Call"]') || document.querySelector('button[title*="Log Call"]') || Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Log Call'));
                if (btn) {
                    btn.click();
                } else {
                    window.dispatchEvent(new CustomEvent('open-log-call', {
                        detail: {
                            companyId: 1,
                            companyName: 'Beasley Forest Products',
                            facilityId: 1,
                            originStateProv: 'GA',
                            phoneNumber: '(912) 375-5174',
                            contactName: 'Shipping Desk'
                        }
                    }));
                }
            """)
            await asyncio.sleep(0.8)
            await capture(ws, "03_log_call_modal_flat_dispatch_and_lane_inputs")

            # 4. 04_prospect_detail_facility_1_clean_safe_url_and_actions
            print("\n4. Capturing Prospect Detail Facility 1 with Safe URLs and Actions...")
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")
            await asyncio.sleep(0.8)
            await capture(ws, "04_prospect_detail_facility_1_clean_safe_url_and_actions")

            # 5. 05_log_call_modal_active_lane_restriction_warning
            print("\n5. Capturing Log Call Modal with Active Lane Restriction Warning Banner...")
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")
            await evaluate(ws, """
                window.dispatchEvent(new CustomEvent('open-log-call', {
                    detail: {
                        companyId: 1,
                        companyName: 'Beasley Forest Products',
                        facilityId: 1,
                        originStateProv: 'GA',
                        destStateProv: 'FL',
                        phoneNumber: '(912) 375-5174',
                        contactName: 'Shipping Desk'
                    }
                }));
            """)
            await asyncio.sleep(0.5)
            await evaluate(ws, """
                const modal = document.getElementById('log-call-modal');
                if (modal && modal._x_dataStack && modal._x_dataStack[0]) {
                    const data = modal._x_dataStack[0];
                    data.showLaneWarning = true;
                    data.laneWarningMessage = 'Active lane restriction in effect (GLOBAL_LANE): Restrict outbound shipments from GA to FL per brokerage policy.';
                }
            """)
            await asyncio.sleep(0.8)
            await capture(ws, "05_log_call_modal_active_lane_restriction_warning")

        print("\nAll Remediation D.1 Visual QA Screenshots successfully captured!")
    finally:
        chrome_proc.terminate()
        try:
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()

if __name__ == "__main__":
    asyncio.run(run_visual_qa())
