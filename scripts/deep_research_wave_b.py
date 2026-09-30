import json
import re
import sqlite3
from urllib.parse import urljoin, urlparse

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_text(html: str) -> str:
    html = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def check_url(url: str, keywords: list[str]):
    print(f"\n--- Checking {url} ---")
    try:
        with httpx.Client(timeout=12.0, headers=HEADERS, follow_redirects=True, verify=False) as client:
            r = client.get(url)
            print(f"Status: {r.status_code}, len={len(r.text)}")
            if r.status_code == 200:
                txt = clean_text(r.text)
                txt_lower = txt.lower()
                for kw in keywords:
                    if kw in txt_lower:
                        print(f"  [Found keyword: '{kw}']")
                        sentences = [s.strip() for s in re.split(r'[.!?]', txt) if kw in s.lower()]
                        for s in sentences[:3]:
                            if len(s) > 20:
                                safe_s = s[:160].encode('ascii', 'replace').decode('ascii')
                                print(f"    * {safe_s}")
    except Exception as e:
        print(f"Error fetching {url}: {e}")

if __name__ == "__main__":
    # Worthington Steel
    check_url("https://www.worthingtonsteel.com/company/working-with-us/contact-us", ["carrier", "shipping", "freight", "routing"])
    check_url("https://www.worthingtonsteel.com/company/working-with-us/carriers", ["carrier", "freight", "portal", "insurance", "onboarding"])
    
    # Alro Steel
    check_url("https://www.alro.com/about/aboutus.aspx", ["fleet", "truck", "delivery", "carrier"])
    check_url("https://www.alro.com/services/delivery.aspx", ["fleet", "truck", "delivery", "carrier"])
    
    # Mill Steel
    check_url("https://www.millsteel.com/about-us/", ["fleet", "truck", "carrier", "logistics", "freight"])
    check_url("https://www.millsteel.com/services/logistics/", ["fleet", "truck", "carrier", "logistics", "freight"])
    
    # Steel Warehouse
    check_url("https://www.steelwarehouse.com/about/", ["fleet", "truck", "carrier", "delivery"])
    check_url("https://www.steelwarehouse.com/services/", ["fleet", "truck", "carrier", "delivery"])

    # FerrouSouth
    check_url("https://ferrousouth.com/contacts/", ["tim nave", "sales", "manager", "phone", "email"])
    
    # Two Rivers Lumber
    check_url("https://tworiverslumber.com/contact/", ["shipping", "sales", "dispatch", "phone", "email"])
