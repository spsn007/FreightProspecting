"""
FreightProspecting V1 — Batch 1 Closure Blockers Visual QA
Inspects and captures screenshots for:
1. Leslie Forest Products (Facility 9): James Sangara direct personal email vs Shipping Department shared mailbox
2. Edwards Wood Products (Facility 13): Truth Panel with re-grounded IN_HOUSE_OWNED
3. Lindsay Precast (Facility 27): Truth Panel with UNKNOWN fleet relationship
4. Tindall Corporation (Facility 28): Truth Panel with UNKNOWN fleet relationship
5. Bemis Manufacturing Company (Facility 41): Truth Panel with UNKNOWN fleet relationship + verified private fleet
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
CDP_PORT = 9297
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_blockers"
ARTIFACT_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\fd601586-73de-4870-a85c-36d5522ed7e8") / "screenshots" / "batch1_blockers"
LOCAL_SHOTS_DIR = Path(__file__).parent.parent / "screenshots" / "batch1_blockers"


async def run_qa():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_SHOTS_DIR.mkdir(parents=True, exist_ok=True)

    root_dir = Path(__file__).parent.parent
    venv_py = root_dir / ".venv" / "Scripts" / "python.exe"

    print("[QA] Preparing port 8000...", flush=True)
    subprocess.run([str(venv_py), "scripts/prepare_server_port.py"], cwd=str(root_dir))

    print(f"[QA] Launching server on port {APP_PORT}...", flush=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    server_proc = subprocess.Popen(
        [str(venv_py), "-m", "uvicorn", "src.backend.main:app", "--host", "127.0.0.1", "--port", str(APP_PORT)],
        cwd=str(root_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    for _ in range(30):
        time.sleep(0.4)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/", timeout=1) as resp:
                if resp.status == 200:
                    print(f"[QA] Server ready on http://127.0.0.1:{APP_PORT}/", flush=True)
                    break
        except Exception:
            pass

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
        print("[ERROR] Chrome CDP failed to connect.")
        chrome_proc.terminate()
        server_proc.terminate()
        sys.exit(1)

    console_errors = []

    try:
        async with websockets.connect(ws_url) as ws:
            req_id = 0

            async def send(method, params=None):
                nonlocal req_id
                req_id += 1
                payload = {"id": req_id, "method": method}
                if params:
                    payload["params"] = params
                await ws.send(json.dumps(payload))
                while True:
                    raw = await ws.recv()
                    res = json.loads(raw)
                    if "method" in res and res["method"] == "Runtime.consoleAPICalled":
                        if res["params"].get("type") == "error":
                            console_errors.append(res["params"])
                    if "method" in res and res["method"] == "Log.entryAdded":
                        if res["params"]["entry"].get("level") == "error":
                            console_errors.append(res["params"]["entry"])
                    if res.get("id") == req_id:
                        return res.get("result", {})

            await send("Page.enable")
            await send("Runtime.enable")
            await send("Log.enable")

            async def set_viewport(width, height):
                await send("Emulation.setDeviceMetricsOverride", {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": width <= 500,
                })

            async def eval_js(expression):
                res = await send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                return res.get("result", {}).get("value")

            async def take_screenshot(filename):
                shot = await send("Page.captureScreenshot", {"format": "png"})
                img_data = base64.b64decode(shot["data"])
                local_path = LOCAL_SHOTS_DIR / filename
                art_path = ARTIFACT_DIR / filename
                with open(local_path, "wb") as f:
                    f.write(img_data)
                with open(art_path, "wb") as f:
                    f.write(img_data)
                print(f"[QA] Captured: {filename} ({len(img_data)} bytes)", flush=True)

            async def navigate(url):
                for attempt in range(5):
                    await send("Page.navigate", {"url": url})
                    await asyncio.sleep(1.2)
                    page_text = await eval_js("document.body ? document.body.innerText : ''")
                    if page_text and "FreightProspecting" in page_text and "This site can" not in page_text:
                        return
                    await asyncio.sleep(0.8)
                print(f"[WARN] Navigation to {url} may not have loaded properly")

            await set_viewport(1440, 900)

            # 1. Leslie Forest Products (Facility 9, Tier B)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/9")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("01_detail_leslie_facility_9_dark.png")

            # 2. Edwards Wood Products (Facility 13, Tier A)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/13")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("02_detail_edwards_facility_13_dark.png")

            # 3. Lindsay Precast (Facility 27, Tier B)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/27")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("03_detail_lindsay_facility_27_dark.png")

            # 4. Tindall Corporation (Facility 28, Tier B)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/28")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("04_detail_tindall_facility_28_dark.png")

            # 5. Bemis Manufacturing Company (Facility 41, Tier A)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/41")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("05_detail_bemis_facility_41_dark.png")

            print(f"[QA] Completed successfully. Total console errors: {len(console_errors)}")

    finally:
        chrome_proc.terminate()
        server_proc.terminate()


if __name__ == "__main__":
    asyncio.run(run_qa())
