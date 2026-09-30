import asyncio
import base64
import json
import subprocess
import time
import urllib.request
import websockets

async def inspect():
    proc = subprocess.Popen([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "--headless=new",
        "--remote-debugging-port=9222",
        "--disable-gpu",
        "http://127.0.0.1:8000/prospects"
    ])
    await asyncio.sleep(2)

    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json") as r:
            targets = json.loads(r.read().decode("utf-8"))
        page_target = next(t for t in targets if "127.0.0.1:8000/prospects" in t.get("url", ""))
        ws_url = page_target["webSocketDebuggerUrl"]
        print("Connected to page target:", ws_url)

        async with websockets.connect(ws_url) as ws:
            # Enable Runtime and Console
            await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Console.enable"}))
            await ws.send(json.dumps({"id": 3, "method": "Log.enable"}))

            await asyncio.sleep(2)

            # Read any buffered messages
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=0.5)
                    data = json.loads(msg)
                    method = data.get("method")
                    if method in ("Console.messageAdded", "Runtime.exceptionThrown", "Log.entryAdded"):
                        print("CONSOLE/RUNTIME EVENT:", json.dumps(data, indent=2))
                except asyncio.TimeoutError:
                    break

            # Evaluate expressions
            exprs = [
                "window.Alpine !== undefined",
                "document.querySelectorAll('.company-card').length",
                "document.querySelectorAll('.metric-card').length",
                "document.querySelector('.section-title')?.innerText",
                "document.querySelector('script#company-groups-data') !== null",
                "document.querySelector('script#prospects-data') !== null",
                "document.body.innerText.substring(0, 300)"
            ]
            for expr in exprs:
                await ws.send(json.dumps({
                    "id": 10,
                    "method": "Runtime.evaluate",
                    "params": {"expression": expr, "returnByValue": True}
                }))
                res = json.loads(await ws.recv())
                val = res.get("result", {}).get("result", {}).get("value")
                val_str = str(val).encode('ascii', errors='replace').decode('ascii')
                print(f"EVAL [{expr}] -> {val_str}")

            # 1. Search for Georgia-Pacific
            print("\n--- Testing Search for Georgia-Pacific ---")
            await ws.send(json.dumps({
                "id": 30,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """(() => {
                        const input = document.querySelector('input.search-input');
                        input.value = 'Georgia-Pacific';
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                    })()"""
                }
            }))
            await ws.recv()
            await asyncio.sleep(1)

            # Check search results
            await ws.send(json.dumps({
                "id": 31,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": "document.querySelectorAll('.company-card').length",
                    "returnByValue": True
                }
            }))
            res = json.loads(await ws.recv())
            print("Company cards visible after search 'Georgia-Pacific':", res.get("result", {}).get("result", {}).get("value"))

            # 2. Expand Georgia-Pacific
            print("\n--- Expanding Georgia-Pacific ---")
            await ws.send(json.dumps({
                "id": 32,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """(() => {
                        const btn = document.querySelector('.company-card button');
                        if (btn) btn.click();
                    })()"""
                }
            }))
            await ws.recv()
            await asyncio.sleep(1)

            # Check child facility rows
            await ws.send(json.dumps({
                "id": 33,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": "document.querySelectorAll('.child-facilities-table tbody tr').length",
                    "returnByValue": True
                }
            }))
            res = json.loads(await ws.recv())
            print("Child facility rows visible for GP:", res.get("result", {}).get("result", {}).get("value"))

            # Check child facility names
            await ws.send(json.dumps({
                "id": 34,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": "Array.from(document.querySelectorAll('.child-facilities-table tbody tr td:first-child div:first-child')).map(el => el.innerText)",
                    "returnByValue": True
                }
            }))
            res = json.loads(await ws.recv())
            print("Child facility names:", res.get("result", {}).get("result", {}).get("value"))

            # Capture screenshot of expanded GP
            await ws.send(json.dumps({
                "id": 35,
                "method": "Page.captureScreenshot",
                "params": {"captureBeyondViewport": True}
            }))
            s_res = json.loads(await ws.recv())
            img_b64 = s_res.get("result", {}).get("data")
            if img_b64:
                with open("browser_gp_expanded.png", "wb") as f:
                    f.write(base64.b64decode(img_b64))
                print("Saved browser_gp_expanded.png successfully!")

            # 3. Test Toggle to Facilities View
            print("\n--- Testing Toggle to Facilities View ---")
            await ws.send(json.dumps({
                "id": 36,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """(() => {
                        // Reset search
                        const input = document.querySelector('input.search-input');
                        input.value = '';
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        // Click Facilities toggle
                        const btns = document.querySelectorAll('.view-toggle-btn');
                        if (btns[1]) btns[1].click();
                    })()"""
                }
            }))
            await ws.recv()
            await asyncio.sleep(1)

            # 4. Test Dark Mode Toggle
            print("\n--- Testing Dark Mode Toggle ---")
            await ws.send(json.dumps({
                "id": 40,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": """(() => {
                        const themeBtn = document.querySelector('button[onclick*=\"toggleTheme\"]') || document.querySelector('#theme-toggle') || document.querySelector('.theme-btn');
                        if (themeBtn) {
                            themeBtn.click();
                        } else {
                            document.documentElement.setAttribute('data-theme', 'dark');
                        }
                    })()"""
                }
            }))
            await ws.recv()
            await asyncio.sleep(1)

            # Check theme attribute
            await ws.send(json.dumps({
                "id": 41,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": "document.documentElement.getAttribute('data-theme')",
                    "returnByValue": True
                }
            }))
            res = json.loads(await ws.recv())
            print("Current data-theme attribute:", res.get("result", {}).get("result", {}).get("value"))

            # Capture Dark Mode screenshot
            await ws.send(json.dumps({
                "id": 42,
                "method": "Page.captureScreenshot",
                "params": {"captureBeyondViewport": True}
            }))
            s_res = json.loads(await ws.recv())
            img_b64 = s_res.get("result", {}).get("data")
            if img_b64:
                with open("browser_prospects_dark.png", "wb") as f:
                    f.write(base64.b64decode(img_b64))
                print("Saved browser_prospects_dark.png successfully!")

    finally:
        proc.terminate()

if __name__ == "__main__":
    asyncio.run(inspect())
