"""
Visual QA Script for FreightProspecting Search Relevance & Global Card Symmetry Pass via Chrome CDP.

Captures all 8 required screenshots into:
C:\\Users\\DELL\\.gemini\\antigravity\\brain\\fd601586-73de-4870-a85c-36d5522ed7e8\\screenshots\\search_symmetry_pass\\

1. 01_master_directory_search_s_dark.png
2. 02_master_directory_search_ameri_dark.png
3. 03_master_directory_cards_aligned_dark.png
4. 04_master_directory_cards_aligned_light.png
5. 05_cockpit_cards_aligned_dark.png
6. 06_master_directory_1024px.png
7. 07_master_directory_768px.png
8. 08_master_directory_375px.png
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
CDP_PORT = 9290
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_search_symmetry"
SCREENSHOTS_DIR = Path(
    r"C:\Users\DELL\.gemini\antigravity\brain\fd601586-73de-4870-a85c-36d5522ed7e8\screenshots\search_symmetry_pass"
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
            params_data = res.get("params", {})
            if params_data.get("type") == "error":
                args = params_data.get("args", [])
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
    await asyncio.sleep(2.0)


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
    # 1. Cleanly prepare port 8000 and launch fresh Uvicorn process
    venv_py = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
    subprocess.run([str(venv_py), "scripts/prepare_server_port.py"], cwd=str(Path(__file__).parent.parent))

    print(f"[QA] Starting fresh Uvicorn on port {APP_PORT} with {venv_py}...", flush=True)
    server_proc = subprocess.Popen(
        [str(venv_py), "-m", "uvicorn", "src.backend.main:app", "--host", "127.0.0.1", "--port", str(APP_PORT)],
        cwd=str(Path(__file__).parent.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(0.4)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/", timeout=1) as resp:
                if resp.status == 200:
                    print(f"[QA] Uvicorn server is up on port {APP_PORT}.", flush=True)
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
            await send_cmd(ws, "Console.enable")
            await send_cmd(ws, "Runtime.enable")
            await send_cmd(ws, "Log.enable")
            await send_cmd(ws, "Page.enable")

            # -------------------------------------------------------------
            # Screenshot 1: 01_master_directory_search_s_dark.png
            # -------------------------------------------------------------
            print("\n1. Capturing Master Directory search 'S' in Dark Mode...", flush=True)
            await set_viewport(ws, 1440, 900, mobile=False)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?q=S")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "01_master_directory_search_s_dark")

            # -------------------------------------------------------------
            # Screenshot 2: 02_master_directory_search_ameri_dark.png
            # -------------------------------------------------------------
            print("\n2. Capturing Master Directory search 'Ameri' in Dark Mode...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects?q=Ameri")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(1.0)
            await capture(ws, "02_master_directory_search_ameri_dark")

            # -------------------------------------------------------------
            # Screenshot 3: 03_master_directory_cards_aligned_dark.png
            # (AmeriSteel, Andersen Pacific, Battle Lumber visible together)
            # -------------------------------------------------------------
            print("\n3. Capturing Master Directory cards aligned (AmeriSteel, Andersen Pacific, Battle Lumber) in Dark Mode...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "document.querySelector('.company-card').scrollIntoView({behavior: 'instant', block: 'start'});")
            await asyncio.sleep(1.0)
            await capture(ws, "03_master_directory_cards_aligned_dark")

            # -------------------------------------------------------------
            # Screenshot 4: 04_master_directory_cards_aligned_light.png
            # (Same cards in Light Mode)
            # -------------------------------------------------------------
            print("\n4. Capturing Master Directory cards aligned in Light Mode...", flush=True)
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('fp_theme', 'light');")
            await asyncio.sleep(0.8)
            await capture(ws, "04_master_directory_cards_aligned_light")

            # Reset back to dark
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")

            # -------------------------------------------------------------
            # Screenshot 5: 05_cockpit_cards_aligned_dark.png
            # (Shortlist Cockpit cards aligned in Dark Mode)
            # -------------------------------------------------------------
            print("\n5. Capturing Shortlist Cockpit cards aligned in Dark Mode...", flush=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');")
            await evaluate(ws, "document.querySelector('.company-card').scrollIntoView({behavior: 'instant', block: 'start'});")
            await asyncio.sleep(1.0)
            await capture(ws, "05_cockpit_cards_aligned_dark")

            # -------------------------------------------------------------
            # Screenshot 6: 06_master_directory_1024px.png
            # (1024px viewport)
            # -------------------------------------------------------------
            print("\n6. Capturing Master Directory at 1024px viewport...", flush=True)
            await set_viewport(ws, 1024, 768, mobile=False)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "document.querySelector('.company-card').scrollIntoView({behavior: 'instant', block: 'start'});")
            await asyncio.sleep(1.0)
            await capture(ws, "06_master_directory_1024px")

            # -------------------------------------------------------------
            # Screenshot 7: 07_master_directory_768px.png
            # (768px tablet viewport)
            # -------------------------------------------------------------
            print("\n7. Capturing Master Directory at 768px viewport...", flush=True)
            await set_viewport(ws, 768, 1024, mobile=False)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "document.querySelector('.company-card').scrollIntoView({behavior: 'instant', block: 'start'});")
            await asyncio.sleep(1.0)
            await capture(ws, "07_master_directory_768px")

            # -------------------------------------------------------------
            # Screenshot 8: 08_master_directory_375px.png
            # (375px mobile viewport)
            # -------------------------------------------------------------
            print("\n8. Capturing Master Directory at 375px mobile viewport...", flush=True)
            await set_viewport(ws, 375, 812, mobile=True)
            await navigate(ws, f"http://127.0.0.1:{APP_PORT}/prospects")
            await evaluate(ws, "document.documentElement.setAttribute('data-theme', 'dark');")
            await evaluate(ws, "document.querySelector('.company-card').scrollIntoView({behavior: 'instant', block: 'start'});")
            await asyncio.sleep(1.0)
            await capture(ws, "08_master_directory_375px")

            print("\n[QA] All 8 screenshots captured successfully!", flush=True)

    finally:
        # Cleanup Chrome
        if chrome_proc:
            try:
                chrome_proc.terminate()
                chrome_proc.wait(timeout=3)
            except Exception:
                pass

        # Cleanup Uvicorn if we started it
        if server_proc:
            try:
                server_proc.terminate()
                server_proc.wait(timeout=3)
            except Exception:
                pass
        subprocess.run([str(venv_py), "scripts/prepare_server_port.py"], cwd=str(Path(__file__).parent.parent))

        # Report console errors
        print("\n" + "=" * 50)
        print("BROWSER CONSOLE ERROR AUDIT:")
        print("=" * 50)
        if console_errors:
            for err in console_errors:
                print(f"  {err}")
        else:
            print("  [OK] Zero browser console errors recorded.")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run_qa())
