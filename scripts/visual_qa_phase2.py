"""
Visual QA Script for FreightProspecting Broker-First UX Phase 2:
Cockpit + Prospect Detail + Complete Theme Consistency via Chrome CDP.

Captures all 11 required screenshots into:
C:\\Users\\DELL\\.gemini\\antigravity\\brain\\fd601586-73de-4870-a85c-36d5522ed7e8\\screenshots\\broker_first_ux_phase2\\

1.  01_master_directory_dark.png
2.  02_cockpit_dark.png
3.  03_cockpit_light.png
4.  04_priority_prospect_card_closeup.png
5.  05_ameristeel_detail_top_dark.png
6.  06_ameristeel_at_a_glance_why_dark.png
7.  07_ameristeel_readiness_dark.png
8.  08_ameristeel_research_collapsed_dark.png
9.  09_ameristeel_detail_light.png
10. 10_detail_mobile_375px.png
11. 11_cockpit_mobile_375px.png
"""

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import websockets

APP_PORT = 8000
CDP_PORT = 9288
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_broker_first_phase2"
SCREENSHOTS_DIR = Path(
    r"C:\Users\DELL\.gemini\antigravity\brain\fd601586-73de-4870-a85c-36d5522ed7e8\screenshots\broker_first_ux_phase2"
)
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

_msg_counter = 1000
console_errors = []


async def send_cmd(ws, method, params=None):
    global _msg_counter
    _msg_counter += 1
    req_id = _msg_counter
    payload = {"id": req_id, "method": method}
    if params:
        payload["params"] = params
    await ws.send(json.dumps(payload))
    while True:
        raw = await ws.recv()
        res = json.loads(raw)
        if res.get("method") == "Console.messageAdded":
            msg = res.get("params", {}).get("message", {})
            if msg.get("level") == "error":
                console_errors.append(f"[Console Error] {msg.get('text')}")
        elif res.get("method") == "Runtime.consoleAPICalled":
            params = res.get("params", {})
            if params.get("type") == "error":
                args = params.get("args", [])
                text = " ".join([str(a.get("value", a)) for a in args])
                console_errors.append(f"[Runtime Console Error] {text}")
        elif res.get("method") == "Log.entryAdded":
            entry = res.get("params", {}).get("entry", {})
            if entry.get("level") == "error":
                console_errors.append(f"[Log Error] {entry.get('text')}")

        if res.get("id") == req_id:
            return res.get("result", {})


async def evaluate(ws, expr):
    res = await send_cmd(ws, "Runtime.evaluate", {"expression": expr, "returnByValue": True})
    return res.get("result", {}).get("value")


async def navigate(ws, url):
    await send_cmd(ws, "Page.navigate", {"url": url})
    await asyncio.sleep(1.8)


async def set_viewport(ws, width, height, mobile=False):
    await send_cmd(ws, "Emulation.setDeviceMetricsOverride", {
        "width": width,
        "height": height,
        "deviceScaleFactor": 1,
        "mobile": mobile,
    })
    await asyncio.sleep(0.5)


async def capture(ws, name):
    res = await send_cmd(ws, "Page.captureScreenshot", {"format": "png"})
    if "data" in res:
        img_data = base64.b64decode(res["data"])
        p = SCREENSHOTS_DIR / f"{name}.png"
        p.write_bytes(img_data)
        print(f"[QA] Captured: {p.name} ({len(img_data):,} bytes)", flush=True)
    else:
        print(f"[QA] Failed to capture {name}: {res}", flush=True)


async def run_qa():
    # 1. Ensure server is running on port 8000
    server_proc = None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/", timeout=1.5) as resp:
            if resp.status == 200:
                print(f"[QA] Server already running on port {APP_PORT}.", flush=True)
    except Exception:
        print(f"[QA] Starting Uvicorn on port {APP_PORT}...", flush=True)
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.backend.main:app", "--host", "127.0.0.1", "--port", str(APP_PORT)],
            cwd=str(Path(__file__).parent.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait for server to come up
        for _ in range(25):
            time.sleep(0.4)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/", timeout=1) as resp:
                    if resp.status == 200:
                        print(f"[QA] Uvicorn server is up and responsive on port {APP_PORT}.", flush=True)
                        break
            except Exception:
                pass

    # 2. Launch headless Chrome with CDP
    chrome_cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={USER_DATA_DIR}",
        "about:blank",
    ]
    print(f"[QA] Launching headless Chrome on port {CDP_PORT}...", flush=True)
    chrome_proc = subprocess.Popen(chrome_cmd)

    ws_url = None
    for _ in range(30):
        time.sleep(0.3)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=1) as resp:
                data = json.loads(resp.read().decode())
                for target in data:
                    if target.get("type") == "page" and "webSocketDebuggerUrl" in target:
                        ws_url = target["webSocketDebuggerUrl"]
                        break
            if ws_url:
                break
        except Exception:
            pass

    if not ws_url:
        print("[QA] Failed to acquire Chrome CDP websocket URL!", flush=True)
        if chrome_proc:
            chrome_proc.terminate()
        if server_proc:
            server_proc.terminate()
        return

    print(f"[QA] Connected to Chrome CDP: {ws_url}", flush=True)

    try:
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            # Enable subsystems
            await send_cmd(ws, "Console.enable")
            await send_cmd(ws, "Runtime.enable")
            await send_cmd(ws, "Log.enable")
            await send_cmd(ws, "Page.enable")

            # -------------------------------------------------------------
            # Screenshot 1: 01_master_directory_dark.png
            # -------------------------------------------------------------
            print("\n1. Capturing Master Directory in Dark Mode...", flush=True)
            await set_viewport(ws, 1440, 900, mobile=False)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.8)
            await capture(ws, "01_master_directory_dark")

            # -------------------------------------------------------------
            # Screenshot 2: 02_cockpit_dark.png
            # -------------------------------------------------------------
            print("\n2. Capturing Shortlist Cockpit in Dark Mode...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.8)
            await capture(ws, "02_cockpit_dark")

            # -------------------------------------------------------------
            # Screenshot 3: 03_cockpit_light.png
            # -------------------------------------------------------------
            print("\n3. Capturing Shortlist Cockpit in Light Mode...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('fp_theme', 'light');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.8)
            await capture(ws, "03_cockpit_light")

            # Reset back to dark
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")

            # -------------------------------------------------------------
            # Screenshot 4: 04_priority_prospect_card_closeup.png
            # -------------------------------------------------------------
            print("\n4. Capturing Priority Prospect Card Close-up...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            # Scroll down slightly to frame the first priority prospect card perfectly
            await evaluate(ws, "window.scrollTo(0, 180);")
            await asyncio.sleep(0.8)
            await capture(ws, "04_priority_prospect_card_closeup")

            # -------------------------------------------------------------
            # Screenshot 5: 05_ameristeel_detail_top_dark.png (AmeriSteel facility 23)
            # -------------------------------------------------------------
            print("\n5. Capturing AmeriSteel Detail Top in Dark Mode...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects/23")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.8)
            await capture(ws, "05_ameristeel_detail_top_dark")

            # -------------------------------------------------------------
            # Screenshot 6: 06_ameristeel_at_a_glance_why_dark.png
            # -------------------------------------------------------------
            print("\n6. Capturing AmeriSteel At-a-Glance Operational Grid & Why Insights in Dark Mode...", flush=True)
            await evaluate(ws, "document.querySelector('.broker-insights-grid').scrollIntoView({behavior: 'instant', block: 'start'});")
            await asyncio.sleep(0.8)
            await capture(ws, "06_ameristeel_at_a_glance_why_dark")

            # -------------------------------------------------------------
            # Screenshot 7: 07_ameristeel_readiness_dark.png
            # -------------------------------------------------------------
            print("\n7. Capturing AmeriSteel Qualification Readiness in Dark Mode...", flush=True)
            await evaluate(ws, "document.querySelector('.readiness-simple-container').scrollIntoView({behavior: 'instant', block: 'start'});")
            await asyncio.sleep(0.8)
            await capture(ws, "07_ameristeel_readiness_dark")

            # -------------------------------------------------------------
            # Screenshot 8: 08_ameristeel_research_collapsed_dark.png
            # -------------------------------------------------------------
            print("\n8. Capturing AmeriSteel Research Collapsed Accordion in Dark Mode...", flush=True)
            await evaluate(ws, "document.querySelector('.tech-research-card').scrollIntoView({behavior: 'instant', block: 'center'});")
            await asyncio.sleep(0.8)
            await capture(ws, "08_ameristeel_research_collapsed_dark")

            # -------------------------------------------------------------
            # Screenshot 9: 09_ameristeel_detail_light.png
            # -------------------------------------------------------------
            print("\n9. Capturing AmeriSteel Detail Top in Light Mode...", flush=True)
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('fp_theme', 'light');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.8)
            await capture(ws, "09_ameristeel_detail_light")

            # Reset back to dark
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")

            # -------------------------------------------------------------
            # Screenshot 10: 10_detail_mobile_375px.png
            # -------------------------------------------------------------
            print("\n10. Capturing AmeriSteel Detail on 375px Mobile Viewport...", flush=True)
            await set_viewport(ws, 375, 812, mobile=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects/23")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.8)
            await capture(ws, "10_detail_mobile_375px")

            # -------------------------------------------------------------
            # Screenshot 11: 11_cockpit_mobile_375px.png
            # -------------------------------------------------------------
            print("\n11. Capturing Cockpit on 375px Mobile Viewport...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.8)
            await capture(ws, "11_cockpit_mobile_375px")

    finally:
        print("\n[QA] Closing Chrome...", flush=True)
        if chrome_proc:
            try:
                chrome_proc.terminate()
                chrome_proc.wait(timeout=3)
            except Exception:
                try:
                    chrome_proc.kill()
                except Exception:
                    pass

        if server_proc:
            print("[QA] Stopping Uvicorn test process...", flush=True)
            try:
                server_proc.terminate()
                server_proc.wait(timeout=3)
            except Exception:
                try:
                    server_proc.kill()
                except Exception:
                    pass

    print(f"\n[QA] Completed! Screenshots written to: {SCREENSHOTS_DIR}")
    if console_errors:
        print(f"[QA] WARNING: Encountered {len(console_errors)} console errors during test:")
        for err in console_errors:
            print(f"  - {err}")
    else:
        print("[QA] Console check: 0 errors detected. Clean execution!")


if __name__ == "__main__":
    asyncio.run(run_qa())
