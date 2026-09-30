"""
FreightProspecting V1 — Phase A Autonomous Research Crawler
Exhaustively crawls target company websites, collects full machine-auditable provenance,
and extracts evidence on commercial carrier use, private fleet, broker policy, and logistics contacts.
"""

import asyncio
import hashlib
import json
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

COMMON_SUBPAGES = [
    "",
    "/shipping",
    "/shipping-receiving",
    "/delivery",
    "/delivery-services",
    "/transportation",
    "/logistics",
    "/carriers",
    "/carrier-info",
    "/carrier-onboarding",
    "/freight",
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/locations",
    "/facilities",
    "/services",
    "/terms",
    "/terms-and-conditions",
    "/terms-of-sale",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_html(html: str) -> tuple[str, str]:
    """Extract page title and clean visible text."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    title = re.sub(r"\s+", " ", title)

    # Strip scripts, styles, comments
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def extract_internal_links(html: str, base_url: str) -> list[str]:
    """Extract candidate links related to logistics, shipping, delivery, transport."""
    keywords = ["ship", "deliver", "transport", "logist", "carrier", "fleet", "contact", "locat"]
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower()

    raw_hrefs = re.findall(r'href=[\'"]([^\'"#\s>]+)[\'"]', html, re.IGNORECASE)
    found_urls = set()

    for href in raw_hrefs:
        if href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        if parsed.netloc.lower() != base_domain:
            continue
        path_lower = parsed.path.lower()
        if any(kw in path_lower for kw in keywords):
            # Clean url
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            found_urls.add(clean)

    return sorted(list(found_urls))[:10]


async def fetch_page(client: httpx.AsyncClient, url: str) -> dict:
    """Fetch URL and capture full 11-field provenance."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parsed = urlparse(url)
    domain = parsed.hostname

    # DNS check
    dns_status = "RESOLVED"
    try:
        if domain:
            socket.gethostbyname(domain)
        else:
            dns_status = "FAILED"
    except Exception:
        dns_status = "FAILED"

    if dns_status == "FAILED":
        return {
            "attempted_url": url,
            "requested_at_utc": now_utc,
            "http_status": None,
            "final_url": url,
            "dns_status": "FAILED",
            "access_status": "INACCESSIBLE",
            "content_type": None,
            "response_length": 0,
            "page_title": None,
            "content_sha256": None,
            "result": "DNS_FAILURE",
            "text": "",
            "internal_links": [],
        }

    try:
        resp = await client.get(url, timeout=12.0, follow_redirects=True)
        http_code = resp.status_code
        final_url = str(resp.url)
        c_type = resp.headers.get("content-type")
        body_bytes = resp.content
        c_len = len(body_bytes)
        c_hash = hashlib.sha256(body_bytes).hexdigest()

        if http_code == 200:
            html = resp.text
            title, text = clean_html(html)
            # Detect soft 404
            lower_text = text.lower()
            if any(p in lower_text[:400] for p in ["404 not found", "page not found", "does not exist", "error 404"]):
                return {
                    "attempted_url": url,
                    "requested_at_utc": now_utc,
                    "http_status": 404,
                    "final_url": final_url,
                    "dns_status": "RESOLVED",
                    "access_status": "INACCESSIBLE",
                    "content_type": c_type,
                    "response_length": c_len,
                    "page_title": title or "Not Found",
                    "content_sha256": c_hash,
                    "result": "HTTP_404",
                    "text": "",
                    "internal_links": [],
                }
            links = extract_internal_links(html, final_url)
            return {
                "attempted_url": url,
                "requested_at_utc": now_utc,
                "http_status": 200,
                "final_url": final_url,
                "dns_status": "RESOLVED",
                "access_status": "ACCESSIBLE",
                "content_type": c_type,
                "response_length": c_len,
                "page_title": title,
                "content_sha256": c_hash,
                "result": "SUCCESS_FETCHED",
                "text": text,
                "internal_links": links,
            }
        elif http_code == 403:
            return {
                "attempted_url": url,
                "requested_at_utc": now_utc,
                "http_status": 403,
                "final_url": final_url,
                "dns_status": "RESOLVED",
                "access_status": "BLOCKED",
                "content_type": c_type,
                "response_length": c_len,
                "page_title": None,
                "content_sha256": c_hash,
                "result": "HTTP_403",
                "text": "",
                "internal_links": [],
            }
        elif http_code == 404:
            return {
                "attempted_url": url,
                "requested_at_utc": now_utc,
                "http_status": 404,
                "final_url": final_url,
                "dns_status": "RESOLVED",
                "access_status": "INACCESSIBLE",
                "content_type": c_type,
                "response_length": c_len,
                "page_title": None,
                "content_sha256": c_hash,
                "result": "HTTP_404",
                "text": "",
                "internal_links": [],
            }
        else:
            return {
                "attempted_url": url,
                "requested_at_utc": now_utc,
                "http_status": http_code,
                "final_url": final_url,
                "dns_status": "RESOLVED",
                "access_status": "INACCESSIBLE",
                "content_type": c_type,
                "response_length": c_len,
                "page_title": None,
                "content_sha256": c_hash,
                "result": "HTTP_OTHER_ERROR",
                "text": "",
                "internal_links": [],
            }
    except httpx.TimeoutException:
        return {
            "attempted_url": url,
            "requested_at_utc": now_utc,
            "http_status": None,
            "final_url": url,
            "dns_status": "RESOLVED",
            "access_status": "INACCESSIBLE",
            "content_type": None,
            "response_length": 0,
            "page_title": None,
            "content_sha256": None,
            "result": "TIMEOUT",
            "text": "",
            "internal_links": [],
        }
    except Exception as e:
        err_str = str(e).lower()
        res_type = "TLS_FAILURE" if "ssl" in err_str or "tls" in err_str else "OFFICIAL_SOURCE_INACCESSIBLE"
        return {
            "attempted_url": url,
            "requested_at_utc": now_utc,
            "http_status": None,
            "final_url": url,
            "dns_status": "RESOLVED",
            "access_status": "INACCESSIBLE",
            "content_type": None,
            "response_length": 0,
            "page_title": None,
            "content_sha256": None,
            "result": res_type,
            "text": "",
            "internal_links": [],
        }


def extract_evidence(text: str, page_url: str) -> dict:
    """Extract evidence snippets and contacts from clean text."""
    carrier_patterns = [
        r"(?:(?:commercial|common|contract|outside|third-party|third party|independent|approved|authorized)\s+carriers?[^.!?\n]{0,150}[.!?\n])",
        r"(?:(?:utilize|use|partner with|rely on|contract with|ship via)\s+(?:commercial|outside|common|freight)?\s*carriers?[^.!?\n]{0,150}[.!?\n])",
        r"(?:(?:carrier|motor carrier|trucking company)\s+(?:requirements|onboarding|compliance|portal|packet|setup|registration)[^.!?\n]{0,150}[.!?\n])",
        r"(?:(?:fob|freight terms|shipping instructions|routing guide|delivery schedule|pickup policy)[^.!?\n]{0,150}[.!?\n])",
    ]

    broker_patterns = [
        r"(?:(?:freight brokers?|brokerage|3pl|third party logistics|logistics providers?)[^.!?\n]{0,150}[.!?\n])",
        r"(?:(?:direct only|asset carriers? only|no brokers?|brokers? welcome|work with brokers?)[^.!?\n]{0,150}[.!?\n])",
    ]

    fleet_patterns = [
        r"(?:(?:our (?:own )?(?:fleet|trucks|tractors|trailers)|company drivers|private fleet|in-house delivery|in house fleet)[^.!?\n]{0,150}[.!?\n])",
        r"(?:(?:fleet of|operates? a fleet of)\s+\d+[^.!?\n]{0,150}[.!?\n])",
    ]

    logistics_contacts = [
        r"(?:(?:shipping|receiving|traffic|logistics|transportation|dispatch|plant|operations|sales)\s+(?:manager|director|coordinator|supervisor|lead|specialist|contact|department)[^.!?\n]{0,150}[.!?\n])",
    ]

    carrier_snips = []
    for pat in carrier_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            carrier_snips.append({"url": page_url, "snippet": m.group(0).strip()})

    broker_snips = []
    for pat in broker_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            broker_snips.append({"url": page_url, "snippet": m.group(0).strip()})

    fleet_snips = []
    for pat in fleet_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            fleet_snips.append({"url": page_url, "snippet": m.group(0).strip()})

    contact_snips = []
    for pat in logistics_contacts:
        for m in re.finditer(pat, text, re.IGNORECASE):
            contact_snips.append({"url": page_url, "snippet": m.group(0).strip()})

    # Phone and email extraction
    raw_emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    valid_emails = [e for e in set(raw_emails) if not any(e.lower().endswith(x) for x in [".png", ".jpg", ".gif", ".webp", ".svg", ".css", ".js"]) and len(e) < 50]

    raw_phones = re.findall(r"(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)

    return {
        "carrier_snippets": carrier_snips[:10],
        "broker_snippets": broker_snips[:10],
        "fleet_snippets": fleet_snips[:10],
        "contact_snippets": contact_snips[:10],
        "emails": sorted(list(valid_emails)),
        "phones": sorted(list(set(raw_phones))),
    }


async def research_single_company(company_meta: dict) -> dict:
    cid = company_meta["company_id"]
    pos = company_meta["campaign_position"]
    brand = company_meta["operating_brand"]
    web_url = company_meta.get("official_website") or ""

    print(f"[{pos:02d}] Crawling CID {cid:3d} ({brand}) at {web_url}...")

    company_provenance = []
    evidence_gathered = {
        "carrier_snippets": [],
        "broker_snippets": [],
        "fleet_snippets": [],
        "contact_snippets": [],
        "emails": set(),
        "phones": set(),
    }

    if not web_url or not web_url.startswith("http"):
        # Document inaccessible
        company_provenance.append({
            "attempted_url": web_url or "NONE",
            "requested_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "http_status": None,
            "final_url": web_url or "NONE",
            "dns_status": "FAILED",
            "access_status": "INACCESSIBLE",
            "content_type": None,
            "response_length": 0,
            "page_title": None,
            "content_sha256": None,
            "result": "INSUFFICIENT_PUBLIC_EVIDENCE",
        })
        return {
            "company_id": cid,
            "campaign_position": pos,
            "operating_brand": brand,
            "website_url": web_url,
            "provenance_records": company_provenance,
            "pages_checked_count": 0,
            "evidence": {k: list(v) if isinstance(v, set) else v for k, v in evidence_gathered.items()},
        }

    parsed = urlparse(web_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    # Build queue of URLs to test
    urls_to_try = [web_url]
    for sub in COMMON_SUBPAGES[1:]:
        u = urljoin(root, sub)
        if u not in urls_to_try:
            urls_to_try.append(u)

    async with httpx.AsyncClient(headers=HEADERS, verify=False, follow_redirects=True) as client:
        # Step 1: fetch home & primary subpages
        for u in urls_to_try:
            res = await fetch_page(client, u)
            prov = {k: v for k, v in res.items() if k not in ("text", "internal_links")}
            company_provenance.append(prov)

            if res["result"] == "SUCCESS_FETCHED" and len(res["text"]) > 80:
                ev = extract_evidence(res["text"], res["final_url"])
                evidence_gathered["carrier_snippets"].extend(ev["carrier_snippets"])
                evidence_gathered["broker_snippets"].extend(ev["broker_snippets"])
                evidence_gathered["fleet_snippets"].extend(ev["fleet_snippets"])
                evidence_gathered["contact_snippets"].extend(ev["contact_snippets"])
                evidence_gathered["emails"].update(ev["emails"])
                evidence_gathered["phones"].update(ev["phones"])

                # If found relevant internal links that aren't already tested, try them
                for il in res["internal_links"]:
                    if il not in [p["attempted_url"] for p in company_provenance]:
                        sub_res = await fetch_page(client, il)
                        sub_prov = {k: v for k, v in sub_res.items() if k not in ("text", "internal_links")}
                        company_provenance.append(sub_prov)
                        if sub_res["result"] == "SUCCESS_FETCHED" and len(sub_res["text"]) > 80:
                            sub_ev = extract_evidence(sub_res["text"], sub_res["final_url"])
                            evidence_gathered["carrier_snippets"].extend(sub_ev["carrier_snippets"])
                            evidence_gathered["broker_snippets"].extend(sub_ev["broker_snippets"])
                            evidence_gathered["fleet_snippets"].extend(sub_ev["fleet_snippets"])
                            evidence_gathered["contact_snippets"].extend(sub_ev["contact_snippets"])
                            evidence_gathered["emails"].update(sub_ev["emails"])
                            evidence_gathered["phones"].update(sub_ev["phones"])

    # Ensure at least one provenance record exists
    if not company_provenance:
        company_provenance.append({
            "attempted_url": web_url,
            "requested_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "http_status": None,
            "final_url": web_url,
            "dns_status": "FAILED",
            "access_status": "INACCESSIBLE",
            "content_type": None,
            "response_length": 0,
            "page_title": None,
            "content_sha256": None,
            "result": "INSUFFICIENT_PUBLIC_EVIDENCE",
        })

    success_pages = [p["final_url"] for p in company_provenance if p["result"] == "SUCCESS_FETCHED"]

    return {
        "company_id": cid,
        "campaign_position": pos,
        "operating_brand": brand,
        "website_url": web_url,
        "provenance_records": company_provenance,
        "pages_checked_count": len(company_provenance),
        "successful_pages_count": len(success_pages),
        "evidence": {
            "carrier_snippets": evidence_gathered["carrier_snippets"][:10],
            "broker_snippets": evidence_gathered["broker_snippets"][:10],
            "fleet_snippets": evidence_gathered["fleet_snippets"][:10],
            "contact_snippets": evidence_gathered["contact_snippets"][:10],
            "emails": sorted(list(evidence_gathered["emails"])),
            "phones": sorted(list(evidence_gathered["phones"])),
        }
    }


async def main():
    wave_letter = sys.argv[1].upper() if len(sys.argv) > 1 else "A"
    roster_path = Path("reports/tier_a_acceleration_phase_a_roster.json")
    with open(roster_path, "r", encoding="utf-8") as f:
        roster = json.load(f)

    wave_targets = [r for r in roster if r["wave"] == wave_letter]
    print(f"=== Starting Wave {wave_letter} Crawler: {len(wave_targets)} companies ===")

    # Process in batches of 5 concurrent companies
    all_results = []
    chunk_size = 5
    for i in range(0, len(wave_targets), chunk_size):
        chunk = wave_targets[i:i+chunk_size]
        print(f"--- Chunk {(i//chunk_size)+1}: Positions {chunk[0]['campaign_position']} to {chunk[-1]['campaign_position']} ---")
        chunk_res = await asyncio.gather(*[research_single_company(c) for c in chunk])
        all_results.extend(chunk_res)

    out_file = Path(f"reports/tier_a_phase_a_wave_{wave_letter}_crawler_raw.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    total_prov = sum(len(r["provenance_records"]) for r in all_results)
    print(f"\n[DONE] Saved {len(all_results)} companies with {total_prov} total provenance attempts to {out_file}.")


if __name__ == "__main__":
    asyncio.run(main())
