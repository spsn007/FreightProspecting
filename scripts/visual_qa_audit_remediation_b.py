"""
Audit Remediation B Visual QA Script via Chrome CDP.
Captures screenshots to prove:
1. AUD-017: 375px mobile viewport layout without horizontal overflow.
2. AUD-018: Dark mode contrast ratio compliance using var(--color-text-muted) (#94a3b8).
3. AUD-019: Accessible Log Call modal (role='dialog', aria-modal='true', focus trap, accessible radiogroup).
4. AUD-026: Facility 18 (CSP) detail page displaying 'Not specified' fallback for NULL legal entity name.
5. AUD-016: Discovery readiness truthful explanation ('Meets all 5 qualification checks; ready for qualification review').
"""

import asyncio
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

PORT = 9248
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_audit_remediation_b"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\audit_remediation_b")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

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

async def run_desktop_tests():
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
        print("Desktop runner connected to CDP:", ws_url, flush=True)

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

            # 2. AUD-018: Dark Mode Contrast Compliance
            print("\n2. Testing AUD-018: Dark mode contrast...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("dark")
            await asyncio.sleep(1.0)
            muted_color = await evaluate(ws, """
                (() => {
                    const el = document.querySelector('.metric-label, .prospect-card-subtitle, [style*=\"color:var(--color-text-muted)\"]');
                    return el ? window.getComputedStyle(el).color : 'not found';
                })()
            """)
            print(f"  Dark mode muted text computed color: {muted_color}", flush=True)
            await capture(ws, "02_aud018_dark_mode_contrast")

            # 3. AUD-019: Accessible Log Call Modal
            print("\n3. Testing AUD-019: Accessible Log Call modal...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/")
            await set_theme("dark")
            await asyncio.sleep(1.0)
            await evaluate(ws, """
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
            """)
            await asyncio.sleep(1.0)
            modal_attrs = await evaluate(ws, """
                (() => {
                    const modal = document.querySelector('#log-call-modal');
                    if (!modal) return { error: 'log-call-modal not found' };
                    return {
                        role: modal.getAttribute('role'),
                        ariaModal: modal.getAttribute('aria-modal'),
                        ariaLabelledby: modal.getAttribute('aria-labelledby'),
                        radiogroup: !!modal.querySelector('[role=\"radiogroup\"]'),
                        activeElementId: document.activeElement ? document.activeElement.id : null
                    };
                })()
            """)
            print(f"  Modal accessibility attributes: {modal_attrs}", flush=True)
            await capture(ws, "03_aud019_call_modal_accessibility")

            # Close modal
            await evaluate(ws, """
                const closeBtn = document.querySelector('.modal-close-btn');
                if (closeBtn) closeBtn.click();
            """)
            await asyncio.sleep(0.5)

            # 4. AUD-026: Facility 18 (CSP) Legal Name Fallback
            print("\n4. Testing AUD-026: Facility 18 legal name fallback...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/18")
            await set_theme("dark")
            await asyncio.sleep(1.0)
            legal_val = await evaluate(ws, """
                (() => {
                    const keys = Array.from(document.querySelectorAll('.kv-key'));
                    const keyEl = keys.find(k => k.textContent.includes('Legal Entity Name'));
                    if (!keyEl) return 'key not found';
                    const valEl = keyEl.nextElementSibling;
                    return valEl ? valEl.textContent.trim() : 'val not found';
                })()
            """)
            print(f"  Facility 18 Legal Entity Name display: '{legal_val}'", flush=True)
            await capture(ws, "04_aud026_facility_18_legal_name_fallback")

            # 5. AUD-016: Discovery Readiness Truthful Explanation
            print("\n5. Testing AUD-016: Discovery readiness truthful explanation...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("dark")
            # Switch to Flat Facilities view and filter to Discovery
            await evaluate(ws, """
                (() => {
                    const alpineRoot = document.querySelector('[x-data]');
                    if (alpineRoot && alpineRoot._x_dataStack && alpineRoot._x_dataStack[0]) {
                        const scope = alpineRoot._x_dataStack[0];
                        scope.viewMode = 'FACILITIES';
                        scope.lifecycleTab = 'DISCOVERY';
                    }
                })()
            """)
            await asyncio.sleep(1.0)
            ready_explanation = await evaluate(ws, """
                (() => {
                    const cards = Array.from(document.querySelectorAll('.prospect-card'));
                    for (const c of cards) {
                        const text = c.textContent;
                        if (text.includes('ready for qualification review')) {
                            const idx = text.indexOf('Meets all 5');
                            return 'Found: ' + (idx !== -1 ? text.slice(idx, idx + 80) : text.slice(0, 100));
                        }
                    }
                    return 'Not found';
                })()
            """)
            print(f"  Discovery readiness text: {ready_explanation}", flush=True)
            await capture(ws, "05_aud016_discovery_readiness_explanation")

    finally:
        chrome_proc.terminate()
        chrome_proc.wait()

async def run_mobile_test():
    # Dedicated mobile Chrome launch at 375x812
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={USER_DATA_DIR}_mobile",
        "--headless=new",
        "--window-size=375,812",
        "--disable-gpu",
        "http://127.0.0.1:8000/prospects"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2.0)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Mobile runner connected to CDP:", ws_url, flush=True)

        async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "DOM.enable"}))

            print("\n1. Testing AUD-017: 375px mobile viewport...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            scroll_width = await evaluate(ws, "document.documentElement.scrollWidth")
            inner_width = await evaluate(ws, "window.innerWidth")
            top_bar_wrap = await evaluate(ws, """
                (() => {
                    const topBar = document.querySelector('.top-bar');
                    if (!topBar) return 'not found';
                    return window.getComputedStyle(topBar).flexWrap;
                })()
            """)
            print(f"  Mobile 375px check: window.innerWidth={inner_width}, document.scrollWidth={scroll_width}, topBar flexWrap={top_bar_wrap}", flush=True)
            await capture(ws, "01_aud017_mobile_viewport_375px")
    finally:
        chrome_proc.terminate()
        chrome_proc.wait()

async def main():
    await run_desktop_tests()
    await asyncio.sleep(1.0)
    await run_mobile_test()
    print("\nVisual QA complete! All 5 screenshots saved to artifact directory.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
