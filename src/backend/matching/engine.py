"""
Deterministic Load-to-Capacity Matching Engine
Shipper IQ V1 — Production Carrier Network

Zero opaque AI/ML. 100% deterministic, explainable, and testable.
UNKNOWN values contribute 0 points (strictly neutral).
Hard exclusions strictly eliminate invalid, unsafe, or suppressed candidates.
"""

from datetime import datetime, date, timezone
import math
from typing import Any, Dict, List, Optional, Tuple
import sqlite3

# Equipment Compatibility Matrix
# Primary equipment in V1: FLATBED, STEP_DECK, DRY_VAN
EQUIPMENT_TYPES = {"FLATBED", "STEP_DECK", "DRY_VAN"}


def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Deterministic calculation of great-circle distance between two points on Earth in miles.
    """
    R = 3958.8  # Earth radius in miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 1)


def is_cross_border_lane(origin_country: Optional[str], dest_country: Optional[str]) -> bool:
    """Check if lane crosses US-Canada international border."""
    if not origin_country or not dest_country:
        return False
    return (origin_country.upper() == "US" and dest_country.upper() == "CA") or \
           (origin_country.upper() == "CA" and dest_country.upper() == "US")


def check_hard_exclusions(
    load: Dict[str, Any],
    carrier: Dict[str, Any],
    capacity: Dict[str, Any],
    suppressions: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """
    Evaluates hard exclusion conditions.
    Returns (True, None) if candidate passes all checks, or (False, reason) if blocked.
    """
    # 1. Authority Status: Hard block if known out of service or unauthorized
    op_status = (carrier.get("operating_status") or "").upper()
    if op_status in ("VERIFIED_OUT_OF_SERVICE", "VERIFIED_NOT_AUTHORIZED"):
        return False, f"Carrier authority is not active: {op_status}"

    # 2. Capacity Status / Expiry: Stale/Expired capacity cannot be matched as live
    cap_status = (capacity.get("capacity_status") or "").upper()
    if cap_status in ("EXPIRED", "WITHDRAWN"):
        return False, f"Capacity posting is no longer active: {cap_status}"

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    avail_end = capacity.get("available_date_end") or capacity.get("available_date_start")
    if avail_end and str(avail_end)[:10] < now_iso:
        return False, "Capacity posting availability date has passed"

    # 3. Equipment Compatibility
    load_equip = (load.get("equipment_required") or "").upper()
    cap_equip = (capacity.get("equipment_type") or "").upper()
    if load_equip and cap_equip:
        # Step deck can often haul flatbed cargo, but dry van cannot haul flatbed, etc.
        if load_equip != cap_equip:
            # Step deck allowed for flatbed only if explicitly compatible; otherwise hard mismatch
            if not (load_equip == "FLATBED" and cap_equip == "STEP_DECK"):
                return False, f"Equipment mismatch: Load requires {load_equip}, truck has {cap_equip}"

    # 4. Pickup Date Window Overlap
    load_pickup_early = str(load.get("pickup_date_earliest") or "")[:10]
    load_pickup_late = str(load.get("pickup_date_latest") or load_pickup_early)[:10]
    cap_start = str(capacity.get("available_date_start") or "")[:10]
    cap_end = str(capacity.get("available_date_end") or cap_start)[:10]

    if load_pickup_early and cap_end and cap_end < load_pickup_early:
        return False, f"Capacity ends ({cap_end}) before earliest pickup ({load_pickup_early})"
    if load_pickup_late and cap_start and cap_start > load_pickup_late:
        return False, f"Capacity becomes available ({cap_start}) after latest pickup ({load_pickup_late})"

    # 5. Cross-Border Requirement Conflict
    load_orig_country = (load.get("origin_country") or "").upper()
    load_dest_country = (load.get("dest_country") or "").upper()
    cross_border = is_cross_border_lane(load_orig_country, load_dest_country)

    carrier_cb = (carrier.get("cross_border_capability") or "UNKNOWN").upper()
    if cross_border:
        if carrier_cb in ("US_ONLY", "CANADA_ONLY"):
            return False, f"Load is cross-border, but carrier is restricted to {carrier_cb}"
        if load_orig_country == "US" and carrier_cb == "CANADA_ONLY":
            return False, "Load originates in US, carrier is Canada-only"
        if load_orig_country == "CA" and carrier_cb == "US_ONLY":
            return False, "Load originates in Canada, carrier is US-only"

    # 6. Suppression Checks
    for sup in suppressions:
        scope = sup.get("scope_type")
        status = sup.get("suppression_status")
        if status in ("DO_NOT_CONTACT", "DO_NOT_USE"):
            if scope == "CARRIER" and sup.get("carrier_id") == carrier.get("id"):
                return False, f"Carrier is suppressed: {sup.get('reason_notes')}"
            if scope == "LANE":
                sup_orig = (sup.get("origin_state_prov") or "").upper()
                sup_dest = (sup.get("dest_state_prov") or "").upper()
                load_orig_state = (load.get("origin_state_prov") or "").upper()
                load_dest_state = (load.get("dest_state_prov") or "").upper()
                if sup_orig == load_orig_state and sup_dest == load_dest_state:
                    return False, f"Lane {sup_orig} → {sup_dest} is suppressed: {sup.get('reason_notes')}"

    return True, None


def evaluate_match_score(
    load: Dict[str, Any],
    carrier: Dict[str, Any],
    capacity: Dict[str, Any],
    carrier_lanes: List[Dict[str, Any]],
    quotes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Deterministic scoring and explanation builder.
    Base points max: 100
    - Exact equipment fit: 25 pts
    - Origin location fit: up to 25 pts
    - Destination / Preferred lane fit: up to 20 pts
    - Pickup timing overlap: 15 pts
    - Authority verified active: 10 pts
    - Capacity freshness: 5 pts
    - Rate fit bonus: up to 10 pts (if both known)
    - UNKNOWN values contribute 0 pts (NEVER negative).
    """
    score = 0
    max_score = 100
    explanations: List[Dict[str, str]] = []

    # 1. Equipment Fit
    load_equip = (load.get("equipment_required") or "").upper()
    cap_equip = (capacity.get("equipment_type") or "").upper()
    if load_equip and cap_equip:
        if load_equip == cap_equip:
            score += 25
            explanations.append({"type": "positive", "text": f"{cap_equip} exact equipment match (+25)"})
        elif load_equip == "FLATBED" and cap_equip == "STEP_DECK":
            score += 15
            explanations.append({"type": "positive", "text": "Step Deck suitable for Flatbed freight (+15)"})
    else:
        explanations.append({"type": "neutral", "text": "Equipment requirements partially unconfirmed (0)"})

    # 2. Origin Proximity / Geography
    load_lat = load.get("origin_latitude")
    load_lon = load.get("origin_longitude")
    cap_lat = capacity.get("origin_latitude")
    cap_lon = capacity.get("origin_longitude")

    load_city = (load.get("origin_city") or "").strip().upper()
    load_state = (load.get("origin_state_prov") or "").strip().upper()
    cap_city = (capacity.get("available_city") or "").strip().upper()
    cap_state = (capacity.get("available_state_prov") or "").strip().upper()

    if load_lat is not None and load_lon is not None and cap_lat is not None and cap_lon is not None:
        dist = haversine_distance_miles(float(load_lat), float(load_lon), float(cap_lat), float(cap_lon))
        if dist <= 50:
            score += 25
            explanations.append({"type": "positive", "text": f"Capacity within {dist} miles of pickup (+25)"})
        elif dist <= 125:
            score += 20
            explanations.append({"type": "positive", "text": f"Capacity within {dist} miles of pickup (+20)"})
        elif dist <= 250:
            score += 12
            explanations.append({"type": "positive", "text": f"Capacity within {dist} miles of pickup (+12)"})
        else:
            score += 5
            explanations.append({"type": "neutral", "text": f"Capacity is {dist} miles from pickup (+5)"})
    else:
        # Fallback to city/state/region matching
        if load_city and cap_city and load_city == cap_city and load_state == cap_state:
            score += 25
            explanations.append({"type": "positive", "text": f"Available in {capacity.get('available_city')}, {cap_state} (same city as pickup) (+25)"})
        elif load_state and cap_state and load_state == cap_state:
            score += 18
            explanations.append({"type": "positive", "text": f"Available in {cap_state} (same state/province as pickup) (+18)"})
        else:
            load_country = (load.get("origin_country") or "").upper()
            cap_country = (capacity.get("available_country") or "").upper()
            if load_country and cap_country and load_country == cap_country:
                score += 5
                explanations.append({"type": "neutral", "text": f"Available in same domestic country ({cap_country}) (+5)"})
            else:
                explanations.append({"type": "neutral", "text": "Origin distance approximate based on regional coverage (0)"})

    # 3. Destination / Preferred Lane Match
    load_dest_state = (load.get("dest_state_prov") or "").strip().upper()
    load_dest_city = (load.get("dest_city") or "").strip().upper()
    cap_dest_state = (capacity.get("destination_state_prov") or "").strip().upper()
    cap_dest_city = (capacity.get("destination_city") or "").strip().upper()

    dest_matched = False
    if cap_dest_state and load_dest_state and cap_dest_state == load_dest_state:
        if cap_dest_city and load_dest_city and cap_dest_city == load_dest_city:
            score += 20
            explanations.append({"type": "positive", "text": f"Capacity destination matches load destination: {capacity.get('destination_city')}, {cap_dest_state} (+20)"})
        else:
            score += 15
            explanations.append({"type": "positive", "text": f"Capacity destination matches load destination state: {cap_dest_state} (+15)"})
        dest_matched = True

    if not dest_matched:
        # Check carrier preferred/recurring lanes
        for lane in carrier_lanes:
            lane_dest = (lane.get("dest_region") or "").strip().upper()
            lane_orig = (lane.get("origin_region") or "").strip().upper()
            if lane_dest and load_dest_state and lane_dest == load_dest_state:
                if lane_orig and load_state and lane_orig == load_state:
                    score += 20
                    explanations.append({"type": "positive", "text": f"Lane matches carrier preferred lane: {lane_orig} → {lane_dest} (+20)"})
                    dest_matched = True
                    break
                else:
                    score += 10
                    explanations.append({"type": "positive", "text": f"Destination matches carrier preferred destination region: {lane_dest} (+10)"})
                    dest_matched = True
                    break

    if not dest_matched:
        if not cap_dest_state and not carrier_lanes:
            explanations.append({"type": "neutral", "text": "Carrier has open destination / no lane preference recorded (0)"})
        else:
            explanations.append({"type": "neutral", "text": "No explicit destination lane preference overlap recorded (0)"})

    # 4. Pickup Timing Overlap
    load_pickup_early = str(load.get("pickup_date_earliest") or "")[:10]
    cap_start = str(capacity.get("available_date_start") or "")[:10]
    cap_end = str(capacity.get("available_date_end") or cap_start)[:10]

    if load_pickup_early and cap_start:
        if cap_start <= load_pickup_early <= cap_end:
            score += 15
            explanations.append({"type": "positive", "text": f"Available on pickup date {load_pickup_early} (+15)"})
        else:
            score += 10
            explanations.append({"type": "positive", "text": f"Availability window ({cap_start} to {cap_end}) covers pickup window (+10)"})
    else:
        explanations.append({"type": "neutral", "text": "Timing compatibility based on general availability (0)"})

    # 5. Verified Authority
    op_status = (carrier.get("operating_status") or "").upper()
    if op_status == "VERIFIED_AUTHORIZED":
        score += 10
        explanations.append({"type": "positive", "text": "Active carrier operating authority verified with FMCSA (+10)"})
    else:
        explanations.append({"type": "neutral", "text": f"Operating authority status: {op_status or 'UNKNOWN'} (0)"})

    # 6. Capacity Freshness
    observed_at = capacity.get("observed_at") or capacity.get("created_at")
    if observed_at:
        try:
            obs_dt = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
            hours_old = (datetime.now(timezone.utc) - obs_dt).total_seconds() / 3600.0
            if hours_old <= 24:
                score += 5
                explanations.append({"type": "positive", "text": f"Capacity refreshed recently ({int(hours_old)}h ago) (+5)"})
            elif hours_old <= 72:
                score += 3
                explanations.append({"type": "positive", "text": "Capacity active and observed within 3 days (+3)"})
        except Exception:
            pass

    # 7. Commercial Rate Fit (Honest comparison: only when both are known)
    load_target_cost = load.get("carrier_target_cost")
    # check latest quote or desired rate
    carrier_desired = capacity.get("desired_rate")
    latest_quote = quotes[0].get("quoted_amount") if quotes else None
    effective_rate = latest_quote or carrier_desired

    if load_target_cost is not None and effective_rate is not None:
        try:
            target = float(load_target_cost)
            rate = float(effective_rate)
            if rate <= target:
                score += 10
                explanations.append({"type": "positive", "text": f"Carrier rate (${rate:,.2f}) within target cost (${target:,.2f}) (+10)"})
            elif rate <= target * 1.08:
                score += 5
                explanations.append({"type": "positive", "text": f"Carrier rate (${rate:,.2f}) within 8% of target cost (${target:,.2f}) (+5)"})
            else:
                explanations.append({"type": "neutral", "text": f"Carrier rate (${rate:,.2f}) exceeds target cost (${target:,.2f}) (0)"})
        except (ValueError, TypeError):
            explanations.append({"type": "neutral", "text": "Rate information format unverified (0)"})
    else:
        explanations.append({"type": "neutral", "text": "Rate comparison pending quote (neutral 0)"})

    normalized_score = min(max_score, score)

    return {
        "score_percent": normalized_score,
        "raw_points": score,
        "max_points": max_score,
        "explanations": explanations,
    }
