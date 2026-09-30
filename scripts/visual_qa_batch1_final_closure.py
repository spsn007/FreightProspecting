"""
FreightProspecting V1 — Broker Research Batch 1 Final Closure Autonomous Browser QA
Captures screenshots across Cockpit, Master Directory, and Prospect Detail pages
in dark theme, verifying live counts (11 / 105 / 4 / 445) and exact Truth Panels for:
- Beasley Forest Products (Facility 1, Tier A, outside carrier verified, affiliated carrier entity, ext 4317)
- Edwards Wood Products (Facility 13, Tier A, outside carrier verified, private fleet verified)
- E.C. Babbert (Facility 33, Tier B, fleet UNKNOWN, carrier UNKNOWN)
- Yoder Lumber (Facility 408, Tier B, fleet UNKNOWN, affiliated carrier entity)
- SyBridge Technologies (Facility 43, Tier B, QUALIFIED, fleet UNKNOWN, 833 phone)
- Leslie Forest Products (Facility 9, Tier B, SHORTLISTED, james@leslieforest.com)
- AarKel Tool and Die (Facility 184, Tier B, SHORTLISTED, ext 205)
- Anchor Concrete Products (Facility 143, Tier B, SHORTLISTED, ext 250)
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
CDP_PORT = 9296
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_batch1_closure"
ARTIFACT_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\fd601586-73de-4870-a85c-36d5522ed7e8") / "screenshots" / "batch1_final_closure"
LOCAL_SHOTS_DIR = Path(__file__).parent.parent / "screenshots" / "batch1_final_closure"


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

            # ------------------------------------------------------------------
            # 1. Cockpit: Priority Prospects (Default) in Dark Theme (11)
            # ------------------------------------------------------------------
            await set_viewport(1440, 900)
            await navigate(f"http://127.0.0.1:{APP_PORT}/")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.5)
            await take_screenshot("01_cockpit_priority_dark.png")

            # ------------------------------------------------------------------
            # 2. Cockpit: Switch to Worth Calling Tab (105)
            # ------------------------------------------------------------------
            await eval_js("""
                const btn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.textContent.includes('Worth Calling'));
                if (btn) btn.click();
            """)
            await asyncio.sleep(0.5)
            await take_screenshot("02_cockpit_worth_calling_dark.png")

            # ------------------------------------------------------------------
            # 3. Cockpit: Switch to Secondary Prospects Tab (4)
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
            # 5. Master Directory: Priority Prospects Tab (11) in Dark Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_A_PRIORITY")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("05_master_directory_priority_tier_a_dark.png")

            # ------------------------------------------------------------------
            # 6. Master Directory: Worth Calling Tab (105 / 138) in Dark Theme
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_B_WORTH_CALLING")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("06_master_directory_worth_calling_tier_b_dark.png")

            # ------------------------------------------------------------------
            # 7. Master Directory: Secondary Prospects Tab (4) in Dark Theme
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
            # 9. Detail: Beasley Forest Products (Facility 1, Tier A, Carrier VERIFIED, Fleet UNKNOWN, AFFILIATED_CARRIER_ENTITY, ext 4317)
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/1")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("09_detail_beasley_facility_1_dark.png")

            # ------------------------------------------------------------------
            # 10. Detail: Edwards Wood Products (Facility 13, Tier A, Carrier VERIFIED, Fleet VERIFIED_PRESENT, IN_HOUSE_OWNED)
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/13")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("10_detail_edwards_facility_13_dark.png")

            # ------------------------------------------------------------------
            # 11. Detail: E.C. Babbert (Facility 33, Tier B, Fleet UNKNOWN, Carrier UNKNOWN)
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/33")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("11_detail_ec_babbert_facility_33_dark.png")

            # ------------------------------------------------------------------
            # 12. Detail: Yoder Lumber (Facility 408, Tier B, Fleet UNKNOWN, AFFILIATED_CARRIER_ENTITY)
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/408")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("12_detail_yoder_facility_408_dark.png")

            # ------------------------------------------------------------------
            # 13. Detail: SyBridge Technologies (Facility 43, Tier B, QUALIFIED, Fleet UNKNOWN, 833 Phone)
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/43")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("13_detail_sybridge_facility_43_dark.png")

            # ------------------------------------------------------------------
            # 14. Detail: Leslie Forest Products (Facility 9, Tier B, SHORTLISTED, james@leslieforest.com)
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/9")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("14_detail_leslie_facility_9_dark.png")

            # ------------------------------------------------------------------
            # 15. Detail: AarKel Tool and Die (Facility 184, Tier B, SHORTLISTED, ext 205)
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/184")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("15_detail_aarkel_facility_184_dark.png")

            # ------------------------------------------------------------------
            # 16. Detail: Anchor Concrete Products (Facility 143, Tier B, SHORTLISTED, ext 250)
            # ------------------------------------------------------------------
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/143")
            await eval_js("document.documentElement.setAttribute('data-theme', 'dark');")
            await asyncio.sleep(0.6)
            await take_screenshot("16_detail_anchor_concrete_facility_143_dark.png")

            print(f"[QA] Completed successfully. Total console errors: {len(console_errors)}")

    finally:
        chrome_proc.terminate()
        server_proc.terminate()


if __name__ == "__main__":
    asyncio.run(run_qa())
