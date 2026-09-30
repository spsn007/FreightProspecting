import sqlite3
from collections import Counter
from pathlib import Path

DB_PATH = Path("data/prospects.db")

def evaluate_company_tier(comp_id, conn):
    cursor = conn.cursor()
    
    # 1. Check company suppressions
    supp = cursor.execute("""
        SELECT scope_type, suppression_status, reason_notes
        FROM suppressions
        WHERE (scope_type = 'COMPANY' AND company_id = ?)
    """, (comp_id,)).fetchall()
    for s in supp:
        if s[1] == 'DO_NOT_CONTACT':
            return {
                "tier": "RESTRICTED",
                "frontend_label": "Restricted",
                "reason_code": "DO_NOT_CONTACT",
                "positive_facts": [],
                "counter_factors": ["Company marked Do Not Contact"],
                "unknowns": []
            }

    # 2. Check facilities
    facs = cursor.execute("""
        SELECT f.id, f.facility_name, f.city, f.state_prov, f.country,
               f.private_fleet_present, f.fleet_relationship_type,
               f.commercial_carrier_use, f.broker_friendly_status,
               f.freight_procurement_level,
               pl.stage
        FROM facilities f
        LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE f.company_id = ?
    """, (comp_id,)).fetchall()

    if not facs:
        return {
            "tier": "RESTRICTED",
            "frontend_label": "Restricted",
            "reason_code": "NO_OPERATING_FACILITIES",
            "positive_facts": [],
            "counter_factors": ["No operating facilities found"],
            "unknowns": []
        }

    # Check direct-only policy across facilities
    if any(f[8] == 'VERIFIED_DIRECT_ONLY' for f in facs):
        return {
            "tier": "RESTRICTED",
            "frontend_label": "Restricted",
            "reason_code": "DIRECT_ONLY_POLICY",
            "positive_facts": [],
            "counter_factors": ["Verified direct-only procurement policy (does not use brokers)"],
            "unknowns": []
        }

    # Contacts check for company and facilities
    contacts = cursor.execute("""
        SELECT id, person_name, phone_number, email_address, role_category, phone_directness
        FROM contacts
        WHERE company_id = ? OR facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
    """, (comp_id, comp_id)).fetchall()

    has_callable = any(
        (c[2] and c[2].strip()) or (c[3] and c[3].strip())
        for c in contacts
    )

    # Commodities check
    comms = cursor.execute("""
        SELECT fc.equipment_category
        FROM facility_commodities fc
        JOIN facilities f ON fc.facility_id = f.id
        WHERE f.company_id = ?
    """, (comp_id,)).fetchall()
    has_ftl = any(c[0] in ('FLATBED', 'STEP_DECK', 'DRY_VAN') for c in comms)

    # Stages across facilities
    stages = {f[10] for f in facs if f[10]}
    is_ready_to_contact = bool(stages & {'SHORTLISTED', 'QUALIFIED'})
    is_all_discovery = stages == {'DISCOVERY'}

    # Fleet & carrier flags
    has_carrier_verified = any(f[7] == 'VERIFIED' for f in facs)
    has_broker_verified = any(f[8] == 'VERIFIED_ACCEPTS' for f in facs)
    has_fleet_verified = any(f[5] == 'VERIFIED_PRESENT' for f in facs)

    # Opportunity vs Readiness logic:
    # If no callable contact route, cannot be Tier A or B
    if not has_callable:
        return {
            "tier": "TIER_D_RESEARCH_NEEDED",
            "frontend_label": "Needs More Research",
            "reason_code": "NO_CALLABLE_ROUTE",
            "positive_facts": ["FTL freight profile exists"] if has_ftl else [],
            "counter_factors": ["No callable phone or email contact route available"],
            "unknowns": ["Direct contact route unconfirmed"]
        }

    # If carrier use verified or broker verified
    if has_carrier_verified or has_broker_verified:
        if is_ready_to_contact:
            # TIER A: Priority Prospect!
            pos = []
            if has_broker_verified:
                pos.append("Broker acceptance explicitly confirmed (VERIFIED)")
            if has_carrier_verified:
                pos.append("Outside carrier use confirmed (VERIFIED)")
            if has_fleet_verified:
                pos.append("Own trucks confirmed (competing asset capacity noted, but outside carrier use proves outsourced freight exists)")
            pos.append("Callable outreach route verified")
            if has_ftl:
                pos.append("Target FTL equipment fit")
            
            unk = []
            if not has_broker_verified:
                unk.append("Broker use not confirmed")
            if not has_fleet_verified:
                unk.append("Own trucks not confirmed")

            return {
                "tier": "TIER_A_PRIORITY",
                "frontend_label": "Priority Prospect",
                "reason_code": "VERIFIED_CARRIER_USE_READY",
                "positive_facts": pos,
                "counter_factors": [],
                "unknowns": unk
            }
        else:
            # Carrier use verified but in Discovery pool (research incomplete)
            return {
                "tier": "TIER_D_RESEARCH_NEEDED",
                "frontend_label": "Needs More Research",
                "reason_code": "STRONG_SIGNAL_RESEARCH_INCOMPLETE",
                "positive_facts": ["Outside carrier use confirmed (VERIFIED)", "Callable outreach route verified"],
                "counter_factors": ["Research incomplete (in Discovery pool / Pending evidence verification)"],
                "unknowns": ["Broker use not confirmed", "Audited evidence verification pending"]
            }

    # If in Discovery pool and no carrier use verified -> TIER D
    if is_all_discovery:
        return {
            "tier": "TIER_D_RESEARCH_NEEDED",
            "frontend_label": "Needs More Research",
            "reason_code": "DISCOVERY_POOL_RESEARCH_INCOMPLETE",
            "positive_facts": ["Operating facility verified in US/Canada", "FTL equipment fit"],
            "counter_factors": ["Research incomplete in Discovery pool"],
            "unknowns": ["Own trucks not confirmed", "Outside carrier use not confirmed", "Broker use not confirmed"]
        }

    # Now we are in Ready to Contact (SHORTLISTED or QUALIFIED) without verified carrier use
    if has_fleet_verified:
        # TIER C: Secondary Prospect
        pos = ["Target FTL equipment fit", "Callable outreach route verified"]
        cntr = ["Own trucks confirmed", "Use of outside carriers not confirmed"]
        unk = ["Outside carrier use not confirmed", "Broker use not confirmed"]
        return {
            "tier": "TIER_C_SECONDARY",
            "frontend_label": "Secondary Prospect",
            "reason_code": "PRIVATE_FLEET_CARRIER_UNKNOWN",
            "positive_facts": pos,
            "counter_factors": cntr,
            "unknowns": unk
        }
    else:
        # TIER B: Worth Calling
        pos = ["Target FTL equipment fit", "Callable outreach route verified"]
        unk = ["Own trucks not confirmed", "Outside carrier use not confirmed", "Broker use not confirmed"]
        return {
            "tier": "TIER_B_WORTH_CALLING",
            "frontend_label": "Worth Calling",
            "reason_code": "CALLABLE_OPPORTUNITY_UNCONFIRMED",
            "positive_facts": pos,
            "counter_factors": [],
            "unknowns": unk
        }

def run():
    conn = sqlite3.connect(DB_PATH)
    comps = conn.execute("SELECT id, operating_brand FROM companies WHERE id IN (SELECT DISTINCT company_id FROM facilities) ORDER BY id").fetchall()
    
    tier_counts = Counter()
    results = []
    for cid, brand in comps:
        res = evaluate_company_tier(cid, conn)
        tier_counts[res["tier"]] += 1
        results.append((cid, brand, res))

    print(f"Evaluated {len(comps)} operating companies:")
    for tier, cnt in tier_counts.most_common():
        print(f"  {tier}: {cnt}")

    conn.close()

if __name__ == "__main__":
    run()
