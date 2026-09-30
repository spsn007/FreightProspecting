"""
Automated Visual QA and Grid Alignment Verification Script.
- Launches headless Chrome via CDP and connects to local FreightProspecting server.
- Verifies DOM bounding boxes programmatically with <= 2px strict tolerance.
- Audits console errors (must be 0).
- Captures all 10 required visual QA screenshots with alignment overlays.
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
CDP_PORT = 9293
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_grid_pass"
ARTIFACT_DIR = Path(r"C:\Users\DELL\.gemini\antigravity\brain\fd601586-73de-4870-a85c-36d5522ed7e8") / "screenshots" / "grid_alignment_pass"
LOCAL_SHOTS_DIR = Path(__file__).parent.parent / "screenshots" / "grid_alignment_pass"

async def run_qa():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_SHOTS_DIR.mkdir(parents=True, exist_ok=True)

    root_dir = Path(__file__).parent.parent
    venv_py = root_dir / ".venv" / "Scripts" / "python.exe"

    print("[QA] Cleaning port 8000...", flush=True)
    subprocess.run([str(venv_py), "scripts/prepare_server_port.py"], cwd=str(root_dir))

    print(f"[QA] Starting Uvicorn server on port {APP_PORT}...", flush=True)
    server_proc = subprocess.Popen(
        [str(venv_py), "-m", "uvicorn", "src.backend.main:app", "--host", "127.0.0.1", "--port", str(APP_PORT)],
        cwd=str(root_dir),
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
                print(f"[SCREENSHOT] Saved: {filename} ({len(img_data)} bytes)", flush=True)

            # ==========================================
            # STEP 1: 1440x900 Master Directory Dark Mode
            # ==========================================
            print("[QA] Testing 1440x900 Master Directory in Dark Mode...", flush=True)
            await set_viewport(1440, 900)
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/prospects"})
            await asyncio.sleep(2.0)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.5)

            # Evaluate card geometry
            js_measure = """
            (() => {
                const targetNames = [
                    "AmeriSteel",
                    "Andersen Pacific Forest Products Ltd.",
                    "Battle Lumber Company"
                ];
                const cards = Array.from(document.querySelectorAll('.company-card'));
                const results = {};

                for (const name of targetNames) {
                    const card = cards.find(c => {
                        const brandEl = c.querySelector('span[x-text="c.operating_brand"]') || c.querySelector('.broker-brand-title');
                        return brandEl && brandEl.textContent.trim().includes(name);
                    });
                    if (!card) continue;
                    const cardRect = card.getBoundingClientRect();
                    const whyBox = card.querySelector('.broker-why-container') || card.querySelector('.broker-discovery-container');
                    const contactCol = card.querySelector('.broker-card-col-contact');
                    const actionCol = card.querySelector('.broker-card-actions');
                    const round = (val) => Math.round(val * 10) / 10;

                    results[name] = {
                        card_left: round(cardRect.left),
                        card_right: round(cardRect.right),
                        card_width: round(cardRect.width),
                        why_left: whyBox ? round(whyBox.getBoundingClientRect().left) : null,
                        why_width: whyBox ? round(whyBox.getBoundingClientRect().width) : null,
                        why_top: whyBox ? round(whyBox.getBoundingClientRect().top) : null,
                        contact_left: contactCol ? round(contactCol.getBoundingClientRect().left) : null,
                        contact_width: contactCol ? round(contactCol.getBoundingClientRect().width) : null,
                        contact_top: contactCol ? round(contactCol.getBoundingClientRect().top) : null,
                        action_left: actionCol ? round(actionCol.getBoundingClientRect().left) : null,
                        action_width: actionCol ? round(actionCol.getBoundingClientRect().width) : null,
                        action_right: actionCol ? round(actionCol.getBoundingClientRect().right) : null,
                        action_top: actionCol ? round(actionCol.getBoundingClientRect().top) : null,
                        right_gutter: (cardRect && actionCol) ? round(cardRect.right - actionCol.getBoundingClientRect().right) : null
                    };
                }
                return results;
            })()
            """
            eval_res = await send("Runtime.evaluate", {"expression": js_measure, "returnByValue": True})
            measurements = eval_res.get("result", {}).get("value", {})
            print("[QA] Measured DOM Geometry:\n", json.dumps(measurements, indent=2))

            # Programmatic assertions
            names = ["AmeriSteel", "Andersen Pacific Forest Products Ltd.", "Battle Lumber Company"]
            c1 = measurements[names[0]]
            c2 = measurements[names[1]]
            c3 = measurements[names[2]]

            # Assert Contact Column geometry
            assert abs(c1["contact_left"] - c2["contact_left"]) <= 2.0, f"Contact left diff {c1['contact_left']} vs {c2['contact_left']} > 2px"
            assert abs(c1["contact_left"] - c3["contact_left"]) <= 2.0, f"Contact left diff {c1['contact_left']} vs {c3['contact_left']} > 2px"
            assert abs(c1["contact_width"] - c2["contact_width"]) <= 2.0, f"Contact width diff {c1['contact_width']} vs {c2['contact_width']} > 2px"
            assert abs(c1["contact_width"] - c3["contact_width"]) <= 2.0, f"Contact width diff {c1['contact_width']} vs {c3['contact_width']} > 2px"

            # Assert Action Column geometry
            assert abs(c1["action_left"] - c2["action_left"]) <= 2.0, f"Action left diff {c1['action_left']} vs {c2['action_left']} > 2px"
            assert abs(c1["action_left"] - c3["action_left"]) <= 2.0, f"Action left diff {c1['action_left']} vs {c3['action_left']} > 2px"
            assert abs(c1["action_width"] - c2["action_width"]) <= 2.0, f"Action width diff {c1['action_width']} vs {c2['action_width']} > 2px"
            assert abs(c1["action_width"] - c3["action_width"]) <= 2.0, f"Action width diff {c1['action_width']} vs {c3['action_width']} > 2px"
            assert abs(c1["action_right"] - c2["action_right"]) <= 2.0, f"Action right diff {c1['action_right']} vs {c2['action_right']} > 2px"
            assert abs(c1["action_right"] - c3["action_right"]) <= 2.0, f"Action right diff {c1['action_right']} vs {c3['action_right']} > 2px"

            # Assert Right Gutter
            assert abs(c1["right_gutter"] - c2["right_gutter"]) <= 2.0, f"Right gutter diff {c1['right_gutter']} vs {c2['right_gutter']} > 2px"
            assert abs(c1["right_gutter"] - c3["right_gutter"]) <= 2.0, f"Right gutter diff {c1['right_gutter']} vs {c3['right_gutter']} > 2px"

            # Assert Why Column geometry
            assert abs(c1["why_left"] - c2["why_left"]) <= 2.0, f"Why left diff {c1['why_left']} vs {c2['why_left']} > 2px"
            assert abs(c1["why_left"] - c3["why_left"]) <= 2.0, f"Why left diff {c1['why_left']} vs {c3['why_left']} > 2px"
            assert abs(c1["why_width"] - c2["why_width"]) <= 2.0, f"Why width diff {c1['why_width']} vs {c2['why_width']} > 2px"
            assert abs(c1["why_width"] - c3["why_width"]) <= 2.0, f"Why width diff {c1['why_width']} vs {c3['why_width']} > 2px"

            # Assert Vertical Row Baseline (Top alignment within each card)
            for n in names:
                m = measurements[n]
                assert abs(m["why_top"] - m["contact_top"]) <= 2.0, f"[{n}] Why top ({m['why_top']}) != Contact top ({m['contact_top']})"
                assert abs(m["why_top"] - m["action_top"]) <= 2.0, f"[{n}] Why top ({m['why_top']}) != Action top ({m['action_top']})"

            print("[QA] ALL PROGRAMMATIC GEOMETRY ASSERTIONS PASSED WITH ZERO TOLERANCE ISSUES!", flush=True)

            # 1. Capture 01_master_directory_three_cards_grid_dark.png
            await take_screenshot("01_master_directory_three_cards_grid_dark.png")

            # 2. Add visual yellow dashed alignment guidelines and capture 02_master_directory_alignment_guides_dark.png
            js_overlay = """
            (() => {
                const overlay = document.createElement('div');
                overlay.id = 'qa-alignment-overlay';
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100vw';
                overlay.style.height = '100vh';
                overlay.style.pointerEvents = 'none';
                overlay.style.zIndex = '999999';

                // Guideline X positions
                const lines = [
                    { x: 299, label: 'Why Col Left (299px)' },
                    { x: 838, label: 'Why Col Right (838px)' },
                    { x: 862, label: 'Contact Col Left (862px)' },
                    { x: 1142, label: 'Contact Col Right (1142px)' },
                    { x: 1166, label: 'Action Col Left (1166px)' },
                    { x: 1376, label: 'Action Col Right (1376px)' }
                ];

                for (const line of lines) {
                    const l = document.createElement('div');
                    l.style.position = 'absolute';
                    l.style.left = line.x + 'px';
                    l.style.top = '0';
                    l.style.width = '1px';
                    l.style.height = '100vh';
                    l.style.borderLeft = '2px dashed #facc15';
                    l.style.opacity = '0.9';

                    const tag = document.createElement('div');
                    tag.style.position = 'absolute';
                    tag.style.left = (line.x + 4) + 'px';
                    tag.style.top = '8px';
                    tag.style.background = '#854d0e';
                    tag.style.color = '#fef08a';
                    tag.style.fontSize = '10px';
                    tag.style.fontWeight = 'bold';
                    tag.style.padding = '2px 4px';
                    tag.style.borderRadius = '3px';
                    tag.textContent = line.label;

                    overlay.appendChild(l);
                    overlay.appendChild(tag);
                }
                document.body.appendChild(overlay);
            })()
            """
            await send("Runtime.evaluate", {"expression": js_overlay})
            await asyncio.sleep(0.3)
            await take_screenshot("02_master_directory_alignment_guides_dark.png")

            # Remove overlay
            await send("Runtime.evaluate", {"expression": "document.getElementById('qa-alignment-overlay')?.remove();"})
            await asyncio.sleep(0.2)

            # 3. Capture 03_master_directory_light.png
            print("[QA] Testing Light Mode...", flush=True)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('fp_theme', 'light');"
            })
            await asyncio.sleep(0.4)
            await take_screenshot("03_master_directory_light.png")

            # Switch back to dark mode
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.3)

            # 4. Capture 04_search_s_dark.png
            print("[QA] Testing Search 'S'...", flush=True)
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/prospects?q=S"})
            await asyncio.sleep(1.5)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.3)
            # Verify top card
            js_top_card = "document.querySelector('.company-card span[x-text=\"c.operating_brand\"]')?.textContent.trim()"
            top_eval = await send("Runtime.evaluate", {"expression": js_top_card})
            top_name = top_eval.get("result", {}).get("value")
            print(f"[QA] Search 'S' top result: {top_name}", flush=True)
            assert top_name and top_name.startswith("S"), f"Top result for 'S' does not start with S: {top_name}"
            await take_screenshot("04_search_s_dark.png")

            # 5. Capture 05_search_ameri_dark.png
            print("[QA] Testing Search 'Ameri'...", flush=True)
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/prospects?q=Ameri"})
            await asyncio.sleep(1.5)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.3)
            top_eval = await send("Runtime.evaluate", {"expression": js_top_card})
            top_name = top_eval.get("result", {}).get("value")
            print(f"[QA] Search 'Ameri' top result: {top_name}", flush=True)
            assert top_name == "AmeriSteel", f"Top result for 'Ameri' is not AmeriSteel: {top_name}"
            await take_screenshot("05_search_ameri_dark.png")

            # 6. Capture 06_search_steel_dark.png
            print("[QA] Testing Search 'Steel'...", flush=True)
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/prospects?q=Steel"})
            await asyncio.sleep(1.5)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.3)
            await take_screenshot("06_search_steel_dark.png")

            # 7. Capture 07_cockpit_three_cards_dark.png
            print("[QA] Testing Cockpit Layout...", flush=True)
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/"})
            await asyncio.sleep(1.5)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.3)
            # Verify cockpit grid geometry
            js_cockpit = """
            (() => {
                const cards = Array.from(document.querySelectorAll('.company-card'));
                const results = [];
                for (const c of cards.slice(0, 3)) {
                    const why = c.querySelector('.broker-why-container');
                    const contact = c.querySelector('.broker-card-col-contact');
                    const actions = c.querySelector('.broker-card-actions');
                    results.push({
                        why_top: why ? Math.round(why.getBoundingClientRect().top * 10) / 10 : null,
                        contact_top: contact ? Math.round(contact.getBoundingClientRect().top * 10) / 10 : null,
                        actions_top: actions ? Math.round(actions.getBoundingClientRect().top * 10) / 10 : null,
                        contact_width: contact ? Math.round(contact.getBoundingClientRect().width * 10) / 10 : null,
                        actions_width: actions ? Math.round(actions.getBoundingClientRect().width * 10) / 10 : null,
                    });
                }
                return results;
            })()
            """
            cockpit_eval = await send("Runtime.evaluate", {"expression": js_cockpit, "returnByValue": True})
            cockpit_res = cockpit_eval.get("result", {}).get("value", [])
            print("[QA] Cockpit Cards Geometry:\n", json.dumps(cockpit_res, indent=2))
            for i, r in enumerate(cockpit_res):
                assert abs(r["why_top"] - r["contact_top"]) <= 2.0, f"Cockpit card {i} why_top != contact_top"
                assert abs(r["why_top"] - r["actions_top"]) <= 2.0, f"Cockpit card {i} why_top != actions_top"
                assert r["contact_width"] == 280.0, f"Cockpit card {i} contact_width != 280.0"
                assert r["actions_width"] == 210.0, f"Cockpit card {i} actions_width != 210.0"

            await take_screenshot("07_cockpit_three_cards_dark.png")

            # 8. Capture 08_master_directory_1024.png
            print("[QA] Testing Viewport 1024x768...", flush=True)
            await set_viewport(1024, 768)
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/prospects"})
            await asyncio.sleep(1.5)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.3)
            await take_screenshot("08_master_directory_1024.png")

            # 9. Capture 09_master_directory_768.png
            print("[QA] Testing Viewport 768x1024...", flush=True)
            await set_viewport(768, 1024)
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/prospects"})
            await asyncio.sleep(1.5)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.3)
            await take_screenshot("09_master_directory_768.png")

            # 10. Capture 10_master_directory_mobile_375.png
            print("[QA] Testing Viewport 375x812...", flush=True)
            await set_viewport(375, 812)
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/prospects"})
            await asyncio.sleep(1.5)
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark'); document.querySelector('.company-card')?.scrollIntoView({behavior: 'instant', block: 'start'});"
            })
            await asyncio.sleep(0.4)
            await take_screenshot("10_master_directory_mobile_375.png")

            # Console error audit
            print(f"[QA] Console Errors Detected: {len(console_errors)}", flush=True)
            if console_errors:
                print("[ERROR] Console Errors:\n", json.dumps(console_errors, indent=2))
            assert len(console_errors) == 0, f"Found {len(console_errors)} console errors during test run."

            print("\n[SUCCESS] ALL 10 SCREENSHOTS CAPTURED, DOM ASSERTIONS PASSED, 0 CONSOLE ERRORS!", flush=True)

    finally:
        chrome_proc.terminate()
        server_proc.terminate()
        subprocess.run([str(venv_py), "scripts/prepare_server_port.py"], cwd=str(root_dir))

if __name__ == "__main__":
    asyncio.run(run_qa())
