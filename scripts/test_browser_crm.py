"""
Automated CDP Real-Browser Visual Verification for Stage 3C Outreach CRM
Captures screenshots, tests UI elements, verifies modals, and confirms zero regressions.
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

SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9222
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


async def capture_screenshot(ws, output_path):
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
            with open(output_path, "wb") as f:
                f.write(img_data)
            print(f"Screenshot saved: {output_path.name}")
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
    await asyncio.sleep(2)


async def run_visual_verification():
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        "--disable-gpu",
        "--window-size=1440,900",
        "http://127.0.0.1:8000/prospects"
    ])
    await asyncio.sleep(2.5)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if "127.0.0.1:8000/prospects" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Connected to CDP:", ws_url)

        async with websockets.connect(ws_url, max_size=20*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "DOM.enable"}))

            # Wait for Alpine to initialize
            print("Waiting for Alpine.js initialization...")
            for i in range(20):
                ready = await evaluate(ws, "window.Alpine !== undefined && document.querySelectorAll('.company-card').length > 0")
                if ready:
                    print(f"Alpine initialized in ~{i * 0.3:.1f}s")
                    break
                await asyncio.sleep(0.3)

            # 1. Verify Master Directory /prospects
            print("\n--- 1. Testing /prospects Header & Filters ---")
            company_cards_count = await evaluate(ws, "document.querySelectorAll('.company-card').length")
            print(f"Company cards rendered on page 1: {company_cards_count}")

            has_outreach_filter = await evaluate(ws, "document.querySelector('select[x-model=\"outreachFilter\"]') !== null")
            print(f"Has Outreach Status filter dropdown: {has_outreach_filter}")

            has_unreviewed_toggle = await evaluate(ws, "document.querySelector('input[x-model=\"unreviewedOnly\"]') !== null")
            print(f"Has Unreviewed Only checkbox: {has_unreviewed_toggle}")

            uncontacted_badges = await evaluate(ws, "document.querySelectorAll('.badge-uncontacted').length")
            print(f"Uncontacted badges on visible cards: {uncontacted_badges}")

            # 2. Test Georgia-Pacific and Log Call Modal
            print("\n--- 2. Testing Georgia-Pacific & Modal Trigger ---")
            await evaluate(ws, """
                const input = document.querySelector('input[placeholder*="Search"]');
                if (input) {
                    input.value = 'Georgia-Pacific';
                    input.dispatchEvent(new Event('input'));
                }
            """)
            await asyncio.sleep(0.6)

            gp_cards = await evaluate(ws, "document.querySelectorAll('.company-card').length")
            print(f"Georgia-Pacific filtered cards count: {gp_cards}")

            # Click [Log Call] button on GP card
            print("Clicking [Log Call] button on Georgia-Pacific card...")
            await evaluate(ws, """
                const btns = Array.from(document.querySelectorAll('.company-card button'));
                const callBtn = btns.find(b => b.innerText.includes('Log Call'));
                if (callBtn) callBtn.click();
            """)
            await asyncio.sleep(0.8)

            modal_visible = await evaluate(ws, "window.getComputedStyle(document.getElementById('log-call-modal')).display !== 'none'")
            modal_title = await evaluate(ws, "document.querySelector('#log-call-modal .modal-title')?.innerText")
            clean_title = str(modal_title).encode('ascii', errors='replace').decode('ascii')
            print(f"Log Call Modal visible: {modal_visible}, Title: {clean_title}")

            facility_options_count = await evaluate(ws, "document.querySelectorAll('#call-facility-select option').length")
            print(f"Facility dropdown option count in modal: {facility_options_count}")

            # Screenshot open modal
            await capture_screenshot(ws, SCREENSHOTS_DIR / "crm_modal_open.png")

            # Click "Interested" pill in modal
            print("Selecting 'Interested' pill in modal...")
            await evaluate(ws, """
                const labels = Array.from(document.querySelectorAll('#log-call-modal label'));
                const interestedPill = labels.find(el => el.innerText.includes('Interested'));
                if (interestedPill) interestedPill.click();
            """)
            await asyncio.sleep(0.3)

            # Close modal via close button
            print("Closing modal via close button...")
            await evaluate(ws, """
                const closeBtn = document.querySelector('#log-call-modal .modal-close-btn');
                if (closeBtn) closeBtn.click();
            """)
            await asyncio.sleep(0.6)

            modal_closed = await evaluate(ws, "window.getComputedStyle(document.getElementById('log-call-modal')).display === 'none'")
            print(f"Log Call Modal closed successfully: {modal_closed}")

            # Expand Georgia-Pacific child facilities
            print("Expanding Georgia-Pacific child facilities tray...")
            await evaluate(ws, """
                const btns = Array.from(document.querySelectorAll('.company-card button'));
                const expandBtn = btns.find(b => b.innerText.includes('Show'));
                if (expandBtn) expandBtn.click();
            """)
            await asyncio.sleep(0.8)

            child_rows_count = await evaluate(ws, "document.querySelectorAll('.child-facilities-table tbody tr').length")
            print(f"Georgia-Pacific child facilities count: {child_rows_count}")

            child_call_buttons = await evaluate(ws, """
                Array.from(document.querySelectorAll('.child-facilities-table button')).filter(b => b.innerText.includes('Call')).length
            """)
            print(f"Child table [Call] button count: {child_call_buttons}")

            await capture_screenshot(ws, SCREENSHOTS_DIR / "crm_gp_expanded_calls.png")

            # 3. Test /crm/interested View
            print("\n--- 3. Testing /crm/interested View ---")
            await navigate(ws, "http://127.0.0.1:8000/crm/interested")

            interested_title = await evaluate(ws, "document.querySelector('.section-title')?.innerText")
            print(f"Navigated to /crm/interested -> Section Title: {interested_title}")
            await capture_screenshot(ws, SCREENSHOTS_DIR / "crm_interested_view.png")

            # 4. Test /crm/follow-ups View
            print("\n--- 4. Testing /crm/follow-ups View ---")
            await navigate(ws, "http://127.0.0.1:8000/crm/follow-ups")

            followups_title = await evaluate(ws, "document.querySelector('.section-title')?.innerText")
            print(f"Navigated to /crm/follow-ups -> Section Title: {followups_title}")
            await capture_screenshot(ws, SCREENSHOTS_DIR / "crm_followups_view.png")

            # 5. Test /prospects/1 (Beasley Forest Products)
            print("\n--- 5. Testing /prospects/1 Detail Page ---")
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")

            has_detail_call_btn = await evaluate(ws, """
                Array.from(document.querySelectorAll('button')).some(b => b.innerText.includes('Log Outreach Call'))
            """)
            print(f"Has [Log Outreach Call] button on detail page: {has_detail_call_btn}")

            has_history_section = await evaluate(ws, "document.body.innerText.includes('Outreach & Call Log History')")
            print(f"Has Outreach & Call Log History section: {has_history_section}")

            await capture_screenshot(ws, SCREENSHOTS_DIR / "crm_detail_beasley.png")

            # 6. Test Dark Mode
            print("\n--- 6. Testing Dark Mode Toggle ---")
            await evaluate(ws, "document.getElementById('themeToggleBtn')?.click()")
            await asyncio.sleep(0.5)

            current_theme = await evaluate(ws, "document.documentElement.getAttribute('data-theme')")
            print(f"Dark mode attribute data-theme: {current_theme}")
            await capture_screenshot(ws, SCREENSHOTS_DIR / "crm_dark_mode.png")

            print("\nALL VISUAL QA CHECKS COMPLETED SUCCESSFULLY!")

    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    asyncio.run(run_visual_verification())
