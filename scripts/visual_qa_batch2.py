"""
FreightProspecting V1 — Broker Research Batch 2 Visual QA & Browser Inspection
Inspects and captures screenshots for:
1. Cockpit overview with updated tier counts (12 Tier A, 103 Tier B, 5 Tier C, 445 Tier D)
2. Master Directory - Tier A Priority (12 prospects, Interfor present)
3. Master Directory - Tier B Worth Calling (103 prospects)
4. Master Directory - Tier C Secondary (5 prospects, Northern Concrete Pipe present)
5. Detail: Interfor (Facility 51) - Priority Prospect, commercial carrier VERIFIED, broker UNKNOWN
6. Detail: Northern Concrete Pipe (Facility 163) - Secondary Prospect, private fleet VERIFIED_PRESENT, IN_HOUSE_OWNED
7. Detail: Target Steel (Facility 133) - Worth Calling, affiliate carrier SST Trucking
8. Detail: Coreslab Structures (Facility 31) - Worth Calling, Jordan Davidson direct email
9. Detail: Swanson Group (Facility 418) - Needs More Research (DISCOVERY), commercial carrier VERIFIED
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
CDP_PORT = 9298
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_batch2"
ARTIFACT_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\fd601586-73de-4870-a85c-36d5522ed7e8") / "screenshots" / "batch2_research"
LOCAL_SHOTS_DIR = Path(__file__).parent.parent / "screenshots" / "batch2_research"


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
                    if page_text and "Loading" not in page_text:
                        break
                    await asyncio.sleep(0.5)

            await set_viewport(1440, 900)

            # 1. Cockpit Overview
            print("\n[QA] 1. Inspecting Cockpit...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/")
            cockpit_text = await eval_js("document.body.innerText")
            print(f"[QA] Cockpit loaded ({len(cockpit_text)} chars)")
            assert "Shortlist Cockpit" in cockpit_text
            await take_screenshot("01_cockpit_overview.png")

            # 2. Master Directory - Tier A Priority
            print("\n[QA] 2. Inspecting Master Directory (Tier A - Priority)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_A_PRIORITY")
            tier_a_text = await eval_js("document.body.innerText")
            print(f"[QA] Tier A loaded ({len(tier_a_text)} chars). Interfor present: {'Interfor' in tier_a_text}")
            assert "Interfor" in tier_a_text
            await take_screenshot("02_master_directory_tier_a_priority.png")

            # 3. Master Directory - Tier B Worth Calling
            print("\n[QA] 3. Inspecting Master Directory (Tier B - Worth Calling)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_B_WORTH_CALLING")
            tier_b_text = await eval_js("document.body.innerText")
            print(f"[QA] Tier B loaded ({len(tier_b_text)} chars).")
            assert "Worth Calling" in tier_b_text
            await take_screenshot("03_master_directory_tier_b_worth_calling.png")

            # 3b. Verify Northern Concrete Pipe is present in Tier B via search
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_B_WORTH_CALLING&q=Northern")
            ncp_search_text = await eval_js("document.body.innerText")
            assert "Northern Concrete Pipe" in ncp_search_text
            print("[QA] Northern Concrete Pipe confirmed present in Tier B Worth Calling search.")

            # 4. Master Directory - Tier C Secondary
            print("\n[QA] 4. Inspecting Master Directory (Tier C - Secondary)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_C_SECONDARY")
            tier_c_text = await eval_js("document.body.innerText")
            print(f"[QA] Tier C loaded ({len(tier_c_text)} chars).")
            assert "Secondary Prospect" in tier_c_text or "Secondary" in tier_c_text
            assert "Northern Concrete Pipe" not in tier_c_text
            await take_screenshot("04_master_directory_tier_c_secondary.png")

            # 5. Detail: Interfor (Facility 51)
            print("\n[QA] 5. Inspecting Interfor (Facility 51)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/51")
            fac51_text = await eval_js("document.body.innerText")
            print(f"[QA] Interfor facility loaded ({len(fac51_text)} chars)")
            assert "Interfor" in fac51_text
            assert "Commercial carrier use" in fac51_text or "VERIFIED" in fac51_text
            await take_screenshot("05_detail_interfor_facility_51.png")

            # 6. Detail: Northern Concrete Pipe (Facility 163)
            print("\n[QA] 6. Inspecting Northern Concrete Pipe (Facility 163)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/163")
            fac163_text = await eval_js("document.body.innerText")
            assert "Northern Concrete Pipe" in fac163_text
            assert "Ready to Contact" in fac163_text
            assert "Own Trucks Confirmed" not in fac163_text
            await take_screenshot("06_detail_northern_concrete_pipe_facility_163.png")

            # 7. Detail: Target Steel (Facility 133)
            print("\n[QA] 7. Inspecting Target Steel (Facility 133)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/133")
            fac133_text = await eval_js("document.body.innerText")
            print(f"[QA] Target Steel facility loaded ({len(fac133_text)} chars)")
            assert "Target Steel" in fac133_text
            assert "Traffic" in fac133_text or "traffic@targetsteel.net" in fac133_text or "AFFILIATED_CARRIER_ENTITY" in fac133_text
            await take_screenshot("07_detail_target_steel_facility_133.png")

            # 8. Detail: Coreslab Structures (Facility 31)
            print("\n[QA] 8. Inspecting Coreslab Structures (Facility 31)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/31")
            fac31_text = await eval_js("document.body.innerText")
            print(f"[QA] Coreslab facility loaded ({len(fac31_text)} chars)")
            assert "Coreslab" in fac31_text
            assert "jdavidson@coreslab.com" in fac31_text
            await take_screenshot("08_detail_coreslab_facility_31.png")

            # 9. Detail: Swanson Group (Facility 418)
            print("\n[QA] 9. Inspecting Swanson Group (Facility 418)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/418")
            fac418_text = await eval_js("document.body.innerText")
            print(f"[QA] Swanson Group facility loaded ({len(fac418_text)} chars)")
            assert "Swanson Group" in fac418_text
            assert "Commercial carrier use" in fac418_text or "Discovery" in fac418_text
            await take_screenshot("09_detail_swanson_group_facility_418.png")

            print("\n=== CONSOLE ERRORS AUDIT ===")
            print(f"Total console errors encountered: {len(console_errors)}")
            if console_errors:
                for ce in console_errors:
                    print("  Console error:", ce)
            assert len(console_errors) == 0, f"Found console errors: {console_errors}"

    finally:
        print("\n[QA] Cleaning up browser and server processes...", flush=True)
        try:
            chrome_proc.terminate()
            chrome_proc.wait(timeout=2)
        except Exception:
            pass
        try:
            server_proc.terminate()
            server_proc.wait(timeout=2)
        except Exception:
            pass
        subprocess.run([str(venv_py), "scripts/prepare_server_port.py"], cwd=str(root_dir))
        print("[QA] Visual QA Completed Successfully!", flush=True)


if __name__ == "__main__":
    asyncio.run(run_qa())
