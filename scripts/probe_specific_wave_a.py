import asyncio
import re
from urllib.parse import urljoin
import httpx

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

URLS_TO_TEST = [
    # Lindsay Precast
    "https://lindsayprecast.com/suppliers",
    "https://lindsayprecast.com/contact-us",
    # High Concrete
    "https://www.highconcrete.com/about-us",
    "https://www.highconcrete.com/contact",
    # Coreslab
    "https://coreslab.com/locations/ontario/",
    "https://coreslab.com/about-us/",
    # Janco Steel
    "https://jancosteel.com/about-us/",
    "https://jancosteel.com/contact-us/",
]

async def main():
    async with httpx.AsyncClient(headers=HEADERS, verify=False) as client:
        for u in URLS_TO_TEST:
            try:
                r = await client.get(u, timeout=10.0)
                if r.status_code == 200:
                    text = re.sub(r'<[^>]+>', ' ', r.text)
                    text = re.sub(r'\s+', ' ', text)
                    matches = re.findall(r'(?:carrier|freight|delivery|truckload|shipping)[^.!?]{0,100}[.!?]', text, re.I)
                    print(f"[200 OK] {u} (matches: {len(matches)})")
                    for m in matches[:2]:
                        print("  ", m.strip())
                else:
                    print(f"[{r.status_code}] {u}")
            except Exception as e:
                print(f"[ERR] {u}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
