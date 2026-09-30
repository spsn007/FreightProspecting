"""
Stage 3E Visual QA Script:
Captures screenshots and validates UI DOM for the 500+ Discovery Company Pool.
"""
import asyncio
import base64
import json
import subprocess
import urllib.request
import websockets
from pathlib import Path

SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\stage3e")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9226
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
            with open(p, "wb") as f:
                f.write(img_data)
            print(f"[QA] Captured: {p.name}", flush=True)
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

async def run_qa():
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
        page_target = next(t for t in targets if t.get("type") == "page" and "127.0.0.1:8000" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Connected to CDP:", ws_url, flush=True)

        async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "DOM.enable"}))

            async def set_theme(theme):
                await evaluate(ws, f"document.documentElement.setAttribute('data-theme', '{theme}'); localStorage.setItem('fp_theme', '{theme}');")
                await asyncio.sleep(0.3)

            # 1. Master Directory: Companies View (Light Mode)
            print("\n--- 1. MASTER DIRECTORY LIGHT MODE ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("light")
            await asyncio.sleep(0.5)

            # Check DOM metrics safely
            total_companies = await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].companies);
                    return root ? root._x_dataStack[0].companies.length : -1;
                })()
            """)
            print(f"Total companies loaded in Alpine.js: {total_companies}", flush=True)
            await capture(ws, "01_directory_companies_light")

            # 2. Master Directory: Companies View (Dark Mode)
            print("\n--- 2. MASTER DIRECTORY DARK MODE ---", flush=True)
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "02_directory_companies_dark")

            # 3. Expand Georgia-Pacific in Dark Mode
            print("\n--- 3. MASTER DIRECTORY: EXPAND GEORGIA-PACIFIC ---", flush=True)
            await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].companies);
                    if (root) {
                        const d = root._x_dataStack[0];
                        d.searchQuery = "Georgia-Pacific";
                        d.resetPage();
                        const gp = d.filteredCompanies().find(c => c.operating_brand.includes('Georgia-Pacific'));
                        if (gp) d.expandedCompanies[gp.company_id] = true;
                    }
                })()
            """)
            await asyncio.sleep(0.8)
            await capture(ws, "03_georgia_pacific_expanded_dark")

            # 4. Cockpit View
            print("\n--- 4. COCKPIT LIGHT & DARK ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/")
            await set_theme("light")
            await capture(ws, "04_cockpit_light")
            await set_theme("dark")
            await capture(ws, "05_cockpit_dark")

            # 5. CRM Overview (clean state)
            print("\n--- 5. CRM FOLLOW-UPS ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/crm/follow-ups")
            await set_theme("dark")
            await capture(ws, "06_crm_follow_ups_dark")

            print("\n=== ALL STAGE 3E QA SCREENSHOTS CAPTURED! ===", flush=True)
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    asyncio.run(run_qa())
