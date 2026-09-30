"""
Visual QA and Polish Verification Script for Stage 3D
Uses Headless Chrome over CDP to inspect and capture high-resolution screenshots.
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

SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\stage3d")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9226
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
            with open(p, "wb") as f:
                f.write(img_data)
            print(f"[SCREENSHOT] Saved: {p.name}", flush=True)
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
    await asyncio.sleep(0.9)

async def run_stage3d_qa():
    print(f"Launching Chrome Headless on port {PORT}...", flush=True)
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        "--disable-gpu",
        "--window-size=1440,900",
        "http://127.0.0.1:8000/"
    ])
    await asyncio.sleep(2.5)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Connected to CDP:", ws_url, flush=True)

        async with websockets.connect(ws_url, max_size=30*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "DOM.enable"}))

            # Helper for setting theme
            async def set_theme(theme):
                await evaluate(ws, f"document.documentElement.setAttribute('data-theme', '{theme}'); localStorage.setItem('fp_theme', '{theme}');")
                await asyncio.sleep(0.3)

            # ========================================================
            # 1. Cockpit in Light & Dark Mode
            # ========================================================
            print("\n--- 1. COCKPIT ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/")
            await set_theme("light")
            await capture(ws, "01_cockpit_light")
            await set_theme("dark")
            await capture(ws, "01_cockpit_dark")

            # ========================================================
            # 2. Master Directory: Companies View (Default)
            # ========================================================
            print("\n--- 2. MASTER DIRECTORY (DEFAULT COMPANIES VIEW) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("light")
            await capture(ws, "02_master_directory_companies_light")
            await set_theme("dark")
            await capture(ws, "02_master_directory_companies_dark")

            # ========================================================
            # 3. Master Directory: Expand 'More Filters' Drawer
            # ========================================================
            print("\n--- 3. MASTER DIRECTORY WITH 'MORE FILTERS' EXPANDED ---", flush=True)
            # Click More Filters button
            await evaluate(ws, """
                const btn = document.querySelector('button[title="Show additional filters"]') || Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Filters'));
                if (btn) btn.click();
            """)
            await asyncio.sleep(0.5)
            await capture(ws, "03_directory_more_filters_open_dark")
            await set_theme("light")
            await capture(ws, "03_directory_more_filters_open_light")

            # Close drawer before GP test
            await evaluate(ws, """
                const btn = document.querySelector('button[title="Show additional filters"]');
                if (btn) btn.click();
            """)
            await asyncio.sleep(0.3)

            # ========================================================
            # 4. Master Directory: Expand Georgia-Pacific
            # ========================================================
            print("\n--- 4. MASTER DIRECTORY: EXPAND GEORGIA-PACIFIC ---", flush=True)
            await evaluate(ws, """
                const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].companies);
                if (root) {
                    const d = root._x_dataStack[0];
                    d.searchQuery = "Georgia-Pacific";
                    d.resetPage();
                    const gp = d.filteredCompanies().find(c => c.operating_brand.includes('Georgia-Pacific'));
                    if (gp) d.expandedCompanies[gp.company_id] = true;
                }
            """)
            await set_theme("dark")
            await asyncio.sleep(0.6)
            await evaluate(ws, "window.scrollTo(0, 480);")
            await asyncio.sleep(0.3)
            await capture(ws, "04_directory_gp_expanded_dark")
            await set_theme("light")
            await capture(ws, "04_directory_gp_expanded_light")
            await set_theme("dark")
            await evaluate(ws, "window.scrollTo(0, 0);")

            # Reset search before Section 5
            await evaluate(ws, """
                const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].companies);
                if (root) {
                    const d = root._x_dataStack[0];
                    d.searchQuery = "";
                    d.expandedCompanies = {};
                    d.resetPage();
                }
            """)
            await asyncio.sleep(0.4)

            # ========================================================
            # 5. Master Directory: Switch to Facilities View
            # ========================================================
            print("\n--- 5. MASTER DIRECTORY: FACILITIES VIEW ---", flush=True)
            await evaluate(ws, """
                const facTab = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Facilities') && b.closest('.view-toggle-group'));
                if (facTab) facTab.click();
            """)
            await asyncio.sleep(0.5)
            await capture(ws, "05_directory_facilities_view_dark")
            await set_theme("light")
            await capture(ws, "05_directory_facilities_view_light")

            # Switch back to companies view
            await evaluate(ws, """
                const compTab = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Companies') && b.closest('.view-toggle-group'));
                if (compTab) compTab.click();
            """)
            await asyncio.sleep(0.3)

            # ========================================================
            # 6. Log Call Modal
            # ========================================================
            print("\n--- 6. LOG CALL MODAL ---", flush=True)
            await evaluate(ws, """
                window.dispatchEvent(new CustomEvent('open-log-call', {
                    detail: {
                        companyId: 1,
                        companyName: 'Beasley Forest Products',
                        facilityId: 1,
                        facilityName: 'Beasley Forest Products - Sandersville Hardwood Mill',
                        contactName: 'Darrell Beasley',
                        phoneNumber: '(912) 375-7111',
                        defaultDisposition: 'INTERESTED'
                    }
                }));
            """)
            await asyncio.sleep(0.5)
            await capture(ws, "06_log_call_modal_open_light")
            await set_theme("dark")
            await capture(ws, "06_log_call_modal_open_dark")

            # Close modal
            await evaluate(ws, """
                const cancelBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Cancel');
                if (cancelBtn) cancelBtn.click();
            """)
            await asyncio.sleep(0.3)

            # ========================================================
            # 7. Sidebar Accordion Interaction
            # ========================================================
            print("\n--- 7. SIDEBAR ACCORDIONS ---", flush=True)
            # Toggle Freight & Operations and Research & Data
            await evaluate(ws, """
                const opsHeader = Array.from(document.querySelectorAll('.sidebar-accordion-header')).find(h => h.textContent.includes('Freight & Operations'));
                if (opsHeader) opsHeader.click();
            """)
            await asyncio.sleep(0.4)
            await capture(ws, "07_sidebar_ops_open_dark")
            await set_theme("light")
            await capture(ws, "07_sidebar_ops_open_light")

            # ========================================================
            # 8. CRM Workflow Views
            # ========================================================
            print("\n--- 8. CRM WORKFLOW QUEUES ---", flush=True)
            crm_views = [
                ("/crm/interested", "08_crm_interested"),
                ("/crm/follow-ups", "09_crm_follow_ups"),
                ("/crm/no-answer", "10_crm_no_answer"),
                ("/crm/not-interested", "11_crm_not_interested"),
            ]
            for url, label in crm_views:
                await navigate(ws, f"http://127.0.0.1:8000{url}")
                await set_theme("light")
                await capture(ws, f"{label}_light")
                await set_theme("dark")
                await capture(ws, f"{label}_dark")

            # ========================================================
            # 9. Prospect Detail Page
            # ========================================================
            print("\n--- 9. PROSPECT DETAIL (BEASLEY) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")
            await set_theme("light")
            await capture(ws, "12_prospect_detail_beasley_light")
            await set_theme("dark")
            await capture(ws, "12_prospect_detail_beasley_dark")

            print("\n=== ALL STAGE 3D VISUAL QA SCREENSHOTS COMPLETED SUCCESSFULLY! ===", flush=True)

    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    asyncio.run(run_stage3d_qa())
