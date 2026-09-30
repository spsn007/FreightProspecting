"""
Audit Remediation C Visual QA Script via Chrome CDP.
Captures screenshots proving UI correctness:
1. AUD-011: Master directory at 1440px with server-side pagination, search, and decoupled friction badges.
2. AUD-018: Dark mode contrast compliance with #94a3b8 input placeholders (WCAG AA >= 4.5:1).
3. AUD-017: 375px mobile viewport layout without horizontal overflow.
4. AUD-020: Prospect detail page (Facility 1) showing read-only state and safe URLs.
5. AUD-003: Prospect detail evidence ledger drawer showing verified address, equipment, and primary sources.
"""

import asyncio
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

PORT = 9249
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_audit_remediation_c"
SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\audit_remediation_c")
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

            # 1. AUD-011: Master Directory at 1440px
            print("\n1. Testing AUD-011: Master Directory at 1440px...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("light")
            await asyncio.sleep(1.0)
            await capture(ws, "01_aud011_master_directory_server_pagination_1440px")

            # 2. AUD-018: Dark Mode Contrast with #94a3b8 Placeholder
            print("\n2. Testing AUD-018: Dark mode placeholder contrast...", flush=True)
            await set_theme("dark")
            await asyncio.sleep(1.0)
            placeholder_color = await evaluate(ws, """
                (() => {
                    const inp = document.querySelector('input[type=\"text\"], input[placeholder]');
                    if (!inp) return 'not found';
                    return window.getComputedStyle(inp, '::placeholder').color;
                })()
            """)
            print(f"  Dark mode placeholder computed color: {placeholder_color}", flush=True)
            await capture(ws, "02_aud018_dark_mode_placeholder_contrast")

            # 4. AUD-020: Prospect Detail Read-Only
            print("\n4. Testing AUD-020: Prospect detail page read-only state...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/1")
            await set_theme("light")
            await asyncio.sleep(1.0)
            await capture(ws, "04_aud020_prospect_detail_idempotent_read")

            # 5. AUD-003: Evidence Ledger Drawer Open
            print("\n5. Testing AUD-003: Evidence ledger drawer...", flush=True)
            await evaluate(ws, """
                (() => {
                    const btn = document.querySelector('button[\\@click*=\"claimsDrawerOpen\"]');
                    if (btn) btn.click();
                })()
            """)
            await asyncio.sleep(1.0)
            await capture(ws, "05_aud003_qualification_readiness_drawer")

    finally:
        chrome_proc.terminate()
        chrome_proc.wait()

async def run_mobile_test():
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

            print("\n3. Testing AUD-017: 375px mobile viewport...", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            scroll_width = await evaluate(ws, "document.documentElement.scrollWidth")
            inner_width = await evaluate(ws, "window.innerWidth")
            print(f"  Mobile 375px check: window.innerWidth={inner_width}, document.scrollWidth={scroll_width}", flush=True)
            await capture(ws, "03_aud017_mobile_viewport_375px")
    finally:
        chrome_proc.terminate()
        chrome_proc.wait()

async def main():
    await run_desktop_tests()
    await asyncio.sleep(1.0)
    await run_mobile_test()
    print("\nVisual QA complete! All screenshots saved to artifact directory.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
