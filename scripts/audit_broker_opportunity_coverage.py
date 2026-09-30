"""
Script to audit broker opportunity coverage across all 565 operating companies
and 653 facilities in data/prospects.db.
"""

import sqlite3
from collections import Counter
from pathlib import Path

DB_PATH = Path("data/prospects.db")

def run_audit():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Total counts
    total_companies = cursor.execute("SELECT count(*) FROM companies").fetchone()[0]
    total_facilities = cursor.execute("SELECT count(*) FROM facilities").fetchone()[0]
    operating_companies = cursor.execute("SELECT count(DISTINCT company_id) FROM facilities").fetchone()[0]

    print(f"Total Companies: {total_companies}")
    print(f"Operating Companies: {operating_companies}")
    print(f"Total Facilities: {total_facilities}")

    # Facilities breakdown
    print("\n--- FACILITY-LEVEL DISTRIBUTIONS (653 facilities) ---")
    
    # private_fleet_present
    fleet_fac = cursor.execute("SELECT private_fleet_present, count(*) FROM facilities GROUP BY private_fleet_present").fetchall()
    print("private_fleet_present (facilities):")
    for r in fleet_fac:
        print(f"  {r[0]}: {r[1]}")

    # fleet_relationship_type
    rel_fac = cursor.execute("SELECT fleet_relationship_type, count(*) FROM facilities GROUP BY fleet_relationship_type").fetchall()
    print("fleet_relationship_type (facilities):")
    for r in rel_fac:
        print(f"  {r[0]}: {r[1]}")

    # commercial_carrier_use
    carrier_fac = cursor.execute("SELECT commercial_carrier_use, count(*) FROM facilities GROUP BY commercial_carrier_use").fetchall()
    print("commercial_carrier_use (facilities):")
    for r in carrier_fac:
        print(f"  {r[0]}: {r[1]}")

    # broker_friendly_status
    broker_fac = cursor.execute("SELECT broker_friendly_status, count(*) FROM facilities GROUP BY broker_friendly_status").fetchall()
    print("broker_friendly_status (facilities):")
    for r in broker_fac:
        print(f"  {r[0]}: {r[1]}")

    # freight_procurement_level
    proc_fac = cursor.execute("SELECT freight_procurement_level, count(*) FROM facilities GROUP BY freight_procurement_level").fetchall()
    print("freight_procurement_level (facilities):")
    for r in proc_fac:
        print(f"  {r[0]}: {r[1]}")

    # 2. Company-level analysis
    # For each operating company, examine aggregate/max values across its facilities
    print("\n--- COMPANY-LEVEL DISTRIBUTIONS (565 operating companies) ---")
    
    companies = cursor.execute("""
        SELECT c.id, c.operating_brand, c.legal_name,
               count(f.id) as fac_count
        FROM companies c
        JOIN facilities f ON c.id = f.company_id
        GROUP BY c.id
        ORDER BY c.id
    """).fetchall()

    comp_fleet = Counter()
    comp_fleet_rel = Counter()
    comp_carrier = Counter()
    comp_broker = Counter()
    comp_direct_contact = Counter()
    comp_callable_route = Counter()
    comp_crosstab = Counter()

    for comp in companies:
        cid = comp["id"]
        
        # Facilities for this company
        facs = cursor.execute("""
            SELECT id, private_fleet_present, fleet_relationship_type,
                   commercial_carrier_use, broker_friendly_status, freight_procurement_level
            FROM facilities
            WHERE company_id = ?
        """, (cid,)).fetchall()

        # Company-level private_fleet:
        # If any facility has VERIFIED_PRESENT -> VERIFIED_PRESENT
        # Else if any VERIFIED_NO_FLEET and no VERIFIED_PRESENT -> VERIFIED_NO_FLEET
        # Else -> UNKNOWN
        fleet_statuses = {f["private_fleet_present"] for f in facs}
        if "VERIFIED_PRESENT" in fleet_statuses:
            c_fleet = "VERIFIED_PRESENT"
        elif "VERIFIED_NO_FLEET" in fleet_statuses:
            c_fleet = "VERIFIED_NO_FLEET"
        else:
            c_fleet = "UNKNOWN"
        comp_fleet[c_fleet] += 1

        # Fleet relationship type
        rel_statuses = {f["fleet_relationship_type"] for f in facs if f["fleet_relationship_type"] != "UNKNOWN"}
        if rel_statuses:
            c_rel = list(rel_statuses)[0] if len(rel_statuses) == 1 else "MIXED"
        else:
            c_rel = "UNKNOWN"
        comp_fleet_rel[c_rel] += 1

        # Commercial carrier use
        carrier_statuses = {f["commercial_carrier_use"] for f in facs}
        if "VERIFIED" in carrier_statuses:
            c_carrier = "VERIFIED"
        else:
            c_carrier = "UNKNOWN"
        comp_carrier[c_carrier] += 1

        # Broker friendly status
        broker_statuses = {f["broker_friendly_status"] for f in facs}
        if "VERIFIED_ACCEPTS" in broker_statuses:
            c_broker = "VERIFIED_ACCEPTS"
        elif "VERIFIED_DIRECT_ONLY" in broker_statuses:
            c_broker = "VERIFIED_DIRECT_ONLY"
        else:
            c_broker = "UNKNOWN"
        comp_broker[c_broker] += 1

        # Contacts for this company or its facilities
        contacts = cursor.execute("""
            SELECT id, role_category, phone_directness, phone_number, email_address,
                   outbound_shipping_procurement_relevance
            FROM contacts
            WHERE company_id = ? OR facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
        """, (cid, cid)).fetchall()

        # Direct freight/logistics contact
        has_direct_freight = any(
            c["role_category"] == "FREIGHT_LOGISTICS" or 
            c["outbound_shipping_procurement_relevance"] in ("VERIFIED", "INFERRED")
            for c in contacts
        )
        comp_direct_contact["YES" if has_direct_freight else "NO"] += 1

        # Callable outreach route (valid phone or email)
        has_callable = any(
            (c["phone_number"] is not None and len(c["phone_number"].strip()) > 0) or
            (c["email_address"] is not None and len(c["email_address"].strip()) > 0)
            for c in contacts
        )
        comp_callable_route["YES" if has_callable else "NO"] += 1

        # Cross-tabs: fleet + carrier
        comp_crosstab[(c_fleet, c_carrier)] += 1

    print("private_fleet_present (companies):")
    for k, v in comp_fleet.most_common():
        print(f"  {k}: {v}")

    print("\nfleet_relationship_type (companies):")
    for k, v in comp_fleet_rel.most_common():
        print(f"  {k}: {v}")

    print("\ncommercial_carrier_use (companies):")
    for k, v in comp_carrier.most_common():
        print(f"  {k}: {v}")

    print("\nbroker_friendly_status (companies):")
    for k, v in comp_broker.most_common():
        print(f"  {k}: {v}")

    print("\nDirect freight/logistics contact (companies):")
    for k, v in comp_direct_contact.most_common():
        print(f"  {k}: {v}")

    print("\nCallable outreach route (companies):")
    for k, v in comp_callable_route.most_common():
        print(f"  {k}: {v}")

    print("\n--- CROSS-TABS: Private Fleet x Commercial Carrier Use (565 companies) ---")
    for (flt, car), cnt in sorted(comp_crosstab.items()):
        print(f"  Fleet={flt} + Carrier={car}: {cnt}")

    # Also check suppressions in DB
    print("\n--- SUPPRESSIONS IN DB ---")
    suppressions = cursor.execute("SELECT * FROM suppressions").fetchall()
    print(f"Total suppressions: {len(suppressions)}")
    for s in suppressions:
        print(f"  ID={s['id']}, Scope={s['scope_type']}, CoID={s['company_id']}, FacID={s['facility_id']}, Status={s['suppression_status']}, Reason={s['reason_notes']}")

    conn.close()

if __name__ == "__main__":
    run_audit()
