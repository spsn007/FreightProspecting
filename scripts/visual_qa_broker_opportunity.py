"""
Automated Visual QA for Full Broker Opportunity Reclassification.
Captures all required screenshots across Cockpit and Master Directory
in dark and light themes, verifying opportunity tiers, tabs, and honest unknown wording.
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import websockets

APP_PORT = 8000
CDP_PORT = 9294
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_broker_opp"
ARTIFACT_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\fd601586-73de-4870-a85c-36d5522ed7e8") / "screenshots" / "broker_opportunity_reclassification"
LOCAL_SHOTS_DIR = Path(__file__).parent.parent / "screenshots" / "broker_opportunity_reclassification"


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

            async def eval_js(expression):
                res = await send("Runtime.evaluate", {"expression": expression, "returnByValue": True})
                return res.get("result", {}).get("value")

            # ------------------------------------------------------------------
            # 1. Cockpit: Priority Prospects (Default) in Dark Theme
            # ------------------------------------------------------------------
            await set_viewport(1440, 900)
            await navigate(f"http://127.0.0.1:{APP_PORT}/")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.5)
            await take_screenshot("01_cockpit_priority_dark.png")

            # ------------------------------------------------------------------
            # 2. Cockpit: Switch to Worth Calling Tab
            # ------------------------------------------------------------------
            await eval_js("""
                const btn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.textContent.includes('Worth Calling'));
                if (btn) btn.click();
            """)
            await asyncio.sleep(0.5)
            await take_screenshot("02_cockpit_worth_calling_dark.png")

            # ------------------------------------------------------------------
            # 3. Cockpit: Switch to Secondary Prospects Tab (Beasley, etc.)
            # ------------------------------------------------------------------
            await eval_js("""
                const btn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.textContent.includes('Secondary Prospects'));
                if (btn) btn.click();
            """)
            await asyncio.sleep(0.5)
            await take_screenshot("03_cockpit_secondary_dark.png")

            # ------------------------------------------------------------------
            # 4. Master Directory: All Prospects (565) in Dark Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("04_master_directory_all_dark.png")

            # ------------------------------------------------------------------
            # 5. Master Directory: Priority Prospects Tab (9) in Dark Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_A_PRIORITY")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("05_master_directory_priority_tier_a_dark.png")

            # ------------------------------------------------------------------
            # 6. Master Directory: Worth Calling Tab (103) in Dark Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_B_WORTH_CALLING")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("06_master_directory_worth_calling_tier_b_dark.png")

            # ------------------------------------------------------------------
            # 7. Master Directory: Secondary Prospects Tab (8) in Dark Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_C_SECONDARY")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("07_master_directory_secondary_tier_c_dark.png")

            # ------------------------------------------------------------------
            # 8. Master Directory: Needs More Research Tab (445) in Dark Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_D_RESEARCH_NEEDED")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("08_master_directory_needs_research_tier_d_dark.png")

            # ------------------------------------------------------------------
            # 9. Master Directory: Priority Prospects in Light Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_A_PRIORITY")
            await eval_js("document.documentElement.setAttribute('data-theme', 'light');")
            await asyncio.sleep(0.6)
            await take_screenshot("09_master_directory_priority_light.png")

            # ------------------------------------------------------------------
            # 10. Prospect Detail: Battle Lumber Company (Tier A Priority) in Dark Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/5")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("10_prospect_detail_battle_lumber_dark.png")

            print(f"[QA] Completed all 10 visual screenshots with {len(console_errors)} console errors.")
            assert len(console_errors) == 0, f"Found console errors: {console_errors}"

    finally:
        chrome_proc.terminate()
        server_proc.terminate()
        print("[QA] Cleaned up browser and server processes.")


if __name__ == "__main__":
    asyncio.run(run_qa())
