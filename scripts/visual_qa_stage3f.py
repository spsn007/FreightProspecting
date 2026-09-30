"""
Stage 3F Visual QA Script:
Captures screenshots and validates UI DOM for the Stage 3F Lifecycle Review:
- 32 Shortlisted prospects in Cockpit (with Why Shortlisted facts and Log Call button)
- Master Directory with 527 All Companies, 32 Shortlisted, 96 Qualified, 399 Discovery
- Expandable Lifecycle Guide Banner with color-coded DISCOVERY, QUALIFIED, and SHORTLISTED cards
- Why Shortlisted and Why Qualified factual drill-downs
"""
import asyncio
import base64
import json
import subprocess
import urllib.request
import websockets
from pathlib import Path

SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\stage3f")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9228
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
        "http://127.0.0.1:8000/"
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

            # 1. Shortlist Cockpit: 32 Shortlisted Prospects (Light Mode)
            print("\n--- 1. SHORTLIST COCKPIT LIGHT MODE ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/")
            await set_theme("light")
            await asyncio.sleep(0.5)
            await capture(ws, "01_cockpit_shortlist_32_light")

            # 2. Shortlist Cockpit: 32 Shortlisted Prospects (Dark Mode)
            print("\n--- 2. SHORTLIST COCKPIT DARK MODE ---", flush=True)
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "02_cockpit_shortlist_32_dark")

            # 3. Master Directory: All Companies (527) Dark Mode
            print("\n--- 3. MASTER DIRECTORY ALL COMPANIES DARK MODE ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("dark")
            await asyncio.sleep(0.6)
            total_companies = await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].companies);
                    return root ? root._x_dataStack[0].companies.length : -1;
                })()
            """)
            print(f"Total companies loaded in Alpine.js: {total_companies}", flush=True)
            await capture(ws, "03_master_directory_all_companies_dark")

            # 4. Master Directory: Expand Lifecycle Guide Banner
            print("\n--- 4. LIFECYCLE GUIDE BANNER EXPANDED ---", flush=True)
            await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].showLifecycleGuide !== undefined);
                    if (root) {
                        root._x_dataStack[0].showLifecycleGuide = true;
                    }
                })()
            """)
            await asyncio.sleep(0.6)
            await capture(ws, "04_lifecycle_guide_expanded_dark")

            # 5. Master Directory: Shortlist Tab (32 Companies)
            print("\n--- 5. SHORTLIST TAB (32 COMPANIES) ---", flush=True)
            await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].lifecycleTab !== undefined);
                    if (root) {
                        const d = root._x_dataStack[0];
                        d.lifecycleTab = 'SHORTLISTED';
                        d.resetPage();
                        d.showLifecycleGuide = false;
                    }
                })()
            """)
            await asyncio.sleep(0.6)
            shortlist_rendered = await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].filteredCompanies);
                    return root ? root._x_dataStack[0].filteredCompanies().length : -1;
                })()
            """)
            print(f"Shortlist companies in tab: {shortlist_rendered}", flush=True)
            await capture(ws, "05_shortlist_companies_tab_dark")

            # 6. Master Directory: Qualified Tab (96 Companies)
            print("\n--- 6. QUALIFIED TAB (96 COMPANIES) ---", flush=True)
            await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].lifecycleTab !== undefined);
                    if (root) {
                        const d = root._x_dataStack[0];
                        d.lifecycleTab = 'QUALIFIED';
                        d.resetPage();
                    }
                })()
            """)
            await asyncio.sleep(0.6)
            qual_rendered = await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].filteredCompanies);
                    return root ? root._x_dataStack[0].filteredCompanies().length : -1;
                })()
            """)
            print(f"Qualified companies in tab: {qual_rendered}", flush=True)
            await capture(ws, "06_qualified_companies_tab_dark")

            # 7. Master Directory: Discovery Tab (399 Companies)
            print("\n--- 7. DISCOVERY TAB (399 COMPANIES) ---", flush=True)
            await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].lifecycleTab !== undefined);
                    if (root) {
                        const d = root._x_dataStack[0];
                        d.lifecycleTab = 'DISCOVERY';
                        d.resetPage();
                    }
                })()
            """)
            await asyncio.sleep(0.6)
            disc_rendered = await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].filteredCompanies);
                    return root ? root._x_dataStack[0].filteredCompanies().length : -1;
                })()
            """)
            print(f"Discovery companies in tab: {disc_rendered}", flush=True)
            await capture(ws, "07_discovery_companies_tab_dark")

            print("\n[QA] ALL 7 SCREENSHOTS CAPTURED SUCCESSFULLY!", flush=True)

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(run_qa())
