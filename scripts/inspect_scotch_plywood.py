import httpx
import re
from urllib.parse import urljoin

url = "https://www.scotchplywood.com/"
resp = httpx.get(url, verify=False)
for h in set(re.findall(r'href=["\']([^"\']+)["\']', resp.text)):
    if any(k in h.lower() for k in ["ship", "transport", "logist", "contact"]):
        full = urljoin(url, h)
        print("LINK:", full)
        try:
            sub = httpx.get(full, verify=False, timeout=8.0)
            text = re.sub(r'<[^>]+>', ' ', sub.text)
            text = re.sub(r'\s+', ' ', text)
            m = re.findall(r'(?:carrier|fleet|truck|freight|delivery|shipping)[^.!?\n]{0,120}[.!?\n]', text, re.I)
            for item in m[:3]:
                print("  ", item.strip())
        except Exception as e:
            print("  Err:", e)
