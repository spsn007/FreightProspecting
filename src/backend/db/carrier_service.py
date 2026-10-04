"""
Carrier & Capacity Network Service Layer
Shipper IQ V1 — Deterministic Business Logic & Database Queries

Provides clean relational access for:
- Carrier profiles & identity deduplication
- Carrier business contacts (phone directness, verification level)
- Equipment & published capabilities
- Lane preferences & recurring routes
- Available capacity postings & freshness filtering
- Dedicated carrier team ownership & authorization guards
- Append-only carrier outreach history & engagement state
- Preserved carrier quote history
- Distinct carrier suppressions
- Load-to-capacity matching query orchestration
"""

import json
import sqlite3
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from src.backend.matching.engine import (
    check_hard_exclusions,
    evaluate_match_score,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ==============================================================================
# CARRIER IDENTITY & PROFILES
# ==============================================================================

def get_carrier_by_id(conn: sqlite3.Connection, carrier_id: int) -> Optional[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    row = cur.execute("""
        SELECT c.*,
               ca.owner_id,
               tu.username AS owner_username,
               es.current_relationship_status,
               es.attempt_count,
               es.last_contacted_at,
               es.next_callback_at,
               es.last_call_disposition,
               es.last_call_notes
        FROM carriers c
        LEFT JOIN carrier_assignments ca ON ca.carrier_id = c.id
        LEFT JOIN team_users tu ON tu.id = ca.owner_id
        LEFT JOIN carrier_engagement_state es ON es.carrier_id = c.id
        WHERE c.id = ?
    """, (carrier_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("primary_equipment_types"):
        try:
            d["equipment_types_list"] = json.loads(d["primary_equipment_types"])
        except Exception:
            d["equipment_types_list"] = [d["primary_equipment_types"]]
    else:
        d["equipment_types_list"] = []
    return d


def get_carrier_by_usdot(conn: sqlite3.Connection, usdot: str) -> Optional[Dict[str, Any]]:
    clean = str(usdot).strip()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM carriers WHERE usdot_number = ?", (clean,)).fetchone()
    if row:
        return get_carrier_by_id(conn, row["id"])
    return None


def get_carrier_by_mc(conn: sqlite3.Connection, mc: str) -> Optional[Dict[str, Any]]:
    clean = str(mc).strip()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM carriers WHERE mc_number = ?", (clean,)).fetchone()
    if row:
        return get_carrier_by_id(conn, row["id"])
    return None


def create_or_update_carrier(
    conn: sqlite3.Connection,
    data: Dict[str, Any],
    user_id: int,
) -> Dict[str, Any]:
    """
    Creates or updates a carrier with strict deduplication priority:
    1. USDOT number match
    2. MC number match
    3. Legal Name + State match
    """
    cur = conn.cursor()
    usdot = str(data.get("usdot_number") or "").strip() or None
    mc = str(data.get("mc_number") or "").strip() or None
    legal_name = str(data.get("legal_name") or "").strip()
    dba_name = str(data.get("dba_name") or "").strip() or None
    physical_city = str(data.get("physical_city") or "").strip() or None
    physical_state_prov = str(data.get("physical_state_prov") or "").strip() or None
    country = str(data.get("country") or "US").strip().upper()
    postal_code = str(data.get("postal_code") or "").strip() or None
    business_phone = str(data.get("business_phone") or "").strip() or None
    business_email = str(data.get("business_email") or "").strip() or None
    website = str(data.get("website") or "").strip() or None
    raw_safety = str(data.get("safety_rating") or "UNKNOWN").strip().upper()
    if raw_safety in ("SATISFACTORY", "VERIFIED_SATISFACTORY"):
        safety_rating = "VERIFIED_SATISFACTORY"
    elif raw_safety in ("CONDITIONAL", "VERIFIED_CONDITIONAL"):
        safety_rating = "VERIFIED_CONDITIONAL"
    elif raw_safety in ("UNSATISFACTORY", "VERIFIED_UNSATISFACTORY"):
        safety_rating = "VERIFIED_UNSATISFACTORY"
    elif raw_safety in ("NOT_RATED", "VERIFIED_NOT_RATED"):
        safety_rating = "VERIFIED_NOT_RATED"
    else:
        safety_rating = "UNKNOWN"

    raw_status = str(data.get("operating_status") or "UNKNOWN").strip().upper()
    if raw_status in ("AUTHORIZED", "VERIFIED_AUTHORIZED", "ACTIVE"):
        operating_status = "VERIFIED_AUTHORIZED"
    elif raw_status in ("NOT_AUTHORIZED", "VERIFIED_NOT_AUTHORIZED", "INACTIVE"):
        operating_status = "VERIFIED_NOT_AUTHORIZED"
    elif raw_status in ("OUT_OF_SERVICE", "VERIFIED_OUT_OF_SERVICE"):
        operating_status = "VERIFIED_OUT_OF_SERVICE"
    else:
        operating_status = "UNKNOWN"

    raw_cb = str(data.get("cross_border_capability") or "UNKNOWN").strip().upper()
    if raw_cb in ("US_ONLY", "CANADA_ONLY", "US_CANADA_CAPABLE"):
        cross_border = raw_cb
    elif raw_cb in ("YES", "TRUE", "CAPABLE"):
        cross_border = "US_CANADA_CAPABLE"
    else:
        cross_border = "UNKNOWN"
    fleet_power_units = data.get("fleet_power_units")
    driver_count = data.get("driver_count")
    preferred_lanes_notes = data.get("preferred_lanes_notes")
    source_type = data.get("source_type") or "USER_ENTERED"
    source_name = data.get("source_name") or "Manual User Intake"
    source_url = data.get("source_url")

    # Equipment handling
    equip_input = data.get("primary_equipment_types")
    if isinstance(equip_input, list):
        primary_equipment_json = json.dumps(equip_input)
    elif isinstance(equip_input, str) and equip_input:
        primary_equipment_json = json.dumps([e.strip() for e in equip_input.split(",") if e.strip()])
    else:
        primary_equipment_json = None

    if country not in ("US", "CA"):
        raise ValueError("Carrier country must be US or CA.")

    # Deduplication check
    existing_id = None
    if usdot:
        row = cur.execute("SELECT id FROM carriers WHERE usdot_number = ?", (usdot,)).fetchone()
        if row:
            existing_id = row[0]
    if not existing_id and mc:
        row = cur.execute("SELECT id FROM carriers WHERE mc_number = ?", (mc,)).fetchone()
        if row:
            existing_id = row[0]
    if not existing_id and legal_name and physical_state_prov:
        row = cur.execute(
            "SELECT id FROM carriers WHERE UPPER(legal_name) = UPPER(?) AND UPPER(physical_state_prov) = UPPER(?)",
            (legal_name, physical_state_prov)
        ).fetchone()
        if row:
            existing_id = row[0]

    now = _now_iso()

    if existing_id:
        # Update existing carrier
        cur.execute("""
            UPDATE carriers SET
                legal_name = COALESCE(NULLIF(?, ''), legal_name),
                dba_name = COALESCE(?, dba_name),
                usdot_number = COALESCE(?, usdot_number),
                mc_number = COALESCE(?, mc_number),
                physical_city = COALESCE(?, physical_city),
                physical_state_prov = COALESCE(?, physical_state_prov),
                country = COALESCE(?, country),
                postal_code = COALESCE(?, postal_code),
                business_phone = COALESCE(?, business_phone),
                business_email = COALESCE(?, business_email),
                website = COALESCE(?, website),
                safety_rating = COALESCE(NULLIF(?, 'UNKNOWN'), safety_rating),
                operating_status = COALESCE(NULLIF(?, 'UNKNOWN'), operating_status),
                cross_border_capability = COALESCE(NULLIF(?, 'UNKNOWN'), cross_border_capability),
                primary_equipment_types = COALESCE(?, primary_equipment_types),
                fleet_power_units = COALESCE(?, fleet_power_units),
                driver_count = COALESCE(?, driver_count),
                preferred_lanes_notes = COALESCE(?, preferred_lanes_notes),
                source_type = COALESCE(?, source_type),
                source_name = COALESCE(?, source_name),
                source_url = COALESCE(?, source_url),
                observed_at = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            legal_name, dba_name, usdot, mc, physical_city, physical_state_prov,
            country, postal_code, business_phone, business_email, website,
            safety_rating, operating_status, cross_border, primary_equipment_json,
            fleet_power_units, driver_count, preferred_lanes_notes,
            source_type, source_name, source_url, now, now, existing_id
        ))
        carrier_id = existing_id
    else:
        # Insert new carrier
        cur.execute("""
            INSERT INTO carriers (
                legal_name, dba_name, usdot_number, mc_number, physical_city,
                physical_state_prov, country, postal_code, business_phone,
                business_email, website, safety_rating, operating_status,
                cross_border_capability, primary_equipment_types,
                fleet_power_units, driver_count, preferred_lanes_notes,
                source_type, source_name, source_url, observed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            legal_name, dba_name, usdot, mc, physical_city,
            physical_state_prov, country, postal_code, business_phone,
            business_email, website, safety_rating, operating_status,
            cross_border, primary_equipment_json,
            fleet_power_units, driver_count, preferred_lanes_notes,
            source_type, source_name, source_url, now, now, now
        ))
        carrier_id = cur.lastrowid

        # Initialize default engagement state
        cur.execute("""
            INSERT OR IGNORE INTO carrier_engagement_state (carrier_id, current_relationship_status, created_at, updated_at)
            VALUES (?, 'UNCONTACTED', ?, ?)
        """, (carrier_id, now, now))

    conn.commit()
    return get_carrier_by_id(conn, carrier_id)


def list_carriers(
    conn: sqlite3.Connection,
    search: Optional[str] = None,
    ownership: Optional[str] = None,
    user_id: Optional[int] = None,
    authority: Optional[List[str]] = None,
    equipment: Optional[List[str]] = None,
    country: Optional[List[str]] = None,
    capacity: Optional[str] = None,
    relationship: Optional[List[str]] = None,
    cross_border: Optional[List[str]] = None,
    source: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> Dict[str, Any]:
    """
    Search and multi-group filter query for Carrier Directory.
    OR within a filter group, AND across groups. Server-side paginated.
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    where_clauses = []
    params: List[Any] = []

    # 1. Search: name, USDOT, MC, phone, city, state
    if search and search.strip():
        term = f"%{search.strip()}%"
        where_clauses.append("""
            (c.legal_name LIKE ? OR c.dba_name LIKE ? OR c.usdot_number LIKE ?
             OR c.mc_number LIKE ? OR c.business_phone LIKE ? OR c.physical_city LIKE ?
             OR c.physical_state_prov LIKE ?)
        """)
        params.extend([term, term, term, term, term, term, term])

    # 2. Ownership: Available (unclaimed), Mine (assigned to user_id), All
    if ownership == "mine" and user_id:
        where_clauses.append("ca.owner_id = ?")
        params.append(user_id)
    elif ownership == "available":
        where_clauses.append("ca.owner_id IS NULL")

    # 3. Authority Status (OR within group)
    if authority:
        sub_auth = []
        for a in authority:
            a_clean = a.strip().upper()
            if a_clean == "VERIFIED_ACTIVE" or a_clean == "ACTIVE":
                sub_auth.append("c.operating_status = 'VERIFIED_AUTHORIZED'")
            elif a_clean == "UNKNOWN":
                sub_auth.append("c.operating_status = 'UNKNOWN'")
            elif a_clean in ("INACTIVE", "OUT_OF_SERVICE"):
                sub_auth.append("c.operating_status IN ('VERIFIED_NOT_AUTHORIZED', 'VERIFIED_OUT_OF_SERVICE')")
        if sub_auth:
            where_clauses.append(f"({' OR '.join(sub_auth)})")

    # 4. Equipment (OR within group)
    if equipment:
        sub_eq = []
        for eq in equipment:
            eq_term = f"%{eq.strip().upper()}%"
            sub_eq.append("c.primary_equipment_types LIKE ?")
            params.append(eq_term)
        if sub_eq:
            where_clauses.append(f"({' OR '.join(sub_eq)})")

    # 5. Country (OR within group)
    if country:
        sub_cnt = []
        for cnt in country:
            sub_cnt.append("c.country = ?")
            params.append(cnt.strip().upper())
        if sub_cnt:
            where_clauses.append(f"({' OR '.join(sub_cnt)})")

    # 6. Capacity Status
    today_str = date.today().isoformat()
    if capacity == "available_now":
        where_clauses.append("""
            EXISTS (
                SELECT 1 FROM capacity_postings cp
                WHERE cp.carrier_id = c.id
                  AND cp.capacity_status IN ('ACTIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW')
                  AND cp.available_date_start <= ?
                  AND (cp.available_date_end IS NULL OR cp.available_date_end >= ?)
            )
        """)
        params.extend([today_str, today_str])
    elif capacity == "upcoming":
        where_clauses.append("""
            EXISTS (
                SELECT 1 FROM capacity_postings cp
                WHERE cp.carrier_id = c.id
                  AND cp.capacity_status IN ('ACTIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW')
                  AND cp.available_date_start > ?
            )
        """)
        params.append(today_str)
    elif capacity == "none":
        where_clauses.append("""
            NOT EXISTS (
                SELECT 1 FROM capacity_postings cp
                WHERE cp.carrier_id = c.id
                  AND cp.capacity_status IN ('ACTIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW')
                  AND (cp.available_date_end IS NULL OR cp.available_date_end >= ?)
            )
        """)
        params.append(today_str)

    # 7. Relationship Status (OR within group)
    if relationship:
        sub_rel = []
        for r in relationship:
            sub_rel.append("COALESCE(es.current_relationship_status, 'UNCONTACTED') = ?")
            params.append(r.strip().upper())
        if sub_rel:
            where_clauses.append(f"({' OR '.join(sub_rel)})")

    # 8. Cross-Border (OR within group)
    if cross_border:
        sub_cb = []
        for cb in cross_border:
            cb_clean = cb.strip().upper()
            if cb_clean in ("VERIFIED", "US_CANADA_CAPABLE"):
                sub_cb.append("c.cross_border_capability = 'US_CANADA_CAPABLE'")
            elif cb_clean == "UNKNOWN":
                sub_cb.append("c.cross_border_capability = 'UNKNOWN'")
            elif cb_clean in ("US_ONLY", "CANADA_ONLY"):
                sub_cb.append("c.cross_border_capability = ?")
                params.append(cb_clean)
        if sub_cb:
            where_clauses.append(f"({' OR '.join(sub_cb)})")

    # 9. Source
    if source and source.strip():
        where_clauses.append("c.source_type = ?")
        params.append(source.strip().upper())

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Count total
    count_sql = f"""
        SELECT count(DISTINCT c.id)
        FROM carriers c
        LEFT JOIN carrier_assignments ca ON ca.carrier_id = c.id
        LEFT JOIN carrier_engagement_state es ON es.carrier_id = c.id
        {where_sql}
    """
    total = cur.execute(count_sql, params).fetchone()[0]

    # Order
    order_clause = "c.legal_name ASC"
    if sort_by == "created":
        order_clause = f"c.created_at {'DESC' if sort_dir.lower() == 'desc' else 'ASC'}"
    elif sort_by == "power_units":
        order_clause = f"c.fleet_power_units {'DESC' if sort_dir.lower() == 'desc' else 'ASC'}"
    elif sort_by == "state":
        order_clause = f"c.physical_state_prov {'DESC' if sort_dir.lower() == 'desc' else 'ASC'}, c.legal_name ASC"

    offset = (max(1, page) - 1) * page_size
    query_sql = f"""
        SELECT c.*,
               ca.owner_id,
               tu.username AS owner_username,
               COALESCE(es.current_relationship_status, 'UNCONTACTED') AS current_relationship_status,
               es.attempt_count,
               es.last_contacted_at,
               es.next_callback_at,
               (
                   SELECT count(*) FROM capacity_postings cp
                   WHERE cp.carrier_id = c.id
                     AND cp.capacity_status IN ('ACTIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW')
                     AND (cp.available_date_end IS NULL OR cp.available_date_end >= '{today_str}')
               ) AS active_capacity_count,
               (
                   SELECT cp.available_city || ', ' || cp.available_state_prov || ' (' || cp.equipment_type || ')'
                   FROM capacity_postings cp
                   WHERE cp.carrier_id = c.id
                     AND cp.capacity_status IN ('ACTIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW')
                     AND (cp.available_date_end IS NULL OR cp.available_date_end >= '{today_str}')
                   ORDER BY cp.available_date_start ASC LIMIT 1
               ) AS next_available_capacity_summary
        FROM carriers c
        LEFT JOIN carrier_assignments ca ON ca.carrier_id = c.id
        LEFT JOIN team_users tu ON tu.id = ca.owner_id
        LEFT JOIN carrier_engagement_state es ON es.carrier_id = c.id
        {where_sql}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    rows = cur.execute(query_sql, params + [page_size, offset]).fetchall()
    items = []
    for r in rows:
        item = dict(r)
        if item.get("primary_equipment_types"):
            try:
                item["equipment_types_list"] = json.loads(item["primary_equipment_types"])
            except Exception:
                item["equipment_types_list"] = [item["primary_equipment_types"]]
        else:
            item["equipment_types_list"] = []
        items.append(item)

    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_carrier_summary_counts(conn: sqlite3.Connection, user_id: Optional[int] = None) -> Dict[str, int]:
    """Returns dynamic summary counts for the Carrier Directory top area."""
    cur = conn.cursor()
    today_str = date.today().isoformat()

    total_carriers = cur.execute("SELECT count(*) FROM carriers;").fetchone()[0]
    verified_carriers = cur.execute(
        "SELECT count(*) FROM carriers WHERE operating_status = 'VERIFIED_AUTHORIZED';"
    ).fetchone()[0]

    available_capacity = cur.execute("""
        SELECT count(*) FROM capacity_postings
        WHERE capacity_status IN ('ACTIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW')
          AND (available_date_end IS NULL OR available_date_end >= ?)
    """, (today_str,)).fetchone()[0]

    my_carriers = 0
    if user_id:
        my_carriers = cur.execute(
            "SELECT count(*) FROM carrier_assignments WHERE owner_id = ?;", (user_id,)
        ).fetchone()[0]

    active_matches = cur.execute("""
        SELECT count(DISTINCT load_opportunity_id) FROM load_capacity_matches
        WHERE match_status IN ('PROPOSED', 'CANDIDATE', 'CONTACTED', 'QUOTED')
    """).fetchone()[0]

    return {
        "total_carriers": total_carriers,
        "verified_carriers": verified_carriers,
        "available_capacity": available_capacity,
        "my_carriers": my_carriers,
        "active_matches": active_matches,
    }


# ==============================================================================
# CARRIER BUSINESS CONTACTS
# ==============================================================================

def get_carrier_contacts(conn: sqlite3.Connection, carrier_id: int) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM contacts
        WHERE carrier_id = ?
        ORDER BY is_primary_contact DESC, id ASC
    """, (carrier_id,)).fetchall()
    return [dict(r) for r in rows]


def add_carrier_contact(
    conn: sqlite3.Connection,
    carrier_id: int,
    data: Dict[str, Any],
    user_id: int,
) -> Dict[str, Any]:
    """
    Stores authorized carrier business contact with strict provenance.
    No private driver harvesting; business lines only.
    """
    person_name = str(data.get("person_name") or "").strip() or None
    title = str(data.get("exact_published_title") or "").strip() or None
    department = str(data.get("department") or "DISPATCH").strip()
    phone = str(data.get("phone_number") or "").strip() or None
    extension = str(data.get("phone_extension") or "").strip() or None
    email = str(data.get("email_address") or "").strip() or None
    raw_pd = str(data.get("phone_directness") or "GENERAL_SWITCHBOARD").strip().upper()
    if raw_pd in ('DIRECT_PERSON', 'DIRECT', 'DIRECT_DESK'):
        phone_directness = 'DIRECT_PERSON'
    elif raw_pd in ('DEPARTMENT_LINE', 'DEPARTMENT'):
        phone_directness = 'DEPARTMENT_LINE'
    elif raw_pd in ('RECEPTION',):
        phone_directness = 'RECEPTION'
    elif raw_pd in ('TOLL_FREE',):
        phone_directness = 'TOLL_FREE'
    elif raw_pd in ('GENERAL_SWITCHBOARD', 'SWITCHBOARD'):
        phone_directness = 'GENERAL_SWITCHBOARD'
    else:
        phone_directness = 'UNKNOWN'

    raw_ed = str(data.get("email_directness") or "GENERAL").strip().upper()
    if raw_ed in ('DIRECT_PERSON', 'DIRECT'):
        email_directness = 'DIRECT_PERSON'
    elif raw_ed in ('DEPARTMENT_ROLE', 'DEPARTMENT'):
        email_directness = 'DEPARTMENT_ROLE'
    elif raw_ed in ('GENERAL',):
        email_directness = 'GENERAL'
    else:
        email_directness = 'UNKNOWN'

    role_cat = str(data.get("role_category") or "OPERATIONS").strip().upper()
    is_primary = 1 if data.get("is_primary_contact") else 0

    identity = "NAMED_PERSON" if person_name else "DEPARTMENT"

    cur = conn.cursor()
    if is_primary:
        cur.execute("UPDATE contacts SET is_primary_contact = 0 WHERE carrier_id = ?", (carrier_id,))

    cur.execute("""
        INSERT INTO contacts (
            carrier_id, contact_identity, person_name, exact_published_title,
            department, phone_number, phone_extension, phone_directness,
            email_address, email_directness, role_category, is_primary_contact, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        carrier_id, identity, person_name, title, department, phone, extension,
        phone_directness, email, email_directness, role_cat, is_primary, _now_iso()
    ))
    conn.commit()
    contact_id = cur.lastrowid
    conn.row_factory = sqlite3.Row
    return dict(cur.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone())


# ==============================================================================
# CARRIER LANE PREFERENCES & RECURRING ROUTES
# ==============================================================================

def get_carrier_lanes(conn: sqlite3.Connection, carrier_id: int) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM carrier_lane_activity
        WHERE carrier_id = ?
        ORDER BY preference_level ASC, id DESC
    """, (carrier_id,)).fetchall()
    return [dict(r) for r in rows]


def add_carrier_lane(
    conn: sqlite3.Connection,
    carrier_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    origin_region = str(data.get("origin_region") or "").strip().upper()
    dest_region = str(data.get("dest_region") or "").strip().upper()
    origin_country = str(data.get("origin_country") or "US").strip().upper()
    dest_country = str(data.get("dest_country") or "US").strip().upper()
    origin_city = str(data.get("origin_city") or "").strip() or None
    dest_city = str(data.get("dest_city") or "").strip() or None
    equipment_type = str(data.get("equipment_type") or "").strip().upper() or None
    activity_type = str(data.get("activity_type") or "DISPATCHER_PREFERRED").strip()
    preference_level = str(data.get("preference_level") or "PREFERRED").strip().upper()
    available_days = data.get("available_days")
    notes = data.get("notes")

    if not origin_region or not dest_region:
        raise ValueError("Origin and destination regions are required for lane preference.")

    now = _now_iso()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO carrier_lane_activity (
            carrier_id, origin_country, origin_region, dest_country, dest_region,
            origin_city, dest_city, equipment_type, activity_type, preference_level,
            available_days, observed_at, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        carrier_id, origin_country, origin_region, dest_country, dest_region,
        origin_city, dest_city, equipment_type, activity_type, preference_level,
        available_days, now, notes, now
    ))
    conn.commit()
    lane_id = cur.lastrowid
    conn.row_factory = sqlite3.Row
    return dict(cur.execute("SELECT * FROM carrier_lane_activity WHERE id = ?", (lane_id,)).fetchone())


# ==============================================================================
# CAPACITY POSTINGS (AVAILABLE TRUCKS)
# ==============================================================================

def list_capacity_postings(
    conn: sqlite3.Connection,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    available_date: Optional[str] = None,
    equipment: Optional[List[str]] = None,
    country: Optional[List[str]] = None,
    carrier_id: Optional[int] = None,
    active_only: bool = True,
    page: int = 1,
    page_size: int = 25,
) -> Dict[str, Any]:
    """
    Lists available trucks/capacity with freshness filtering.
    Stale or expired postings are excluded by default when active_only=True.
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    where_clauses = []
    params: List[Any] = []

    today_str = date.today().isoformat()

    if active_only:
        where_clauses.append("cp.capacity_status IN ('ACTIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW')")
        where_clauses.append("(cp.available_date_end IS NULL OR cp.available_date_end >= ?)")
        params.append(today_str)

    if carrier_id:
        where_clauses.append("cp.carrier_id = ?")
        params.append(carrier_id)

    if origin and origin.strip():
        term = f"%{origin.strip()}%"
        where_clauses.append("(cp.available_city LIKE ? OR cp.available_state_prov LIKE ?)")
        params.extend([term, term])

    if destination and destination.strip():
        term = f"%{destination.strip()}%"
        where_clauses.append("(cp.destination_city LIKE ? OR cp.destination_state_prov LIKE ? OR cp.destination_preference_notes LIKE ?)")
        params.extend([term, term, term])

    if available_date and available_date.strip():
        ad_clean = available_date.strip()[:10]
        where_clauses.append("cp.available_date_start <= ? AND (cp.available_date_end IS NULL OR cp.available_date_end >= ?)")
        params.extend([ad_clean, ad_clean])

    if equipment:
        sub_eq = []
        for eq in equipment:
            sub_eq.append("cp.equipment_type = ?")
            params.append(eq.strip().upper())
        if sub_eq:
            where_clauses.append(f"({' OR '.join(sub_eq)})")

    if country:
        sub_cnt = []
        for cnt in country:
            sub_cnt.append("cp.available_country = ?")
            params.append(cnt.strip().upper())
        if sub_cnt:
            where_clauses.append(f"({' OR '.join(sub_cnt)})")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    count_sql = f"SELECT count(*) FROM capacity_postings cp {where_sql}"
    total = cur.execute(count_sql, params).fetchone()[0]

    offset = (max(1, page) - 1) * page_size
    query_sql = f"""
        SELECT cp.*,
               c.legal_name AS carrier_name,
               c.usdot_number,
               c.mc_number,
               c.operating_status,
               c.cross_border_capability,
               c.business_phone,
               ca.owner_id,
               tu.username AS owner_username,
               COALESCE(es.current_relationship_status, 'UNCONTACTED') AS relationship_status
        FROM capacity_postings cp
        JOIN carriers c ON c.id = cp.carrier_id
        LEFT JOIN carrier_assignments ca ON ca.carrier_id = c.id
        LEFT JOIN team_users tu ON tu.id = ca.owner_id
        LEFT JOIN carrier_engagement_state es ON es.carrier_id = c.id
        {where_sql}
        ORDER BY cp.available_date_start ASC, cp.id DESC
        LIMIT ? OFFSET ?
    """
    rows = cur.execute(query_sql, params + [page_size, offset]).fetchall()
    items = [dict(r) for r in rows]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


def add_capacity_posting(
    conn: sqlite3.Connection,
    carrier_id: int,
    data: Dict[str, Any],
    user_id: int,
) -> Dict[str, Any]:
    """Records an available truck capacity posting."""
    avail_city = str(data.get("available_city") or "").strip()
    avail_state = str(data.get("available_state_prov") or "").strip().upper()
    avail_country = str(data.get("available_country") or "US").strip().upper()
    avail_start = str(data.get("available_date_start") or date.today().isoformat()).strip()[:10]
    avail_end = str(data.get("available_date_end") or avail_start).strip()[:10]
    equipment = str(data.get("equipment_type") or "FLATBED").strip().upper()
    trailer_specs = data.get("trailer_specs_capability")
    weight_cap = data.get("weight_capability_lbs")
    dest_notes = data.get("destination_preference_notes")
    dest_city = str(data.get("destination_city") or "").strip() or None
    dest_state = str(data.get("destination_state_prov") or "").strip().upper() or None
    dest_country = str(data.get("destination_country") or "US").strip().upper() or None
    desired_rate = data.get("desired_rate")
    rate_currency = str(data.get("rate_currency") or "USD").strip().upper()
    rate_basis = str(data.get("rate_basis") or "FLAT").strip().upper()
    truck_count = int(data.get("available_truck_count") or 1)
    raw_status = str(data.get("capacity_status") or "ACTIVE").strip().upper()
    notes = data.get("notes")

    if not avail_city or not avail_state:
        raise ValueError("Available city and state/province are required.")

    now = _now_iso()
    if raw_status in ("ACTIVE", "TRUCK_CONFIRMED_AVAILABLE_NOW"):
        db_status = "TRUCK_CONFIRMED_AVAILABLE_NOW"
        confirmed_at = now
        expires_at = f"{avail_end}T23:59:59Z"
    elif raw_status == "POSTED_TENTATIVE":
        db_status = "POSTED_TENTATIVE"
        confirmed_at = None
        expires_at = None
    elif raw_status in ("EXPIRED", "WITHDRAWN"):
        db_status = "EXPIRED"
        confirmed_at = None
        expires_at = now
    elif raw_status == "COVERED_BOOKED":
        db_status = "COVERED_BOOKED"
        confirmed_at = now
        expires_at = now
    else:
        db_status = "TRUCK_CONFIRMED_AVAILABLE_NOW"
        confirmed_at = now
        expires_at = f"{avail_end}T23:59:59Z"

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO capacity_postings (
            carrier_id, capacity_status, available_city, available_state_prov,
            available_country, available_date_start, available_date_end,
            equipment_type, trailer_specs_capability, weight_capability_lbs,
            destination_preference_notes, destination_city, destination_state_prov,
            destination_country, desired_rate, rate_currency, rate_basis,
            available_truck_count, confirmed_at, expires_at, event_at, observed_at, created_at, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        carrier_id, db_status, avail_city, avail_state,
        avail_country, avail_start, avail_end,
        equipment, trailer_specs, weight_cap,
        dest_notes, dest_city, dest_state,
        dest_country, desired_rate, rate_currency, rate_basis,
        truck_count, confirmed_at, expires_at, now, now, now, notes
    ))
    conn.commit()
    post_id = cur.lastrowid
    conn.row_factory = sqlite3.Row
    return dict(cur.execute("SELECT * FROM capacity_postings WHERE id = ?", (post_id,)).fetchone())


# ==============================================================================
# TEAM OWNERSHIP & ASSIGNMENTS
# ==============================================================================

def get_carrier_owner(conn: sqlite3.Connection, carrier_id: int) -> Optional[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT ca.*, tu.username, tu.role
        FROM carrier_assignments ca
        JOIN team_users tu ON tu.id = ca.owner_id
        WHERE ca.carrier_id = ?
    """, (carrier_id,)).fetchone()
    return dict(row) if row else None


def assert_carrier_owner_or_admin(conn: sqlite3.Connection, carrier_id: int, user: Dict[str, Any]) -> None:
    if user.get("role") == "ADMIN":
        return
    owner = get_carrier_owner(conn, carrier_id)
    if not owner or owner.get("owner_id") != user.get("id"):
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this carrier. Click 'Start Working' first or contact an Admin."
        )


def claim_carrier(conn: sqlite3.Connection, carrier_id: int, user_id: int) -> Dict[str, Any]:
    """Action: 'Start Working' on carrier."""
    cur = conn.cursor()
    now = _now_iso()
    existing = get_carrier_owner(conn, carrier_id)
    if existing:
        if existing["owner_id"] == user_id:
            return existing
        raise HTTPException(
            status_code=409,
            detail=f"Carrier is already assigned to {existing['username']}."
        )

    cur.execute("""
        INSERT INTO carrier_assignments (carrier_id, owner_id, updated_at)
        VALUES (?, ?, ?)
    """, (carrier_id, user_id, now))

    cur.execute("""
        INSERT INTO carrier_assignment_history (carrier_id, actor_id, to_user_id, action, note, created_at)
        VALUES (?, ?, ?, 'CLAIM', 'Started working on carrier', ?)
    """, (carrier_id, user_id, user_id, now))
    conn.commit()
    return get_carrier_owner(conn, carrier_id)


def transfer_carrier(
    conn: sqlite3.Connection,
    carrier_id: int,
    actor_id: int,
    target_id: int,
    note: str = "",
) -> Dict[str, Any]:
    """Admin or current owner transfers carrier to another broker."""
    cur = conn.cursor()
    now = _now_iso()
    existing = get_carrier_owner(conn, carrier_id)
    old_owner_id = existing["owner_id"] if existing else None

    cur.execute("""
        INSERT INTO carrier_assignments (carrier_id, owner_id, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(carrier_id) DO UPDATE SET owner_id = excluded.owner_id, updated_at = excluded.updated_at
    """, (carrier_id, target_id, now))

    cur.execute("""
        INSERT INTO carrier_assignment_history (carrier_id, actor_id, from_user_id, to_user_id, action, note, created_at)
        VALUES (?, ?, ?, ?, 'TRANSFER', ?, ?)
    """, (carrier_id, actor_id, old_owner_id, target_id, note, now))
    conn.commit()
    return get_carrier_owner(conn, carrier_id)


def release_carrier(
    conn: sqlite3.Connection,
    carrier_id: int,
    actor_id: int,
    note: str = "",
) -> None:
    """Releases carrier back to unassigned pool."""
    cur = conn.cursor()
    now = _now_iso()
    existing = get_carrier_owner(conn, carrier_id)
    old_owner_id = existing["owner_id"] if existing else None

    cur.execute("DELETE FROM carrier_assignments WHERE carrier_id = ?", (carrier_id,))
    cur.execute("""
        INSERT INTO carrier_assignment_history (carrier_id, actor_id, from_user_id, to_user_id, action, note, created_at)
        VALUES (?, ?, ?, NULL, 'RELEASE', ?, ?)
    """, (carrier_id, actor_id, old_owner_id, note, now))
    conn.commit()


def get_carrier_assignment_history(conn: sqlite3.Connection, carrier_id: int) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT h.*,
               act.username AS actor_username,
               f.username AS from_username,
               t.username AS to_username
        FROM carrier_assignment_history h
        JOIN team_users act ON act.id = h.actor_id
        LEFT JOIN team_users f ON f.id = h.from_user_id
        LEFT JOIN team_users t ON t.id = h.to_user_id
        WHERE h.carrier_id = ?
        ORDER BY h.id DESC
    """, (carrier_id,)).fetchall()
    return [dict(r) for r in rows]


# ==============================================================================
# CARRIER OUTREACH (APPEND-ONLY) & ENGAGEMENT
# ==============================================================================

def get_carrier_engagement_state(conn: sqlite3.Connection, carrier_id: int) -> Dict[str, Any]:
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM carrier_engagement_state WHERE carrier_id = ?", (carrier_id,)).fetchone()
    if row:
        return dict(row)
    return {
        "carrier_id": carrier_id,
        "current_relationship_status": "UNCONTACTED",
        "attempt_count": 0,
        "last_contacted_at": None,
        "next_callback_at": None,
        "last_call_disposition": None,
        "last_call_notes": None,
    }


def get_carrier_outreach_history(conn: sqlite3.Connection, carrier_id: int) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT o.*,
               tu.username AS author_username,
               cnt.person_name AS contact_person_name,
               cnt.phone_number AS contact_phone
        FROM carrier_outreach_logs o
        LEFT JOIN team_users tu ON tu.id = o.author_user_id
        LEFT JOIN contacts cnt ON cnt.id = o.contact_id
        WHERE o.carrier_id = ?
        ORDER BY o.id DESC
    """, (carrier_id,)).fetchall()
    return [dict(r) for r in rows]


def log_carrier_outreach_call(
    conn: sqlite3.Connection,
    carrier_id: int,
    user_id: int,
    disposition: str,
    notes: str,
    contact_id: Optional[int] = None,
    callback_date: Optional[str] = None,
    callback_time: Optional[str] = None,
    quoted_rate: Optional[float] = None,
    quoted_rate_currency: str = "USD",
    facility_location: Optional[str] = None,
    load_id: Optional[int] = None,
    capacity_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Logs an outreach call to carrier_outreach_logs (strictly append-only).
    Updates carrier_engagement_state projection.
    """
    disp = disposition.strip().upper()
    valid_disp = (
        'INTERESTED', 'CALL_BACK', 'NO_ANSWER', 'NOT_INTERESTED',
        'LEFT_VOICEMAIL', 'WRONG_CONTACT', 'CONNECTED_DISPATCH', 'CONNECTED_OWNER'
    )
    if disp not in valid_disp:
        raise ValueError(f"Invalid carrier call disposition: {disp}")

    if disp == "CALL_BACK" and not callback_date:
        raise ValueError("Callback date is required when disposition is CALL_BACK.")

    now = _now_iso()
    cur = conn.cursor()

    # 1. Insert into append-only log table
    cur.execute("""
        INSERT INTO carrier_outreach_logs (
            carrier_id, author_user_id, contact_id, load_opportunity_id,
            capacity_posting_id, facility_location, disposition, call_timestamp,
            callback_date, callback_time, quoted_rate, quoted_rate_currency,
            notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        carrier_id, user_id, contact_id, load_id,
        capacity_id, facility_location, disp, now,
        callback_date, callback_time, quoted_rate, quoted_rate_currency,
        notes, now
    ))
    log_id = cur.lastrowid

    # 2. Derive relationship status
    rel_status = "INTERESTED" if disp == "INTERESTED" else (
        "CALL_BACK" if disp == "CALL_BACK" else (
            "NOT_INTERESTED" if disp == "NOT_INTERESTED" else (
                "NO_ANSWER" if disp in ("NO_ANSWER", "LEFT_VOICEMAIL") else "UNCONTACTED"
            )
        )
    )

    cb_iso = f"{callback_date}T{callback_time or '09:00'}:00" if callback_date else None

    # 3. Update engagement projection
    cur.execute("""
        INSERT INTO carrier_engagement_state (
            carrier_id, current_relationship_status, attempt_count,
            last_contacted_at, next_callback_at, last_call_disposition,
            last_call_notes, created_at, updated_at
        ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(carrier_id) DO UPDATE SET
            current_relationship_status = excluded.current_relationship_status,
            attempt_count = attempt_count + 1,
            last_contacted_at = excluded.last_contacted_at,
            next_callback_at = excluded.next_callback_at,
            last_call_disposition = excluded.last_call_disposition,
            last_call_notes = excluded.last_call_notes,
            updated_at = excluded.updated_at
    """, (carrier_id, rel_status, now, cb_iso, disp, notes, now, now))

    # 4. If quote was provided, also record in carrier_quotes
    if quoted_rate and load_id:
        cur.execute("""
            INSERT INTO carrier_quotes (
                carrier_id, load_opportunity_id, capacity_posting_id,
                author_user_id, quoted_amount, currency, notes, quoted_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (carrier_id, load_id, capacity_id, user_id, quoted_rate, quoted_rate_currency, notes, now, now))

    conn.commit()
    conn.row_factory = sqlite3.Row
    return dict(cur.execute("SELECT * FROM carrier_outreach_logs WHERE id = ?", (log_id,)).fetchone())


def clear_carrier_relationship(conn: sqlite3.Connection, carrier_id: int, user_id: int) -> Dict[str, Any]:
    """Clears active engagement status to UNCONTACTED while preserving full call history."""
    now = _now_iso()
    cur = conn.cursor()
    cur.execute("""
        UPDATE carrier_engagement_state SET
            current_relationship_status = 'UNCONTACTED',
            next_callback_at = NULL,
            updated_at = ?
        WHERE carrier_id = ?
    """, (now, carrier_id))
    conn.commit()
    return get_carrier_engagement_state(conn, carrier_id)


# ==============================================================================
# QUOTES
# ==============================================================================

def add_carrier_quote(
    conn: sqlite3.Connection,
    carrier_id: int,
    load_id: int,
    author_user_id: int,
    quoted_amount: float,
    rate_basis: str = "FLAT",
    currency: str = "USD",
    notes: str = "",
    capacity_id: Optional[int] = None,
    match_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Records a quote from carrier for a load without overwriting prior quotes."""
    now = _now_iso()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO carrier_quotes (
            carrier_id, load_opportunity_id, capacity_posting_id,
            load_capacity_match_id, author_user_id, quoted_amount,
            rate_basis, currency, quote_status, notes, quoted_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OFFERED', ?, ?, ?)
    """, (
        carrier_id, load_id, capacity_id, match_id, author_user_id,
        quoted_amount, rate_basis, currency, notes, now, now
    ))
    conn.commit()
    quote_id = cur.lastrowid
    conn.row_factory = sqlite3.Row
    return dict(cur.execute("SELECT * FROM carrier_quotes WHERE id = ?", (quote_id,)).fetchone())


def get_carrier_quotes(
    conn: sqlite3.Connection,
    carrier_id: Optional[int] = None,
    load_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    where = []
    params = []
    if carrier_id:
        where.append("q.carrier_id = ?")
        params.append(carrier_id)
    if load_id:
        where.append("q.load_opportunity_id = ?")
        params.append(load_id)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(f"""
        SELECT q.*,
               tu.username AS author_username,
               c.legal_name AS carrier_name
        FROM carrier_quotes q
        JOIN team_users tu ON tu.id = q.author_user_id
        JOIN carriers c ON c.id = q.carrier_id
        {where_sql}
        ORDER BY q.id DESC
    """, params).fetchall()
    return [dict(r) for r in rows]


# ==============================================================================
# CARRIER SUPPRESSIONS
# ==============================================================================

def add_carrier_suppression(
    conn: sqlite3.Connection,
    scope_type: str,
    reason_notes: str,
    carrier_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    origin_state: Optional[str] = None,
    dest_state: Optional[str] = None,
    suppression_status: str = "DO_NOT_CONTACT",
    assigned_by: str = "USER",
) -> Dict[str, Any]:
    now = _now_iso()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO carrier_suppressions (
            scope_type, carrier_id, contact_id, origin_state_prov,
            dest_state_prov, suppression_status, reason_notes,
            assigned_by, effective_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        scope_type, carrier_id, contact_id, origin_state,
        dest_state, suppression_status, reason_notes, assigned_by, now
    ))
    conn.commit()
    sup_id = cur.lastrowid
    conn.row_factory = sqlite3.Row
    return dict(cur.execute("SELECT * FROM carrier_suppressions WHERE id = ?", (sup_id,)).fetchone())


def get_carrier_suppressions(conn: sqlite3.Connection, carrier_id: Optional[int] = None) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    if carrier_id:
        rows = conn.execute("SELECT * FROM carrier_suppressions WHERE carrier_id = ? ORDER BY id DESC", (carrier_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM carrier_suppressions ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def check_carrier_suppression(
    conn: sqlite3.Connection,
    carrier_id: int,
    contact_id: Optional[int] = None,
    origin_state: Optional[str] = None,
    dest_state: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT * FROM carrier_suppressions
        WHERE (scope_type = 'CARRIER' AND carrier_id = ?)
           OR (scope_type = 'CONTACT' AND contact_id = ?)
           OR (scope_type = 'LANE' AND origin_state_prov = ? AND dest_state_prov = ?)
        LIMIT 1
    """, (carrier_id, contact_id, origin_state, dest_state)).fetchone()
    return dict(row) if row else None


def remove_carrier_suppression(conn: sqlite3.Connection, suppression_id: int) -> bool:
    cur = conn.cursor()
    cur.execute("DELETE FROM carrier_suppressions WHERE id = ?", (suppression_id,))
    conn.commit()
    return cur.rowcount > 0


# ==============================================================================
# LOAD-TO-CAPACITY MATCHING SERVICE
# ==============================================================================

def find_capacity_matches_for_load(
    conn: sqlite3.Connection,
    load_id: int,
) -> Dict[str, Any]:
    """
    Evaluates all active capacity postings against a discrete load.
    Applies hard exclusions, then scores candidates deterministically.
    Returns ranked candidate list with explainable breakdown.
    """
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    load_row = cur.execute("SELECT * FROM load_opportunities WHERE id = ?", (load_id,)).fetchone()
    if not load_row:
        raise HTTPException(status_code=404, detail="Load not found.")
    load = dict(load_row)

    # Fetch active suppressions
    suppressions = [dict(r) for r in cur.execute("SELECT * FROM carrier_suppressions").fetchall()]

    # Fetch candidate active capacity postings
    today_str = date.today().isoformat()
    candidate_postings = cur.execute("""
        SELECT cp.*,
               c.legal_name AS carrier_name,
               c.usdot_number,
               c.mc_number,
               c.operating_status,
               c.safety_rating,
               c.cross_border_capability,
               c.business_phone,
               c.business_email
        FROM capacity_postings cp
        JOIN carriers c ON c.id = cp.carrier_id
        WHERE (cp.capacity_status IN ('ACTIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW')
               OR cp.id IN (SELECT capacity_posting_id FROM load_capacity_matches WHERE load_opportunity_id = ?))
          AND (cp.available_date_end IS NULL OR cp.available_date_end >= ?)
    """, (load["id"], today_str)).fetchall()

    results = []

    for post_row in candidate_postings:
        post = dict(post_row)
        carrier = {
            "id": post["carrier_id"],
            "legal_name": post["carrier_name"],
            "usdot_number": post["usdot_number"],
            "mc_number": post["mc_number"],
            "operating_status": post["operating_status"],
            "safety_rating": post["safety_rating"],
            "cross_border_capability": post["cross_border_capability"],
        }

        # 1. Check Hard Exclusions
        passed, exclusion_reason = check_hard_exclusions(load, carrier, post, suppressions)
        if not passed:
            continue

        # 2. Carrier Lanes & Quotes
        carrier_lanes = [dict(r) for r in cur.execute(
            "SELECT * FROM carrier_lane_activity WHERE carrier_id = ?", (carrier["id"],)
        ).fetchall()]

        quotes = [dict(r) for r in cur.execute(
            "SELECT * FROM carrier_quotes WHERE carrier_id = ? AND load_opportunity_id = ? ORDER BY id DESC",
            (carrier["id"], load["id"])
        ).fetchall()]

        # 3. Evaluate Match Score & Explanation
        eval_result = evaluate_match_score(load, carrier, post, carrier_lanes, quotes)

        # Check existing match record if present
        match_record = cur.execute("""
            SELECT * FROM load_capacity_matches
            WHERE load_opportunity_id = ? AND capacity_posting_id = ?
        """, (load["id"], post["id"])).fetchone()

        match_status = "CANDIDATE"
        if match_record:
            if "workflow_status" in match_record.keys() and match_record["workflow_status"]:
                match_status = match_record["workflow_status"]
            else:
                match_status = match_record["match_status"]

        results.append({
            "load_id": load["id"],
            "capacity_posting_id": post["id"],
            "carrier_id": carrier["id"],
            "carrier_name": carrier["legal_name"],
            "usdot_number": carrier["usdot_number"],
            "mc_number": carrier["mc_number"],
            "operating_status": carrier["operating_status"],
            "business_phone": post.get("business_phone"),
            "equipment_type": post["equipment_type"],
            "available_city": post["available_city"],
            "available_state_prov": post["available_state_prov"],
            "available_date_start": post["available_date_start"],
            "available_date_end": post["available_date_end"],
            "desired_rate": post.get("desired_rate"),
            "rate_currency": post.get("rate_currency"),
            "match_score": eval_result["score_percent"],
            "match_status": match_status,
            "explanations": eval_result["explanations"],
            "quotes": quotes,
            "latest_quote": quotes[0] if quotes else None,
        })

    # Sort deterministically by match score descending, then by capacity date ascending
    results.sort(key=lambda x: (-x["match_score"], str(x["available_date_start"])))

    return {
        "load": load,
        "matches_count": len(results),
        "matches": results,
    }


def update_load_match_status(
    conn: sqlite3.Connection,
    load_id: int,
    capacity_posting_id: int,
    new_status: str,
    user_id: int,
    quoted_amount: Optional[float] = None,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Updates match status: CANDIDATE -> CONTACTED -> QUOTED -> ACCEPTED / REJECTED -> BOOKED.
    Booking is strictly load-specific; carrier global relationship state is preserved independently.
    """
    valid_statuses = ('CANDIDATE', 'CONTACTED', 'QUOTED', 'ACCEPTED', 'REJECTED', 'BOOKED')
    stat_clean = new_status.strip().upper()
    if stat_clean not in valid_statuses:
        raise ValueError(f"Invalid match status: {stat_clean}")

    cur = conn.cursor()
    now = _now_iso()

    # Get carrier_id for the posting
    row = cur.execute("SELECT carrier_id FROM capacity_postings WHERE id = ?", (capacity_posting_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Capacity posting not found.")
    carrier_id = row[0]

    # Insert or update load_capacity_matches
    existing = cur.execute("""
        SELECT id FROM load_capacity_matches
        WHERE load_opportunity_id = ? AND capacity_posting_id = ?
    """, (load_id, capacity_posting_id)).fetchone()

    if stat_clean in ('CANDIDATE', 'CONTACTED', 'QUOTED'):
        db_match_status = 'PROPOSED'
    elif stat_clean in ('ACCEPTED', 'BOOKED'):
        db_match_status = 'ACCEPTED'
    elif stat_clean == 'REJECTED':
        db_match_status = 'REJECTED'
    elif stat_clean == 'EXPIRED':
        db_match_status = 'EXPIRED'
    else:
        db_match_status = 'PROPOSED'

    booked_at = now if stat_clean == "BOOKED" else None
    booked_by = user_id if stat_clean == "BOOKED" else None

    if existing:
        match_id = existing[0]
        cur.execute("""
            UPDATE load_capacity_matches SET
                match_status = ?,
                workflow_status = ?,
                last_quoted_rate = COALESCE(?, last_quoted_rate),
                notes = COALESCE(?, notes),
                booked_at = COALESCE(?, booked_at),
                booked_by_user_id = COALESCE(?, booked_by_user_id),
                updated_at = ?
            WHERE id = ?
        """, (db_match_status, stat_clean, quoted_amount, notes, booked_at, booked_by, now, match_id))
    else:
        cur.execute("""
            INSERT INTO load_capacity_matches (
                load_opportunity_id, capacity_posting_id, carrier_id,
                match_status, workflow_status, last_quoted_rate, notes, booked_at,
                booked_by_user_id, match_reasoning, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Deterministic Match Candidate', ?, ?)
        """, (
            load_id, capacity_posting_id, carrier_id,
            db_match_status, stat_clean, quoted_amount, notes, booked_at, booked_by, now, now
        ))
        match_id = cur.lastrowid

    if quoted_amount is not None:
        add_carrier_quote(
            conn, carrier_id=carrier_id, load_id=load_id,
            author_user_id=user_id, quoted_amount=quoted_amount,
            notes=notes, capacity_id=capacity_posting_id, match_id=match_id
        )

    if stat_clean == "BOOKED":
        # Mark load as COVERED in load_opportunities
        cur.execute("UPDATE load_opportunities SET load_status = 'COVERED' WHERE id = ?", (load_id,))
        # Mark capacity as COVERED_BOOKED in capacity_postings
        cur.execute("UPDATE capacity_postings SET capacity_status = 'COVERED_BOOKED' WHERE id = ?", (capacity_posting_id,))

    conn.commit()
    conn.row_factory = sqlite3.Row
    res = dict(cur.execute("SELECT * FROM load_capacity_matches WHERE id = ?", (match_id,)).fetchone())
    res["match_status"] = res.get("workflow_status") or res["match_status"]
    return res
