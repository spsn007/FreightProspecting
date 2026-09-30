"""
Safe port-8000 manager for run_app.bat launcher.
Ensures stale FreightProspecting Uvicorn instances are cleanly restarted,
while strictly protecting unrelated third-party processes.
"""

import socket
import subprocess
import sys
import time

PORT = 8000


def is_port_in_use(port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_freight_prospecting_pids() -> list[int]:
    """Find process IDs running FreightProspecting uvicorn backend."""
    ps_script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*src.backend.main:app*' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_script],
            text=True,
            stderr=subprocess.DEVNULL
        )
        pids = []
        for line in out.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
        return pids
    except Exception:
        return []


def get_port_owning_python_pid(port: int = PORT) -> list[int]:
    """Find PID of any python process currently binding the target port."""
    ps_script = (
        f"$conns = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue; "
        f"foreach ($c in $conns) {{ "
        f"  $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue; "
        f"  if ($p -and $p.ProcessName -like '*python*') {{ $p.Id }} "
        f"}}"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps_script],
            text=True,
            stderr=subprocess.DEVNULL
        )
        pids = []
        for line in out.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
        return list(set(pids))
    except Exception:
        return []


def main() -> int:
    if not is_port_in_use(PORT):
        print(f"[OK] Port {PORT} is available.")
        return 0

    # Port is in use - check if it belongs to FreightProspecting
    fp_pids = set(get_freight_prospecting_pids()) | set(get_port_owning_python_pid(PORT))
    if fp_pids:
        print(f"[INFO] Existing FreightProspecting server detected (PID: {list(fp_pids)}). Restarting cleanly...")
        for pid in fp_pids:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

        # Wait briefly for socket release
        for _ in range(10):
            time.sleep(0.3)
            if not is_port_in_use(PORT):
                print(f"[OK] Stale server stopped. Port {PORT} freed.")
                return 0

        print(f"[OK] Port {PORT} ready for launch.")
        return 0
    else:
        # Port is in use by an unrelated application
        print(f"[ERROR] Port {PORT} is already in use by another application.")
        print(f"[ERROR] Close the application using port {PORT} and retry.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
