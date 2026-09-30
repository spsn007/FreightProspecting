"""
Phase 1: DOM Measurement Script for FreightProspecting Master Directory.
Measures exact boundingClientRect() of AmeriSteel, Andersen Pacific, and Battle Lumber cards.
"""

import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
import websockets

APP_PORT = 8000
CDP_PORT = 9292
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA_DIR = r"C:\Users\DELL\AppData\Local\Temp\chrome_qa_measure"

async def measure():
    venv_py = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
    subprocess.run([str(venv_py), "scripts/prepare_server_port.py"], cwd=str(Path(__file__).parent.parent))

    print(f"[MEASURE] Starting Uvicorn on port {APP_PORT}...", flush=True)
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
                    print(f"[MEASURE] Uvicorn server is up.", flush=True)
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
        print("[MEASURE] Failed to connect to Chrome CDP.")
        server_proc.terminate()
        chrome_proc.terminate()
        return

    try:
        async with websockets.connect(ws_url) as ws:
            # Helper send
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
                    if res.get("id") == req_id:
                        return res.get("result", {})

            await send("Page.enable")
            await send("Runtime.enable")
            await send("Emulation.setDeviceMetricsOverride", {
                "width": 1440,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False,
            })
            await send("Page.navigate", {"url": f"http://127.0.0.1:{APP_PORT}/prospects"})
            await asyncio.sleep(2.0)

            # Set dark mode
            await send("Runtime.evaluate", {
                "expression": "document.documentElement.setAttribute('data-theme', 'dark'); localStorage.setItem('fp_theme', 'dark');"
            })
            await asyncio.sleep(0.5)

            # JS script to inspect the three cards
            js_code = """
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

                    if (!card) {
                        results[name] = { error: "Card not found" };
                        continue;
                    }

                    const cardRect = card.getBoundingClientRect();
                    const infoCol = card.querySelector('.broker-card-col-info') || card.querySelector('.company-card-grid-broker > div:first-child');
                    const infoRect = infoCol ? infoCol.getBoundingClientRect() : null;

                    const whyBox = card.querySelector('.broker-why-container') || card.querySelector('.broker-discovery-container');
                    const whyRect = whyBox ? whyBox.getBoundingClientRect() : null;

                    const contactCol = card.querySelector('.broker-card-col-contact') || card.querySelector('.company-card-grid-broker > div:nth-child(2)');
                    const contactRect = contactCol ? contactCol.getBoundingClientRect() : null;

                    const phoneCard = card.querySelector('.broker-phone-card');
                    const phoneRect = phoneCard ? phoneCard.getBoundingClientRect() : null;

                    const emailLink = card.querySelector('.broker-email-link');
                    const emailRect = emailLink ? emailLink.getBoundingClientRect() : null;

                    const actionCol = card.querySelector('.broker-card-actions');
                    const actionRect = actionCol ? actionCol.getBoundingClientRect() : null;

                    const callNowBtn = card.querySelector('.btn-call');
                    const callNowRect = callNowBtn ? callNowBtn.getBoundingClientRect() : null;

                    const logCallBtn = Array.from(card.querySelectorAll('button')).find(b => b.textContent.includes('Log Call'));
                    const logCallRect = logCallBtn ? logCallBtn.getBoundingClientRect() : null;

                    const reviewBtn = Array.from(card.querySelectorAll('a')).find(a => a.textContent.includes('Review Prospect'));
                    const reviewRect = reviewBtn ? reviewBtn.getBoundingClientRect() : null;

                    const detailsBtn = Array.from(card.querySelectorAll('button')).find(b => b.textContent.includes('Details') || b.textContent.includes('Hide Details'));
                    const detailsRect = detailsBtn ? detailsBtn.getBoundingClientRect() : null;

                    const fmt = (r) => r ? {
                        left: Math.round(r.left * 10) / 10,
                        right: Math.round(r.right * 10) / 10,
                        top: Math.round(r.top * 10) / 10,
                        bottom: Math.round(r.bottom * 10) / 10,
                        width: Math.round(r.width * 10) / 10,
                        height: Math.round(r.height * 10) / 10
                    } : null;

                    results[name] = {
                        card: fmt(cardRect),
                        info_column: fmt(infoRect),
                        why_box: fmt(whyRect),
                        contact_column: fmt(contactRect),
                        phone_card: fmt(phoneRect),
                        email: fmt(emailRect),
                        action_column: fmt(actionRect),
                        call_now: fmt(callNowRect),
                        log_call: fmt(logCallRect),
                        review_prospect: fmt(reviewRect),
                        details_btn: fmt(detailsRect),
                        right_gutter: (cardRect && actionRect) ? Math.round((cardRect.right - actionRect.right) * 10) / 10 : null
                    };
                }
                return results;
            })()
            """

            res = await send("Runtime.evaluate", {"expression": js_code, "returnByValue": True})
            measurements = res.get("result", {}).get("value")
            print("\n=== PHASE 1 DOM MEASUREMENTS (VIEWPORT 1440x900) ===")
            print(json.dumps(measurements, indent=2))

    finally:
        chrome_proc.terminate()
        server_proc.terminate()
        subprocess.run([str(venv_py), "scripts/prepare_server_port.py"], cwd=str(Path(__file__).parent.parent))

if __name__ == "__main__":
    asyncio.run(measure())
