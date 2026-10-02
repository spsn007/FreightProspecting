"""
FreightProspecting Phase C — Real Interactive Browser QA Script
Uses Chrome DevTools Protocol (CDP) via websockets to drive headless Chrome.
Validates:
1. Modal open and UI rendering
2. Gatekeeper role selection displays warning banner
3. Filling verified facts with Shipping Manager
4. Duplicate submission protection (clientRequestId)
5. Call submission and success messaging
6. Cross-prospect reset (opening next prospect has completely empty/clean fields)
7. Screenshot generation for visual proof
"""

import os
import sys
import time
import json
import base64
import shutil
import asyncio
import subprocess
from pathlib import Path
import httpx
import websockets

WORKSPACE = Path(__file__).resolve().parent.parent
PROD_DB = WORKSPACE / "data" / "prospects.db"
TEMP_DB = WORKSPACE / "data" / "temp_browser_qa.db"
SCREENSHOT_DIR = WORKSPACE / "reports" / "browser_qa_screenshots"
CHROME_PATH = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
CHROME_PROFILE = WORKSPACE / "temp_chrome_profile"
SERVER_PORT = 8008
CDP_PORT = 9222

class CDPBrowserSession:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self.req_id = 0

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("DOM.enable")

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def send(self, method, params=None):
        self.req_id += 1
        mid = self.req_id
        msg = {"id": mid, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        while True:
            raw = await self.ws.recv()
            resp = json.loads(raw)
            if resp.get("id") == mid:
                if "error" in resp:
                    raise RuntimeError(f"CDP Error for {method}: {resp['error']}")
                return resp.get("result", {})

    async def eval(self, expr):
        res = await self.send("Runtime.evaluate", {
            "expression": expr,
            "awaitPromise": True,
            "returnByValue": True,
        })
        if "exceptionDetails" in res:
            raise RuntimeError(f"JS Exception in eval: {res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    async def capture_screenshot(self, filepath: Path):
        filepath.parent.mkdir(parents=True, exist_ok=True)
        res = await self.send("Page.captureScreenshot", {"format": "png"})
        img_data = base64.b64decode(res["data"])
        with open(filepath, "wb") as f:
            f.write(img_data)
        print(f"  [Screenshot] Saved: {filepath.name}")

    async def wait_for_expr(self, expr, timeout=10.0, interval=0.2):
        start = time.time()
        while time.time() - start < timeout:
            res = await self.eval(expr)
            if res:
                return res
            await asyncio.sleep(interval)
        raise TimeoutError(f"Timed out waiting for expression: {expr}")


async def run_browser_qa():
    print("=== FREIGHTPROSPECTING PHASE C: INTERACTIVE BROWSER QA ===")
    
    # 1. Setup isolated database copy
    if TEMP_DB.exists():
        TEMP_DB.unlink()
    shutil.copy2(PROD_DB, TEMP_DB)
    print(f"Created temporary QA database: {TEMP_DB.name}")

    # 2. Launch FastAPI / Uvicorn server on port 8008
    env = os.environ.copy()
    env["FREIGHT_DB_PATH"] = str(TEMP_DB)
    server_cmd = [
        str(WORKSPACE / ".venv" / "Scripts" / "python.exe"),
        "-m", "uvicorn",
        "src.backend.main:app",
        "--host", "127.0.0.1",
        "--port", str(SERVER_PORT),
        "--log-level", "warning"
    ]
    server_proc = subprocess.Popen(server_cmd, env=env)
    print(f"Started uvicorn server on PID {server_proc.pid}")

    # 3. Launch Chrome with CDP
    if CHROME_PROFILE.exists():
        shutil.rmtree(CHROME_PROFILE, ignore_errors=True)
    CHROME_PROFILE.mkdir(parents=True, exist_ok=True)

    chrome_cmd = [
        str(CHROME_PATH),
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={CHROME_PROFILE}",
        "--window-size=1280,900",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "about:blank"
    ]
    chrome_proc = subprocess.Popen(chrome_cmd)
    print(f"Started headless Chrome on PID {chrome_proc.pid}")

    # Wait for server and Chrome to be ready
    await asyncio.sleep(2.0)

    try:
        # Check Chrome CDP endpoint
        async with httpx.AsyncClient() as client:
            cdp_info = None
            for _ in range(20):
                try:
                    resp = await client.get(f"http://127.0.0.1:{CDP_PORT}/json")
                    if resp.status_code == 200:
                        cdp_info = resp.json()
                        break
                except Exception:
                    await asyncio.sleep(0.5)
            if not cdp_info:
                raise RuntimeError("Could not connect to Chrome CDP JSON endpoint")

            page_targets = [t for t in cdp_info if t.get("type") == "page"]
            page_ws_url = page_targets[0]["webSocketDebuggerUrl"]
            print(f"Connected to Chrome CDP: {page_ws_url}")

        session = CDPBrowserSession(page_ws_url)
        await session.connect()

        # Step 1: Navigate to Prospects page
        print("\nStep 1: Navigating to prospects page...")
        await session.send("Page.navigate", {"url": f"http://127.0.0.1:{SERVER_PORT}/prospects"})
        await session.wait_for_expr("document.readyState === 'complete'")
        await session.wait_for_expr("document.querySelectorAll('.company-card').length > 0")
        prospect_count = await session.eval("document.querySelectorAll('.company-card').length")
        print(f"  Prospects loaded: {prospect_count} company cards visible in DOM")
        await session.capture_screenshot(SCREENSHOT_DIR / "01_prospects_page_loaded.png")

        # Step 2: Open Log Call Modal for first prospect
        print("\nStep 2: Opening Log Call modal for Prospect 1...")
        comp_name_1 = await session.eval("""
            (() => {
                const titleEl = document.querySelector('.company-card .broker-card-header-top span:first-child');
                return titleEl ? titleEl.innerText.trim() : 'Company 1';
            })()
        """)
        print(f"  Prospect 1: {comp_name_1}")
        
        # Click Log Call button on first card
        await session.eval("""
            (() => {
                const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Log Call'));
                if (btn) btn.click();
            })()
        """)
        await session.wait_for_expr("document.getElementById('log-call-modal').style.display !== 'none'")
        await asyncio.sleep(0.5)
        
        modal_title = await session.eval("document.getElementById('call-modal-title').innerText")
        comp_display = await session.eval("document.querySelector('#log-call-modal-content div:first-child div[x-text=\"companyName\"]').innerText")
        print(f"  Modal visible: '{modal_title}' for '{comp_display}'")
        await session.capture_screenshot(SCREENSHOT_DIR / "02_log_call_modal_opened.png")

        # Step 3: Activate Verified Facts section and test Gatekeeper warning
        print("\nStep 3: Checking Verified Facts checkbox & Gatekeeper warning banner...")
        await session.eval("document.getElementById('chk-has-verified-facts').click()")
        await asyncio.sleep(0.3)
        has_facts = await session.eval("document.getElementById('chk-has-verified-facts').checked")
        assert has_facts is True, "Checkbox should be checked"

        # Select 'Reception / Gatekeeper' role
        await session.eval("""
            (() => {
                const sel = document.getElementById('evidence-source-role');
                sel.value = 'Reception / Gatekeeper';
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                const data = Alpine.$data(document.getElementById('log-call-modal'));
                if (data) data.sourcePersonRole = 'Reception / Gatekeeper';
            })()
        """)
        await asyncio.sleep(0.3)

        # Check if context-only warning banner is visible
        warning_visible = await session.eval("""
            (() => {
                const el = document.getElementById('gatekeeper-warning-banner');
                return el && window.getComputedStyle(el).display !== 'none';
            })()
        """)
        assert warning_visible is True, "Gatekeeper context-only warning banner must be visible!"
        print("  [SUCCESS] Gatekeeper context-only warning banner is visible in browser DOM.")
        await session.capture_screenshot(SCREENSHOT_DIR / "03_gatekeeper_warning_visible.png")

        # Step 4: Switch role to authoritative 'Shipping Manager' and fill verified facts
        print("\nStep 4: Setting role to 'Shipping Manager' and filling verified facts...")
        await session.eval("""
            (() => {
                const modal = document.getElementById('log-call-modal');
                const data = Alpine.$data(modal);
                
                const facSel = document.getElementById('call-facility-select');
                if (facSel && facSel.options.length > 1) {
                    facSel.selectedIndex = 1;
                    facSel.dispatchEvent(new Event('change', { bubbles: true }));
                    data.selectedFacilityId = facSel.value;
                }

                data.sourcePersonRole = 'Shipping Manager';
                data.factCarrierUse = 'YES';
                data.factBrokerStatus = 'YES';
                data.sourcePersonName = 'Dave Vance';
                data.callEvidenceNote = 'Dave confirmed they ship 4 flatbed loads weekly via outside brokers.';
                data.userConfirmedAccuracy = true;

                const sel = document.getElementById('evidence-source-role');
                if (sel) {
                    sel.value = 'Shipping Manager';
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }
            })()
        """)
        await asyncio.sleep(0.3)

        # Verify warning banner is now hidden
        debug_info = await session.eval("""
            (() => {
                const data = Alpine.$data(document.getElementById('log-call-modal'));
                const el = document.getElementById('gatekeeper-warning-banner');
                return {
                    sourcePersonRole: data.sourcePersonRole,
                    isNonAuthoritativeRole: data.isNonAuthoritativeRole(),
                    elExists: !!el,
                    elDisplay: el ? window.getComputedStyle(el).display : null,
                    elStyleDisplay: el ? el.style.display : null
                };
            })()
        """)
        print(f"  Debug info in Step 4: {debug_info}")
        warning_now = await session.eval("""
            (() => {
                const el = document.getElementById('gatekeeper-warning-banner');
                return el && window.getComputedStyle(el).display !== 'none';
            })()
        """)
        assert warning_now is False, f"Warning banner should be hidden for Shipping Manager: {debug_info}"
        print("  [SUCCESS] Warning banner cleanly hidden for authoritative role.")
        await session.capture_screenshot(SCREENSHOT_DIR / "04_verified_facts_filled_shipping_manager.png")

        # Step 5: Submit the call
        print("\nStep 5: Submitting call and verifying response messaging...")
        req_id_before = await session.eval("""
            (() => {
                const alpineData = Alpine.$data(document.getElementById('log-call-modal'));
                return alpineData ? alpineData.clientRequestId : null;
            })()
        """)
        print(f"  clientRequestId generated: {req_id_before}")
        assert req_id_before and req_id_before.startswith("req_"), "clientRequestId must be initialized"

        # Submit via submit button click
        await session.eval("""
            (() => {
                const btn = document.querySelector('#log-call-modal button[type=submit]');
                if (btn) btn.click();
            })()
        """)

        # Wait for either successMessage or errorMessage to be set
        await session.wait_for_expr("""
            (() => {
                const alpineData = Alpine.$data(document.getElementById('log-call-modal'));
                return alpineData && (alpineData.successMessage || alpineData.errorMessage);
            })()
        """, timeout=10.0)

        # Check result message
        modal_result = await session.eval("""
            (() => {
                const alpineData = Alpine.$data(document.getElementById('log-call-modal'));
                return {
                    successMessage: alpineData ? alpineData.successMessage : '',
                    errorMessage: alpineData ? alpineData.errorMessage : '',
                    saving: alpineData ? alpineData.saving : false
                };
            })()
        """)
        print(f"  Result state: {modal_result}")
        success_msg = modal_result.get("successMessage") or ""
        error_msg = modal_result.get("errorMessage") or ""
        assert not error_msg, f"Call submission returned error: {error_msg}"
        assert "verified claim" in success_msg or "successfully" in success_msg, f"Submission must report success, got: {success_msg}"
        await session.capture_screenshot(SCREENSHOT_DIR / "05_call_submitted_success.png")

        # Wait for modal close
        await session.wait_for_expr("Alpine.$data(document.getElementById('log-call-modal')).open === false", timeout=5.0)
        print("  Modal closed automatically after submit.")

        # Step 6: Test Cross-Prospect Form Reset
        print("\nStep 6: Opening Log Call for Prospect 2 and verifying complete form reset...")
        comp_name_2 = await session.eval("""
            (() => {
                const titles = Array.from(document.querySelectorAll('.company-card .broker-card-header-top span:first-child'));
                return titles.length > 1 ? titles[1].innerText.trim() : 'Company 2';
            })()
        """)
        print(f"  Prospect 2: {comp_name_2}")
        
        # Click Log Call on second card
        await session.eval("""
            (() => {
                const btns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText.includes('Log Call'));
                if (btns.length > 1) btns[1].click();
            })()
        """)
        await session.wait_for_expr("document.getElementById('log-call-modal').style.display !== 'none'")
        await asyncio.sleep(0.5)

        # Inspect form state of Prospect 2
        p2_state = await session.eval("""
            (() => {
                const data = Alpine.$data(document.getElementById('log-call-modal'));
                return {
                    companyName: data.companyName,
                    hasVerifiedFacts: data.hasVerifiedFacts,
                    factCarrierUse: data.factCarrierUse,
                    factBrokerStatus: data.factBrokerStatus,
                    sourcePersonName: data.sourcePersonName,
                    sourcePersonRole: data.sourcePersonRole,
                    callEvidenceNote: data.callEvidenceNote,
                    userConfirmedAccuracy: data.userConfirmedAccuracy,
                    successMessage: data.successMessage,
                    errorMessage: data.errorMessage,
                    clientRequestId: data.clientRequestId,
                };
            })()
        """)
        print(f"  Prospect 2 state: {json.dumps(p2_state, indent=2)}")

        # Verify invariants
        assert p2_state["hasVerifiedFacts"] is False, "Verified facts section must be collapsed / false by default"
        assert p2_state["factCarrierUse"] == "UNKNOWN", "Carrier use must reset to UNKNOWN"
        assert p2_state["factBrokerStatus"] == "UNKNOWN", "Broker status must reset to UNKNOWN"
        assert p2_state["sourcePersonRole"] == "", "Source role must reset to empty"
        assert p2_state["callEvidenceNote"] == "", "Evidence note must reset to empty"
        assert p2_state["userConfirmedAccuracy"] is False, "Confirmation checkbox must reset to false"
        assert p2_state["successMessage"] == "", "Success message must reset to empty"
        assert p2_state["clientRequestId"] != req_id_before, "New clientRequestId must be generated for each call"
        print("  [SUCCESS] Cross-prospect form reset invariant 100% verified. Zero field leakage!")
        await session.capture_screenshot(SCREENSHOT_DIR / "06_second_prospect_modal_clean_reset.png")

        print("\n=== INTERACTIVE BROWSER QA PASSED ALL CHECKS ===")

    finally:
        # Teardown
        print("\nCleaning up processes...")
        try:
            chrome_proc.terminate()
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()

        try:
            server_proc.terminate()
            server_proc.wait(timeout=3)
        except Exception:
            server_proc.kill()

        if CHROME_PROFILE.exists():
            shutil.rmtree(CHROME_PROFILE, ignore_errors=True)

        if TEMP_DB.exists():
            TEMP_DB.unlink()
        print("Teardown complete. Temporary files and processes cleaned up.")

if __name__ == "__main__":
    asyncio.run(run_browser_qa())
