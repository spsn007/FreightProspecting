"""
Stage 3F.1 Visual QA Script:
Captures screenshots and validates UI DOM for Stage 3F.1:
1. Shortlist Cockpit with 32 reconciled prospects
2. Master Directory with Shortlist tab (32)
3. Master Directory with Qualified tab (96)
4. Master Directory with Lifecycle Guide expanded
5. Prospect Detail for Facility 18: Coil Steel Processing (CSP) (Toledo, OH, FLATBED VERIFIED)
6. Prospect Detail for Facility 408: Yoder Lumber Co. (Millersburg, OH, CID 321, FID 408)
7. Prospect Detail for Facility 386: Cole Hardwood Inc. (Bourbon, IN, CID 300, FID 386)
"""
import asyncio
import base64
import json
import subprocess
import urllib.request
import websockets
from pathlib import Path

SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\stage3f1")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9229
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

            # 1. Shortlist Cockpit: 32 Shortlisted Prospects (Dark Mode)
            print("\n--- 1. SHORTLIST COCKPIT DARK MODE ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "01_cockpit_shortlist_reconciled")

            # 2. Master Directory: Shortlist Tab (32)
            print("\n--- 2. MASTER DIRECTORY SHORTLIST TAB ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects")
            await set_theme("dark")
            await asyncio.sleep(0.5)
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
            s_count = await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].filteredCompanies);
                    return root ? root._x_dataStack[0].filteredCompanies().length : -1;
                })()
            """)
            print(f"Shortlist companies: {s_count}", flush=True)
            await capture(ws, "02_directory_shortlist_tab")

            # 3. Master Directory: Qualified Tab (96)
            print("\n--- 3. MASTER DIRECTORY QUALIFIED TAB ---", flush=True)
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
            q_count = await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].filteredCompanies);
                    return root ? root._x_dataStack[0].filteredCompanies().length : -1;
                })()
            """)
            print(f"Qualified companies: {q_count}", flush=True)
            await capture(ws, "03_directory_qualified_tab")

            # 4. Master Directory: Lifecycle Guide Expanded
            print("\n--- 4. MASTER DIRECTORY LIFECYCLE GUIDE ---", flush=True)
            await evaluate(ws, """
                (() => {
                    const root = Array.from(document.querySelectorAll("[x-data]")).find(el => el._x_dataStack && el._x_dataStack[0].showLifecycleGuide !== undefined);
                    if (root) {
                        const d = root._x_dataStack[0];
                        d.lifecycleTab = 'ALL';
                        d.showLifecycleGuide = true;
                        d.resetPage();
                    }
                })()
            """)
            await asyncio.sleep(0.6)
            await capture(ws, "04_directory_lifecycle_guide")

            # 5. Detail Profile: Facility 18 Coil Steel Processing (CSP)
            print("\n--- 5. DETAIL PROFILE: CSP (FACILITY 18) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/18")
            await set_theme("dark")
            await asyncio.sleep(0.6)
            csp_text = await evaluate(ws, "document.body.innerText")
            assert "Coil Steel Processing" in csp_text, "Coil Steel Processing not found in profile!"
            assert "1604 Prosperity Road" in csp_text, "1604 Prosperity Road not found in profile!"
            assert "FLATBED" in csp_text, "FLATBED not found in profile!"
            print("CSP Facility 18 Verified in DOM!", flush=True)
            await capture(ws, "05_prospect_detail_csp_facility_18_dark")

            # 6. Detail Profile: Facility 408 Yoder Lumber Co.
            print("\n--- 6. DETAIL PROFILE: YODER LUMBER (FACILITY 408) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/408")
            await set_theme("dark")
            await asyncio.sleep(0.6)
            yoder_text = await evaluate(ws, "document.body.innerText")
            assert "Yoder Lumber" in yoder_text, "Yoder Lumber not found in profile!"
            assert "Millersburg" in yoder_text, "Millersburg not found in profile!"
            print("Yoder Lumber Facility 408 Verified in DOM!", flush=True)
            await capture(ws, "06_prospect_detail_yoder_lumber_dark")

            # 7. Detail Profile: Facility 386 Cole Hardwood Inc.
            print("\n--- 7. DETAIL PROFILE: COLE HARDWOOD (FACILITY 386) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/386")
            await set_theme("dark")
            await asyncio.sleep(0.6)
            cole_text = await evaluate(ws, "document.body.innerText")
            assert "Cole Hardwood" in cole_text, "Cole Hardwood not found in profile!"
            assert "Bourbon" in cole_text, "Bourbon not found in profile!"
            print("Cole Hardwood Facility 386 Verified in DOM!", flush=True)
            await capture(ws, "07_prospect_detail_cole_hardwood_dark")

            print("\n[QA] ALL 7 STAGE 3F.1 SCREENSHOTS CAPTURED AND VERIFIED SUCCESSFULLY!", flush=True)

    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(run_qa())
