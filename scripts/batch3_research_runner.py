"""
Batch 3 Autonomous Research Crawler & Analyzer
Crawls company websites, checks subpages (contact, locations, shipping, logistics, carriers, about),
searches for key evidence on outside carriers, private fleets, brokers, and logistics contacts.
"""

import asyncio
import json
import re
import sqlite3
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

COMMON_SUBPAGES = [
    "",
    "/contact",
    "/contact-us",
    "/contact_us",
    "/about",
    "/about-us",
    "/locations",
    "/facilities",
    "/shipping",
    "/shipping-receiving",
    "/logistics",
    "/transportation",
    "/carriers",
    "/carrier-info",
    "/terms",
    "/terms-and-conditions",
    "/terms-of-sale",
    "/careers",
    "/delivery",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def clean_text(html: str) -> str:
    # Quick strip of scripts/styles and html tags
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_emails(text: str) -> list[str]:
    # Extract email addresses, filter out common file-like extensions or fake patterns
    raw_emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    valid = []
    for e in set(raw_emails):
        e_lower = e.lower()
        if any(e_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".js", ".css"]):
            continue
        if len(e) < 50:
            valid.append(e)
    return sorted(valid)


def extract_phones(text: str) -> list[str]:
    raw_phones = re.findall(r"(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    return sorted(list(set(raw_phones)))


async def fetch_url(client: httpx.AsyncClient, url: str) -> dict:
    try:
        resp = await client.get(url, timeout=12.0, follow_redirects=True)
        if resp.status_code == 200:
            text = clean_text(resp.text)
            # Soft 404 detection: check if text indicates not found
            lower_text = text.lower()
            if any(p in lower_text[:400] for p in ["page not found", "404 not found", "does not exist", "error 404"]):
                return {"url": str(resp.url), "status": 404, "text": "", "len": len(text)}
            return {"url": str(resp.url), "status": 200, "text": text, "len": len(text)}
        return {"url": str(resp.url), "status": resp.status_code, "text": "", "len": 0}
    except Exception as e:
        return {"url": url, "status": "ERROR", "error": str(e), "text": "", "len": 0}


async def research_company(company_meta: dict) -> dict:
    cid = company_meta["company_id"]
    brand = company_meta["operating_brand"]
    base_url = company_meta.get("website_url") or ""
    print(f"[{company_meta['batch_position']:02d}] Researching {brand} (CID {cid}) at {base_url}...")

    results = {
        "company_id": cid,
        "operating_brand": brand,
        "batch_position": company_meta["batch_position"],
        "wave": company_meta["wave"],
        "facility_id": company_meta["research_focus_facility_id"],
        "base_url": base_url,
        "pages_checked": [],
        "evidence_snippets": {
            "commercial_carrier": [],
            "broker": [],
            "private_fleet": [],
            "shipping_logistics": [],
            "contacts_found": [],
        },
        "all_emails": set(),
        "all_phones": set(),
    }

    if not base_url or not base_url.startswith("http"):
        return results

    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(headers=HEADERS, verify=False) as client:
        # Check base url + subpages
        tasks = []
        urls_to_try = [base_url]
        for sub in COMMON_SUBPAGES[1:]:
            urls_to_try.append(urljoin(root, sub))

        # Fetch in batches of 5
        page_results = []
        for i in range(0, len(urls_to_try), 5):
            chunk = urls_to_try[i:i+5]
            chunk_res = await asyncio.gather(*[fetch_url(client, u) for u in chunk])
            page_results.extend(chunk_res)

        for pr in page_results:
            if pr.get("status") == 200 and pr.get("len", 0) > 100:
                url = pr["url"]
                text = pr["text"]
                results["pages_checked"].append(url)

                # Emails & phones
                emails = extract_emails(text)
                phones = extract_phones(text)
                results["all_emails"].update(emails)
                results["all_phones"].update(phones)

                # Regex patterns for shipping & logistics
                # 1. Commercial carrier patterns
                carrier_matches = re.findall(
                    r"(?:carrier|motor carrier|common carrier|contract carrier|routing guide|shipping and receiving|truckload|flatbed|pickup appointment|delivery schedule|shipping instructions)[^.!?]{0,150}[.!?]",
                    text,
                    flags=re.IGNORECASE,
                )
                if carrier_matches:
                    results["evidence_snippets"]["commercial_carrier"].extend(
                        [{"url": url, "snippet": m.strip()} for m in carrier_matches[:5]]
                    )

                # 2. Broker / 3PL patterns
                broker_matches = re.findall(
                    r"(?:freight broker|brokerage|3pl|third party logistics|third-party logistics|direct only|asset carriers only)[^.!?]{0,150}[.!?]",
                    text,
                    flags=re.IGNORECASE,
                )
                if broker_matches:
                    results["evidence_snippets"]["broker"].extend(
                        [{"url": url, "snippet": m.strip()} for m in broker_matches[:5]]
                    )

                # 3. Private fleet patterns
                fleet_matches = re.findall(
                    r"(?:our fleet|private fleet|our trucks|company drivers|delivery fleet|fleet of \d+|tractor trailers|in-house delivery)[^.!?]{0,150}[.!?]",
                    text,
                    flags=re.IGNORECASE,
                )
                if fleet_matches:
                    results["evidence_snippets"]["private_fleet"].extend(
                        [{"url": url, "snippet": m.strip()} for m in fleet_matches[:5]]
                    )

                # 4. Logistics contact patterns
                contact_matches = re.findall(
                    r"(?:shipping manager|traffic manager|logistics manager|shipping coordinator|dispatch|plant manager|sales manager)[^.!?]{0,150}[.!?]",
                    text,
                    flags=re.IGNORECASE,
                )
                if contact_matches:
                    results["evidence_snippets"]["shipping_logistics"].extend(
                        [{"url": url, "snippet": m.strip()} for m in contact_matches[:5]]
                    )

    results["all_emails"] = sorted(list(results["all_emails"]))
    results["all_phones"] = sorted(list(results["all_phones"]))
    return results


async def run_wave_research(wave_letter: str):
    with open("reports/batch_3_frozen_selection.json", "r", encoding="utf-8") as f:
        roster = json.load(f)

    wave_items = [r for r in roster if r["wave"] == wave_letter]
    print(f"=== Starting Wave {wave_letter} Research ({len(wave_items)} companies) ===")

    # Get website_urls from DB
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row
    for item in wave_items:
        comp = conn.execute("SELECT website_url FROM companies WHERE id = ?", (item["company_id"],)).fetchone()
        item["website_url"] = comp["website_url"] if comp else None
    conn.close()

    # Run in parallel tracks (chunks of 5)
    all_findings = []
    chunk_size = 5
    for i in range(0, len(wave_items), chunk_size):
        chunk = wave_items[i:i+chunk_size]
        track_num = (i // chunk_size) + 1
        print(f"\n--- Running Track {track_num} (Companies {i+1} to {min(i+chunk_size, len(wave_items))}) ---")
        track_results = await asyncio.gather(*[research_company(c) for c in chunk])
        all_findings.extend(track_results)

    out_file = Path(f"reports/batch_3_wave_{wave_letter}_crawler_raw.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_findings, f, indent=2)
    print(f"\nSaved raw findings to {out_file} ({len(all_findings)} companies).")


if __name__ == "__main__":
    wave = sys.argv[1] if len(sys.argv) > 1 else "A"
    asyncio.run(run_wave_research(wave))
