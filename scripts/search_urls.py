import glob, re

for p in glob.glob("src/backend/templates/*.html"):
    with open(p, encoding="utf-8") as f:
        lines = f.readlines()
    for idx, line in enumerate(lines, 1):
        if "href=" in line and ("url" in line.lower() or "website" in line.lower() or "link" in line.lower()):
            print(f"{p}:{idx}: {line.strip()}")
