import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

def normalize_name(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\b(inc|corp|corporation|llc|ltd|co|company|group|holdings|enterprises|sawmill|lumber|forest|products|steel|metals|precast|concrete)\b", "", text)
    return re.sub(r"[^a-z0-9]", "", text)

def normalize_domain(url: str) -> str:
    if not url:
        return ""
    url = url.lower().strip()
    dom = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].split(":")[0]
    return dom

def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"[^0-9]", "", phone)
    return digits[-10:] if len(digits) >= 10 else digits

class CandidateValidator:
    def __init__(self, lookup_path: Path = Path("data/existing_lookup.json")):
        with open(lookup_path, "r", encoding="utf-8") as f:
            self.lookup = json.load(f)

        self.existing_normalized_brands: Set[str] = set(self.lookup.get("normalized_brands", []))
        self.existing_addresses: Set[str] = set(self.lookup.get("addresses", []))
        self.existing_phones: Set[str] = set(self.lookup.get("phones", []))
        self.existing_domains: Set[str] = set(self.lookup.get("domains", []))

        # Dynamic batch tracking
        self.batch_brands: Set[str] = set()
        self.batch_addresses: Set[str] = set()
        self.batch_phones: Set[str] = set()
        self.batch_domains: Set[str] = set()

        self.accepted_candidates: List[Dict[str, Any]] = []
        self.rejected_candidates: List[Tuple[Dict[str, Any], str]] = []

    def validate_and_add(self, c: Dict[str, Any]) -> Tuple[bool, str]:
        brand = (c.get("brand") or "").strip()
        if not brand or len(brand) < 2:
            reason = "Missing or invalid brand name"
            self.rejected_candidates.append((c, reason))
            return False, reason

        fac_name = (c.get("fac_name") or "").strip()
        if not fac_name or len(fac_name) < 2:
            reason = "Missing or invalid facility name"
            self.rejected_candidates.append((c, reason))
            return False, reason

        address = (c.get("address") or "").strip()
        if not address or len(address) < 4:
            reason = "Missing or invalid physical address"
            self.rejected_candidates.append((c, reason))
            return False, reason

        city = (c.get("city") or "").strip()
        state = (c.get("state") or "").strip().upper()
        country = (c.get("country") or "").strip().upper()

        if not city or not state:
            reason = "Missing city or state/province"
            self.rejected_candidates.append((c, reason))
            return False, reason

        if country not in ("US", "CA"):
            reason = f"Country '{country}' outside US/Canada scope"
            self.rejected_candidates.append((c, reason))
            return False, reason

        # Alaska excluded by default in V1
        if state == "AK":
            reason = "Alaska is excluded by default in V1"
            self.rejected_candidates.append((c, reason))
            return False, reason

        # Hawaii excluded
        if state == "HI":
            reason = "Hawaii is hard-excluded"
            self.rejected_candidates.append((c, reason))
            return False, reason

        phone = (c.get("phone") or "").strip()
        email = (c.get("email") or "").strip()
        if not phone and not email:
            reason = "Lacks callable phone route or email"
            self.rejected_candidates.append((c, reason))
            return False, reason

        source_url = (c.get("source_url") or c.get("website_url") or "").strip()
        if not source_url:
            reason = "Missing verification source URL"
            self.rejected_candidates.append((c, reason))
            return False, reason

        # Normalization checks
        norm_brand = normalize_name(brand)
        if norm_brand in self.existing_normalized_brands:
            reason = f"Brand '{brand}' matches existing DB company"
            self.rejected_candidates.append((c, reason))
            return False, reason

        if norm_brand in self.batch_brands:
            reason = f"Brand '{brand}' already added in current batch"
            self.rejected_candidates.append((c, reason))
            return False, reason

        addr_key = f"{address.lower()}|{state.lower()}"
        if addr_key in self.existing_addresses:
            reason = f"Address '{address}, {state}' already exists in DB"
            self.rejected_candidates.append((c, reason))
            return False, reason

        if addr_key in self.batch_addresses:
            reason = f"Address '{address}, {state}' already in current batch"
            self.rejected_candidates.append((c, reason))
            return False, reason

        norm_p = normalize_phone(phone)
        if norm_p and norm_p in self.existing_phones:
            reason = f"Phone '{phone}' matches existing DB contact"
            self.rejected_candidates.append((c, reason))
            return False, reason

        if norm_p and norm_p in self.batch_phones:
            reason = f"Phone '{phone}' duplicate within batch"
            self.rejected_candidates.append((c, reason))
            return False, reason

        dom = normalize_domain(c.get("website_url") or source_url)
        if dom and dom in self.existing_domains:
            reason = f"Domain '{dom}' already exists in DB"
            self.rejected_candidates.append((c, reason))
            return False, reason

        if dom and dom in self.batch_domains:
            reason = f"Domain '{dom}' duplicate within batch"
            self.rejected_candidates.append((c, reason))
            return False, reason

        # Accept candidate
        self.batch_brands.add(norm_brand)
        self.batch_addresses.add(addr_key)
        if norm_p:
            self.batch_phones.add(norm_p)
        if dom:
            self.batch_domains.add(dom)

        self.accepted_candidates.append(c)
        return True, "ACCEPTED"

    def validate_batch(self, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Tuple[Dict[str, Any], str]]]:
        accepted = []
        rejected = []
        for c in candidates:
            ok, reason = self.validate_and_add(c)
            if ok:
                accepted.append(c)
            else:
                rejected.append((c, reason))
        return accepted, rejected

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_accepted": len(self.accepted_candidates),
            "total_rejected": len(self.rejected_candidates),
            "unique_new_brands": len(self.batch_brands),
        }
