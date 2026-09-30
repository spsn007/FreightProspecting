"""
FreightProspecting V1 — Broker Research Batch 3 Final Closure Visual QA
Inspects and captures screenshots for:
1. Cockpit overview with updated tier counts (13 Tier A, 102 Tier B, 5 Tier C, 445 Tier D, 0 Restricted)
2. Master Directory - Tier A Priority (13 prospects: Imperial Metal, Interfor, etc., Tolko/O'Neal absent)
3. Master Directory - Tier B Worth Calling (102 prospects: Tolko Industries, O'Neal Steel, Steel Dynamics present)
4. Master Directory - Tier C Secondary (5 prospects: Precision Strip present)
5. Master Directory - Restricted (0 prospects: empty state)
6. Detail: Imperial Metal Services (Facility 22) - Priority Prospect
7. Detail: Tolko Industries (Facility 81) - Worth Calling Prospect (unknown carrier/fleet)
8. Detail: O'Neal Steel (Facility 262) - Worth Calling Prospect (unknown carrier/fleet)
9. Detail: Precision Strip (Facility 134) - Secondary Prospect (own fleet verified)
10. Detail: Steel Dynamics (Facility 266) - Restricted Butler facility / Company Tier B
11. Detail: Peerless Steel (Facility 464) - Troy facility
12. Detail: Rex Lumber (Facility 65) - Chris Brown Operations role
13. Detail: Two Rivers Lumber (Facility 70) - Jody King Demopolis GM, Switchboard
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
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_batch3_final"
ARTIFACT_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\c9751f49-c47d-4415-8cf2-6db615013dfa") / "screenshots" / "batch3_research"
LOCAL_SHOTS_DIR = Path(__file__).parent.parent / "screenshots" / "batch3_research"


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
            print(f"[QA] Tier A loaded ({len(tier_a_text)} chars). Imperial present: {'Imperial Metal' in tier_a_text}")
            assert "Imperial Metal Services" in tier_a_text
            assert "Tolko Industries" not in tier_a_text
            assert "O'Neal Steel" not in tier_a_text
            await take_screenshot("02_master_directory_tier_a_priority.png")

            # 3. Master Directory - Tier B Worth Calling
            print("\n[QA] 3. Inspecting Master Directory (Tier B - Worth Calling)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_B_WORTH_CALLING")
            tier_b_text = await eval_js("document.body.innerText")
            print(f"[QA] Tier B loaded ({len(tier_b_text)} chars).")
            assert "Worth Calling" in tier_b_text
            assert "102" in tier_b_text or "102 prospects" in tier_b_text.lower() or "102 companies" in tier_b_text.lower()
            await take_screenshot("03_master_directory_tier_b_worth_calling.png")

            # Searches across tiers as mandated by prompt:
            print("\n[QA] Searching: Tolko...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?q=Tolko")
            tolko_search_text = await eval_js("document.body.innerText")
            assert "Tolko Industries" in tolko_search_text
            assert "Worth Calling" in tolko_search_text

            print("\n[QA] Searching: O'Neal Steel...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?q=O%27Neal")
            oneal_search_text = await eval_js("document.body.innerText")
            assert "O'Neal Steel" in oneal_search_text
            assert "Worth Calling" in oneal_search_text

            print("\n[QA] Searching: Steel Dynamics...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?q=Steel+Dynamics")
            sdi_search_text = await eval_js("document.body.innerText")
            assert "Steel Dynamics" in sdi_search_text
            assert "Worth Calling" in sdi_search_text

            print("\n[QA] Searching: Interfor...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?q=Interfor")
            interfor_search_text = await eval_js("document.body.innerText")
            assert "Interfor" in interfor_search_text
            assert "Priority Prospect" in interfor_search_text

            print("\n[QA] Searching: Precision Strip...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?q=Precision+Strip")
            ps_search_text = await eval_js("document.body.innerText")
            assert "Precision Strip" in ps_search_text
            assert "Secondary" in ps_search_text

            # 4. Master Directory - Tier C Secondary
            print("\n[QA] 4. Inspecting Master Directory (Tier C - Secondary)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=TIER_C_SECONDARY")
            tier_c_text = await eval_js("document.body.innerText")
            print(f"[QA] Tier C loaded ({len(tier_c_text)} chars). Precision Strip present: {'Precision Strip' in tier_c_text}")
            assert "Precision Strip" in tier_c_text
            await take_screenshot("04_master_directory_tier_c_secondary.png")

            # 5. Master Directory - Restricted
            print("\n[QA] 5. Inspecting Master Directory (Restricted)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects?tier=RESTRICTED")
            restr_text = await eval_js("document.body.innerText")
            print(f"[QA] Restricted loaded ({len(restr_text)} chars).")
            assert "Steel Dynamics" not in restr_text
            await take_screenshot("05_master_directory_restricted.png")

            # 6. Detail: Imperial Metal Services (Facility 22)
            print("\n[QA] 6. Inspecting Detail: Imperial Metal Services (Facility 22)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/22")
            ims_text = await eval_js("document.body.innerText")
            assert "Imperial Metal Services" in ims_text
            assert "Etobicoke" in ims_text
            await take_screenshot("06_detail_imperial_metal_services.png")

            # 7. Detail: Tolko Industries (Facility 81)
            print("\n[QA] 7. Inspecting Detail: Tolko Industries (Facility 81)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/81")
            tolko_text = await eval_js("document.body.innerText")
            assert "Tolko" in tolko_text
            assert "Armstrong Division" in tolko_text
            await take_screenshot("07_detail_tolko_industries.png")

            # 8. Detail: O'Neal Steel (Facility 262)
            print("\n[QA] 8. Inspecting Detail: O'Neal Steel (Facility 262)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/262")
            oneal_text = await eval_js("document.body.innerText")
            assert "Birmingham Service Center" in oneal_text
            assert "Neal" in oneal_text
            await take_screenshot("08_detail_oneal_steel.png")

            # 9. Detail: Precision Strip (Facility 134)
            print("\n[QA] 9. Inspecting Detail: Precision Strip (Facility 134)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/134")
            ps_text = await eval_js("document.body.innerText")
            assert "Precision Strip" in ps_text
            assert "Own Trucks Confirmed" in ps_text
            await take_screenshot("09_detail_precision_strip.png")

            # 10. Detail: Steel Dynamics (Facility 266)
            print("\n[QA] 10. Inspecting Detail: Steel Dynamics (Facility 266)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/266")
            sdi_text = await eval_js("document.body.innerText")
            assert "Steel Dynamics" in sdi_text
            assert "Butler Flat Roll" in sdi_text
            await take_screenshot("10_detail_steel_dynamics_restricted.png")

            # 11. Detail: Peerless Steel (Facility 482)
            print("\n[QA] 11. Inspecting Detail: Peerless Steel (Facility 482)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/482")
            peerless_text = await eval_js("document.body.innerText")
            assert "Peerless Steel" in peerless_text
            await take_screenshot("11_detail_peerless_steel.png")

            # 12. Detail: Rex Lumber (Facility 65)
            print("\n[QA] 12. Inspecting Detail: Rex Lumber (Facility 65)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/65")
            rex_text = await eval_js("document.body.innerText")
            assert "Rex Lumber" in rex_text
            assert "Chris Brown" in rex_text
            await take_screenshot("12_detail_rex_lumber.png")

            # 13. Detail: Two Rivers Lumber (Facility 69)
            print("\n[QA] 13. Inspecting Detail: Two Rivers Lumber (Facility 69)...", flush=True)
            await navigate(f"http://127.0.0.1:{APP_PORT}/prospects/69")
            two_rivers_text = await eval_js("document.body.innerText")
            assert "Two Rivers" in two_rivers_text
            assert "Jody King" in two_rivers_text
            await take_screenshot("13_detail_two_rivers_lumber.png")

            print("\n[QA] All 13 Visual QA inspections completed successfully!", flush=True)
            print(f"[QA] Total Console Errors Encountered: {len(console_errors)}", flush=True)
            if console_errors:
                for err in console_errors:
                    print(f"  - Console Error: {err}", flush=True)
            assert len(console_errors) == 0, f"Found {len(console_errors)} console errors."

    finally:
        print("[QA] Shutting down Chrome and FastAPI server...", flush=True)
        try:
            chrome_proc.terminate()
            chrome_proc.wait(timeout=3)
        except Exception:
            chrome_proc.kill()

        try:
            server_proc.terminate()
            server_proc.wait(timeout=3)
        except Exception:
            server_proc.kill()


if __name__ == "__main__":
    asyncio.run(run_qa())
