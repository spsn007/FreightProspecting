"""
Stage 3F.2 Visual QA Script:
Captures screenshots and validates UI DOM for Stage 3F.2:
1. Cockpit with 31 shortlisted prospects (Dark Mode)
2. Master Directory Shortlist tab (31 companies, Dark Mode)
3. Master Directory Qualified tab (97 companies, Dark Mode)
4. Prospect Detail Facility 408: Yoder Lumber Co. (Berlin OH, toll-free switchboard, non-callable fax note, multi-site 3 loc, MEDIUM friction)
5. Prospect Detail Facility 386: Cole Hardwood Inc. (Logansport IN, phone (574) 753-3151, single-site 1 loc, MEDIUM friction)
6. Prospect Detail Facility 24: Majestic Steel USA (Qualified, multi-site 9 loc, HIGH friction)
7. Prospect Detail Facility 25: Heidtman Steel Products (Qualified, multi-site 5 loc, HIGH friction)
8. Prospect Detail Facility 29: High Concrete Group LLC (Shortlisted, multi-site 2 loc, MEDIUM friction)
9. Prospect Detail Facility 41: Bemis Manufacturing Company (Qualified, multi-site 6 loc, HIGH friction)
10. Prospect Detail Facility 18: Coil Steel Processing (CSP) (Shortlisted, FLATBED VERIFIED, single-site 1 loc, LOW friction)
11. Cockpit with 31 shortlisted prospects (Light Mode)
"""
import asyncio
import base64
import json
import subprocess
import urllib.request
import websockets
from pathlib import Path

SCREENSHOTS_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\2ae177ef-23f7-439b-9542-6a638413f8c3\screenshots\stage3f2")
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

            # 1. Shortlist Cockpit: 31 Shortlisted Prospects (Dark Mode)
            print("\n--- 1. SHORTLIST COCKPIT DARK MODE ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "01_cockpit_shortlist_31_dark")

            # 2. Master Directory: Shortlist Tab (31)
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
            await capture(ws, "02_directory_shortlist_tab_dark")

            # 3. Master Directory: Qualified Tab (97)
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
            await capture(ws, "03_directory_qualified_tab_dark")

            # 4. Detail: Yoder Lumber Co. (FID 408)
            print("\n--- 4. PROSPECT DETAIL YODER LUMBER (FID 408) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/408")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            yoder_dial = await evaluate(ws, """
                (() => {
                    const dialBtn = document.querySelector("a[href^='tel:']");
                    return dialBtn ? dialBtn.getAttribute("href") : "NO_DIAL_BTN";
                })()
            """)
            print(f"Yoder top dial button: {yoder_dial} (Must NOT dial fax!)", flush=True)
            await capture(ws, "04_prospect_detail_yoder_lumber_dark")

            # 5. Detail: Cole Hardwood Inc. (FID 386)
            print("\n--- 5. PROSPECT DETAIL COLE HARDWOOD (FID 386) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/386")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            cole_city = await evaluate(ws, """
                (() => {
                    const addr = document.body.innerText;
                    return addr.includes("Logansport") && addr.includes("46947");
                })()
            """)
            print(f"Cole Hardwood Logansport address found: {cole_city}", flush=True)
            await capture(ws, "05_prospect_detail_cole_hardwood_dark")

            # 6. Detail: Majestic Steel USA (FID 24)
            print("\n--- 6. PROSPECT DETAIL MAJESTIC STEEL (FID 24) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/24")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "06_prospect_detail_majestic_steel_dark")

            # 7. Detail: Heidtman Steel Products (FID 25)
            print("\n--- 7. PROSPECT DETAIL HEIDTMAN STEEL (FID 25) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/25")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "07_prospect_detail_heidtman_steel_dark")

            # 8. Detail: High Concrete Group (FID 29)
            print("\n--- 8. PROSPECT DETAIL HIGH CONCRETE (FID 29) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/29")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "08_prospect_detail_high_concrete_dark")

            # 9. Detail: Bemis Manufacturing Company (FID 41)
            print("\n--- 9. PROSPECT DETAIL BEMIS MFG (FID 41) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/41")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "09_prospect_detail_bemis_mfg_dark")

            # 10. Detail: Coil Steel Processing (FID 18)
            print("\n--- 10. PROSPECT DETAIL CSP (FID 18) ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/prospects/18")
            await set_theme("dark")
            await asyncio.sleep(0.5)
            await capture(ws, "10_prospect_detail_csp_facility_18_dark")

            # 11. Cockpit Light Mode
            print("\n--- 11. SHORTLIST COCKPIT LIGHT MODE ---", flush=True)
            await navigate(ws, "http://127.0.0.1:8000/")
            await set_theme("light")
            await asyncio.sleep(0.5)
            await capture(ws, "11_cockpit_shortlist_31_light")

        print("\nAll Stage 3F.2 Visual QA screenshots captured successfully!", flush=True)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

if __name__ == "__main__":
    asyncio.run(run_qa())
