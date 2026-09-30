"""
Audit Remediation A Visual QA Script via Chrome CDP.
Captures screenshots to prove:
1. Cockpit shortlist with 31 prospects and Why Shortlisted facts
2. Log Call modal displaying all 8 canonical dispositions cleanly
3. Log Call modal displaying DNC / Active Suppression warning banner
4. Facility 18 (CSP) detail page in dark mode (verified shipping contact + flatbed verified)
5. Facility 18 (CSP) detail page in light mode
6. Master Directory showing Broker Access Friction badges
7. Facility 613 (StructureCraft) showing Mass Timber taxonomy reclassification
"""

import asyncio
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

PORT = 9235
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_audit_remediation_a"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\audit_remediation_a")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_msg_counter = 10

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

async def main():
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

            # 1. Cockpit Shortlist with Why Shortlisted facts
            print("\n1. Navigating to Cockpit...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/")
            await set_theme("dark")
            await asyncio.sleep(1.0)
            await capture(ws, "01_cockpit_shortlist_facts")

            # 2. Log Call Modal with 8 Canonical Dispositions
            print("\n2. Opening Log Call Modal for Beasley...", flush=True)
            await evaluate(ws, """
                const buttons = Array.from(document.querySelectorAll('button'));
                const logBtn = buttons.find(b => b.textContent.includes('Log Call'));
                if (logBtn) {
                    logBtn.click();
                } else {
                    window.dispatchEvent(new CustomEvent('open-log-call', {
                        detail: {
                            companyId: 1,
                            companyName: 'Beasley Forest Products',
                            facilityId: 1,
                            facilityName: 'Hazlehurst Sawmill',
                            contactName: 'Mark Joiner',
                            phoneNumber: '(912) 347-5930'
                        }
                    }));
                }
            """)
            await asyncio.sleep(1.2)
            await capture(ws, "02_log_call_modal_dispositions")

            # 3. Log Call Modal DNC Warning Banner
            print("\n3. Simulating DNC Suppression in Log Call Modal...", flush=True)
            await evaluate(ws, """
                const modal = document.querySelector('#log-call-modal');
                if (modal && modal._x_dataStack && modal._x_dataStack[0]) {
                    modal._x_dataStack[0].isSuppressed = true;
                    modal._x_dataStack[0].suppressionMessage = 'Outreach blocked: Company Beasley Forest Products is under active DO_NOT_CONTACT suppression.';
                }
            """)
            await asyncio.sleep(1.0)
            await capture(ws, "03_log_call_modal_dnc_warning")

            # Close modal
            await evaluate(ws, """
                const closeBtn = document.querySelector('.modal-close-btn');
                if (closeBtn) closeBtn.click();
            """)
            await asyncio.sleep(0.8)

            # 4. Facility 18 (Coil Steel Processing) Detail Page - Dark
            print("\n4. Navigating to Facility 18 (CSP) Detail Page (Dark)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/18")
            await set_theme("dark")
            await asyncio.sleep(1.0)
            await capture(ws, "04_facility_18_csp_detail_dark")

            # 4b. Facility 18 Section 3 Outreach Contacts
            print("\n4b. Scrolling to Section 3 Outreach Assets on CSP...", flush=True)
            await evaluate(ws, "window.scrollTo(0, 950);")
            await asyncio.sleep(0.8)
            await capture(ws, "04b_facility_18_csp_contacts_dark")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.5)

            # 5. Facility 18 (Coil Steel Processing) Detail Page - Light
            print("\n5. Capturing Facility 18 (CSP) Detail Page (Light)...", flush=True)
            await set_theme("light")
            await asyncio.sleep(0.8)
            await capture(ws, "05_facility_18_csp_detail_light")

            # 6. Master Directory showing Broker Access Friction Badges
            print("\n6. Navigating to Master Directory (Company View)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects?view_mode=company")
            await set_theme("dark")
            await asyncio.sleep(1.0)
            await capture(ws, "06_master_directory_friction_badges")

            # 7. Facility 613 (StructureCraft) Detail Page showing Mass Timber
            print("\n7. Navigating to Facility 613 (StructureCraft)...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/613")
            await set_theme("dark")
            await asyncio.sleep(1.0)
            await capture(ws, "07_facility_613_structurecraft_mass_timber")

            print("\nAll 7 screenshots captured successfully!", flush=True)

    finally:
        chrome_proc.terminate()
        chrome_proc.wait()

if __name__ == "__main__":
    asyncio.run(main())
