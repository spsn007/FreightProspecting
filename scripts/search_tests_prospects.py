import glob, re

for p in glob.glob("tests/*.py"):
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()
    for idx, line in enumerate(lines, 1):
        if "/prospects" in line and "client.get" in line:
            print(f"{p}:{idx}: {line.strip()}")
