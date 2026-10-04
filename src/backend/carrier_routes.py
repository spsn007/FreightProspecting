"""
Carrier & Capacity Network Endpoints and Router
Shipper IQ V1 — Seamless Extension of Core Architecture
"""

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Dict, List, Literal, Optional
from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from src.backend.db.connection import create_connection
from src.backend.adapters.carrier_sources import (
    get_carrier_adapter,
    list_carrier_adapters,
)
from src.backend.db.carrier_service import (
    create_or_update_carrier,
    get_carrier_by_id,
    get_carrier_by_usdot,
    get_carrier_by_mc,
    list_carriers,
    get_carrier_summary_counts,
    add_carrier_contact,
    get_carrier_contacts,
    add_carrier_lane,
    get_carrier_lanes,
    add_capacity_posting,
    list_capacity_postings,
    claim_carrier,
    transfer_carrier,
    release_carrier,
    get_carrier_owner,
    assert_carrier_owner_or_admin,
    log_carrier_outreach_call,
    get_carrier_outreach_history,
    clear_carrier_relationship,
    add_carrier_quote,
    get_carrier_quotes,
    add_carrier_suppression,
    remove_carrier_suppression,
    get_carrier_suppressions,
    check_carrier_suppression,
    find_capacity_matches_for_load,
    update_load_match_status,
)

carrier_router = APIRouter()


# ==============================================================================
# PYDANTIC SCHEMAS
# ==============================================================================

class CarrierCreateRequest(BaseModel):
    legal_name: str
    dba_name: Optional[str] = None
    usdot_number: Optional[str] = None
    mc_number: Optional[str] = None
    physical_city: Optional[str] = None
    physical_state_prov: str
    country: str = "US"
    postal_code: Optional[str] = None
    business_phone: Optional[str] = None
    business_email: Optional[str] = None
    website: Optional[str] = None
    safety_rating: Optional[str] = "UNKNOWN"
    operating_status: Optional[str] = "UNKNOWN"
    cross_border_capability: Optional[str] = "UNKNOWN"
    primary_equipment_types: Optional[List[str]] = None
    fleet_power_units: Optional[int] = None
    driver_count: Optional[int] = None
    preferred_lanes_notes: Optional[str] = None
    source_type: Optional[str] = "USER_ENTERED"


class CarrierAssignRequest(BaseModel):
    action: Literal["claim", "transfer", "release"]
    target_id: Optional[int] = None
    note: Optional[str] = ""


class CarrierOutreachRequest(BaseModel):
    disposition: str
    notes: str = ""
    contact_id: Optional[int] = None
    callback_date: Optional[str] = None
    callback_time: Optional[str] = None
    quoted_rate: Optional[float] = None
    quoted_rate_currency: str = "USD"
    load_id: Optional[int] = None
    capacity_id: Optional[int] = None
    facility_location: Optional[str] = None


class CarrierContactRequest(BaseModel):
    person_name: Optional[str] = None
    exact_published_title: Optional[str] = None
    department: str = "DISPATCH"
    phone_number: Optional[str] = None
    phone_extension: Optional[str] = None
    email_address: Optional[str] = None
    phone_directness: str = "GENERAL_SWITCHBOARD"
    email_directness: str = "GENERAL"
    role_category: str = "OPERATIONS"
    is_primary_contact: bool = False


class CarrierLaneRequest(BaseModel):
    origin_region: str
    dest_region: str
    origin_country: str = "US"
    dest_country: str = "US"
    origin_city: Optional[str] = None
    dest_city: Optional[str] = None
    equipment_type: Optional[str] = None
    preference_level: str = "PREFERRED"
    available_days: Optional[str] = None
    notes: Optional[str] = None


class CapacityPostRequest(BaseModel):
    available_city: str
    available_state_prov: str
    available_country: str = "US"
    available_date_start: str
    available_date_end: Optional[str] = None
    equipment_type: str = "FLATBED"
    destination_city: Optional[str] = None
    destination_state_prov: Optional[str] = None
    destination_country: Optional[str] = "US"
    desired_rate: Optional[float] = None
    rate_currency: str = "USD"
    rate_basis: str = "FLAT"
    available_truck_count: int = 1
    capacity_status: str = "ACTIVE"
    notes: Optional[str] = None


class CarrierSuppressRequest(BaseModel):
    scope_type: Literal["CARRIER", "CONTACT", "LANE"]
    reason_notes: str
    contact_id: Optional[int] = None
    origin_state: Optional[str] = None
    dest_state: Optional[str] = None
    suppression_status: str = "DO_NOT_CONTACT"


class MatchStatusUpdateRequest(BaseModel):
    status: Literal["CANDIDATE", "CONTACTED", "QUOTED", "ACCEPTED", "REJECTED", "BOOKED"]
    quoted_amount: Optional[float] = None
    notes: Optional[str] = ""


class QuoteCreateRequest(BaseModel):
    carrier_id: int
    load_id: Optional[int] = None
    quoted_amount: float
    currency: str = "USD"
    rate_basis: str = "FLAT"
    notes: Optional[str] = ""
    capacity_id: Optional[int] = None


class LoadCreateRequest(BaseModel):
    origin_city: str
    origin_state_prov: str
    origin_country: str = "US"
    dest_city: str
    dest_state_prov: str
    dest_country: str = "US"
    pickup_date_earliest: str
    pickup_date_latest: Optional[str] = None
    equipment_required: str = "FLATBED"
    facility_id: Optional[int] = None
    weight_lbs: Optional[int] = None
    shipper_target_rate: Optional[float] = None
    carrier_target_cost: Optional[float] = None
    trailer_specs_required: Optional[str] = None
    dimensions_notes: Optional[str] = None


# ==============================================================================
# HTML TEMPLATE VIEWS
# ==============================================================================

def get_templates(request: Request):
    return request.app.state.templates


@carrier_router.get("/carriers", response_class=HTMLResponse)
async def carriers_directory_page(request: Request):
    """Screen 4: Carrier Directory."""
    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="carriers.html",
        context={
            "active_nav": "carriers",
        },
    )


@carrier_router.get("/carriers/{carrier_id}", response_class=HTMLResponse)
async def carrier_detail_page(request: Request, carrier_id: int):
    """Screen 4B: Carrier Detail Profile."""
    templates = get_templates(request)
    with closing(create_connection()) as conn:
        carrier = get_carrier_by_id(conn, carrier_id)
        if not carrier:
            raise HTTPException(status_code=404, detail="Carrier not found.")
    return templates.TemplateResponse(
        request=request,
        name="carrier_detail.html",
        context={
            "carrier": carrier,
            "active_nav": "carriers",
        },
    )


@carrier_router.get("/capacity", response_class=HTMLResponse)
async def available_trucks_page(request: Request):
    """Screen 4C: Available Trucks / Capacity Search."""
    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="capacity.html",
        context={
            "active_nav": "capacity",
        },
    )


@carrier_router.get("/loads", response_class=HTMLResponse)
async def loads_margins_page(request: Request):
    """Screen 3: Loads & Margins (Discrete Opportunities)."""
    templates = get_templates(request)
    return templates.TemplateResponse(
        request=request,
        name="loads.html",
        context={
            "active_nav": "loads",
        },
    )


@carrier_router.get("/loads/{load_id}/matches", response_class=HTMLResponse)
async def load_matches_page(request: Request, load_id: int):
    """Screen 3B: Load Matches Workspace."""
    templates = get_templates(request)
    with closing(create_connection()) as conn:
        conn.row_factory = sqlite3.Row
        load = conn.execute("SELECT * FROM load_opportunities WHERE id = ?", (load_id,)).fetchone()
        if not load:
            raise HTTPException(status_code=404, detail="Load not found.")
    return templates.TemplateResponse(
        request=request,
        name="load_matches.html",
        context={
            "load": dict(load),
            "active_nav": "loads",
        },
    )


# ==============================================================================
# JSON API ENDPOINTS
# ==============================================================================

@carrier_router.get("/api/carriers", response_class=JSONResponse)
async def api_list_carriers(
    request: Request,
    q: Optional[str] = None,
    ownership: Optional[str] = "all",
    capacity: Optional[str] = None,
    equipment: Optional[List[str]] = Query(None),
    authority: Optional[List[str]] = Query(None),
    country: Optional[List[str]] = Query(None),
    relationship: Optional[List[str]] = Query(None),
    cross_border: Optional[List[str]] = Query(None),
    source: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str = "name",
    sort_dir: str = "asc",
):
    user = getattr(request.state, "user", None)
    user_id = user["id"] if user else None
    with closing(create_connection()) as conn:
        result = list_carriers(
            conn,
            search=q,
            ownership=ownership,
            user_id=user_id,
            authority=authority,
            equipment=equipment,
            country=country,
            capacity=capacity,
            relationship=relationship,
            cross_border=cross_border,
            source=source,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    return JSONResponse(content=result)


@carrier_router.post("/api/carriers", response_class=JSONResponse)
async def api_create_carrier(request: Request, req: CarrierCreateRequest):
    user = getattr(request.state, "user", None)
    user_id = user["id"] if user else 1
    with closing(create_connection()) as conn:
        carrier = create_or_update_carrier(conn, req.model_dump(), user_id=user_id)
    return JSONResponse(status_code=201, content=carrier)


@carrier_router.get("/api/carriers/summary", response_class=JSONResponse)
async def api_carrier_summary(request: Request):
    user = getattr(request.state, "user", None)
    user_id = user["id"] if user else None
    with closing(create_connection()) as conn:
        counts = get_carrier_summary_counts(conn, user_id=user_id)
    return JSONResponse(content=counts)


@carrier_router.get("/api/carriers/adapters", response_class=JSONResponse)
async def api_carrier_adapters():
    return JSONResponse(content=list_carrier_adapters())


@carrier_router.get("/api/carriers/verify/fmcsa", response_class=JSONResponse)
async def api_verify_fmcsa(usdot: Optional[str] = None, mc: Optional[str] = None):
    adapter = get_carrier_adapter("FMCSA")
    if not adapter:
        raise HTTPException(500, "FMCSA adapter not found")
    res = adapter.lookup_carrier(usdot=usdot, mc=mc)
    if not res:
        raise HTTPException(400, "Provide USDOT or MC number for FMCSA lookup.")
    return JSONResponse(content=res)


@carrier_router.get("/api/carriers/{carrier_id}", response_class=JSONResponse)
async def api_get_carrier(carrier_id: int):
    with closing(create_connection()) as conn:
        carrier = get_carrier_by_id(conn, carrier_id)
        if not carrier:
            raise HTTPException(status_code=404, detail="Carrier not found.")
        contacts = get_carrier_contacts(conn, carrier_id)
        lanes = get_carrier_lanes(conn, carrier_id)
        capacity = list_capacity_postings(conn, carrier_id=carrier_id, active_only=False)
        outreach = get_carrier_outreach_history(conn, carrier_id)
        quotes = get_carrier_quotes(conn, carrier_id=carrier_id)
        assignment_history = get_carrier_owner(conn, carrier_id)

    return JSONResponse(content={
        "carrier": carrier,
        "contacts": contacts,
        "lanes": lanes,
        "capacity_postings": capacity["items"],
        "outreach_history": outreach,
        "quotes": quotes,
        "ownership": assignment_history,
    })


@carrier_router.post("/api/carriers/{carrier_id}/assign", response_class=JSONResponse)
async def api_assign_carrier(request: Request, carrier_id: int, req: CarrierAssignRequest):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in.")
    with closing(create_connection()) as conn:
        if req.action == "claim":
            res = claim_carrier(conn, carrier_id, user["id"])
        elif req.action == "transfer":
            if user.get("role") != "ADMIN":
                assert_carrier_owner_or_admin(conn, carrier_id, user)
            if not req.target_id:
                raise HTTPException(status_code=400, detail="Target user ID required for transfer.")
            res = transfer_carrier(conn, carrier_id, actor_id=user["id"], target_id=req.target_id, note=req.note or "")
        elif req.action == "release":
            assert_carrier_owner_or_admin(conn, carrier_id, user)
            release_carrier(conn, carrier_id, actor_id=user["id"], note=req.note or "")
            res = {"status": "released", "carrier_id": carrier_id}
        else:
            raise HTTPException(status_code=400, detail="Invalid assignment action.")
    return JSONResponse(content=res)


@carrier_router.post("/api/carriers/{carrier_id}/outreach", response_class=JSONResponse)
async def api_log_carrier_call(request: Request, carrier_id: int, req: CarrierOutreachRequest):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in.")
    with closing(create_connection()) as conn:
        # Check carrier suppression
        sup = check_carrier_suppression(conn, carrier_id=carrier_id, contact_id=req.contact_id)
        if sup and sup.get("suppression_status") in ("DO_NOT_CONTACT", "DO_NOT_USE"):
            raise HTTPException(status_code=403, detail=f"Carrier outreach blocked: {sup.get('reason_notes')}")

        assert_carrier_owner_or_admin(conn, carrier_id, user)

        res = log_carrier_outreach_call(
            conn,
            carrier_id=carrier_id,
            user_id=user["id"],
            disposition=req.disposition,
            notes=req.notes,
            contact_id=req.contact_id,
            callback_date=req.callback_date,
            callback_time=req.callback_time,
            quoted_rate=req.quoted_rate,
            quoted_rate_currency=req.quoted_rate_currency,
            facility_location=req.facility_location,
            load_id=req.load_id,
            capacity_id=req.capacity_id,
        )
    return JSONResponse(status_code=201, content=res)


@carrier_router.post("/api/carriers/{carrier_id}/clear-status", response_class=JSONResponse)
async def api_clear_carrier_status(request: Request, carrier_id: int):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in.")
    with closing(create_connection()) as conn:
        assert_carrier_owner_or_admin(conn, carrier_id, user)
        res = clear_carrier_relationship(conn, carrier_id=carrier_id, user_id=user["id"])
    return JSONResponse(content=res)


@carrier_router.post("/api/carriers/{carrier_id}/contacts", response_class=JSONResponse)
async def api_add_carrier_contact(request: Request, carrier_id: int, req: CarrierContactRequest):
    user = getattr(request.state, "user", None)
    user_id = user["id"] if user else 1
    with closing(create_connection()) as conn:
        res = add_carrier_contact(conn, carrier_id=carrier_id, data=req.model_dump(), user_id=user_id)
    return JSONResponse(status_code=201, content=res)


@carrier_router.post("/api/carriers/{carrier_id}/lanes", response_class=JSONResponse)
async def api_add_carrier_lane(carrier_id: int, req: CarrierLaneRequest):
    with closing(create_connection()) as conn:
        res = add_carrier_lane(conn, carrier_id=carrier_id, data=req.model_dump())
    return JSONResponse(status_code=201, content=res)


@carrier_router.post("/api/carriers/{carrier_id}/capacity", response_class=JSONResponse)
async def api_add_carrier_capacity(request: Request, carrier_id: int, req: CapacityPostRequest):
    user = getattr(request.state, "user", None)
    user_id = user["id"] if user else 1
    with closing(create_connection()) as conn:
        res = add_capacity_posting(conn, carrier_id=carrier_id, data=req.model_dump(), user_id=user_id)
    return JSONResponse(status_code=201, content=res)


@carrier_router.post("/api/carriers/{carrier_id}/suppress", response_class=JSONResponse)
async def api_suppress_carrier(request: Request, carrier_id: int, req: CarrierSuppressRequest):
    user = getattr(request.state, "user", None)
    username = user["username"] if user else "USER"
    with closing(create_connection()) as conn:
        res = add_carrier_suppression(
            conn,
            scope_type=req.scope_type,
            reason_notes=req.reason_notes,
            carrier_id=carrier_id if req.scope_type == "CARRIER" else None,
            contact_id=req.contact_id,
            origin_state=req.origin_state,
            dest_state=req.dest_state,
            suppression_status=req.suppression_status,
            assigned_by=username,
        )
    return JSONResponse(status_code=201, content=res)


@carrier_router.delete("/api/carriers/{carrier_id}/suppressions/{suppression_id}", response_class=JSONResponse)
@carrier_router.post("/api/carriers/{carrier_id}/suppressions/{suppression_id}/remove", response_class=JSONResponse)
async def api_remove_carrier_suppression(carrier_id: int, suppression_id: int):
    with closing(create_connection()) as conn:
        removed = remove_carrier_suppression(conn, suppression_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Suppression not found")
    return JSONResponse(content={"success": True, "suppression_id": suppression_id})


@carrier_router.get("/api/capacity", response_class=JSONResponse)
async def api_list_capacity(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    available_date: Optional[str] = None,
    country: Optional[List[str]] = Query(None),
    equipment: Optional[List[str]] = Query(None),
    carrier_id: Optional[int] = None,
    active_only: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    with closing(create_connection()) as conn:
        res = list_capacity_postings(
            conn,
            origin=origin,
            destination=destination,
            available_date=available_date,
            equipment=equipment,
            country=country,
            carrier_id=carrier_id,
            active_only=active_only,
            page=page,
            page_size=page_size,
        )
    return JSONResponse(content=res)


@carrier_router.get("/api/loads", response_class=JSONResponse)
async def api_list_loads():
    with closing(create_connection()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM load_opportunities ORDER BY id DESC").fetchall()
    return JSONResponse(content={"items": [dict(r) for r in rows]})


@carrier_router.post("/api/loads", response_class=JSONResponse)
async def api_create_load(req: LoadCreateRequest):
    with closing(create_connection()) as conn:
        cur = conn.cursor()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        fac_id = req.facility_id
        if not fac_id:
            # Fallback to facility 1 if not specified
            fac_row = cur.execute("SELECT id FROM facilities LIMIT 1").fetchone()
            fac_id = fac_row[0] if fac_row else 1

        gross_margin = None
        margin_pct = None
        if req.shipper_target_rate is not None and req.carrier_target_cost is not None:
            gross_margin = round(req.shipper_target_rate - req.carrier_target_cost, 2)
            if req.shipper_target_rate > 0:
                margin_pct = round((gross_margin * 100.0) / req.shipper_target_rate, 2)

        cur.execute("""
            INSERT INTO load_opportunities (
                facility_id, load_status, origin_city, origin_state_prov,
                origin_country, dest_city, dest_state_prov, dest_country,
                pickup_date_earliest, pickup_date_latest, equipment_required,
                weight_lbs, shipper_target_rate, carrier_target_cost,
                gross_margin, margin_pct, confirmed_at, expires_at,
                event_at, observed_at, created_at
            ) VALUES (?, 'CONFIRMED_AVAILABLE_NOW', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            fac_id, req.origin_city, req.origin_state_prov, req.origin_country,
            req.dest_city, req.dest_state_prov, req.dest_country,
            req.pickup_date_earliest, req.pickup_date_latest or req.pickup_date_earliest,
            req.equipment_required, req.weight_lbs, req.shipper_target_rate,
            req.carrier_target_cost, gross_margin, margin_pct,
            now, f"{req.pickup_date_earliest}T23:59:59Z", now, now, now
        ))
        conn.commit()
        load_id = cur.lastrowid
        conn.row_factory = sqlite3.Row
        load = dict(cur.execute("SELECT * FROM load_opportunities WHERE id = ?", (load_id,)).fetchone())
    return JSONResponse(status_code=201, content=load)


@carrier_router.get("/api/loads/{load_id}/matches", response_class=JSONResponse)
async def api_get_load_matches(load_id: int):
    with closing(create_connection()) as conn:
        res = find_capacity_matches_for_load(conn, load_id=load_id)
    return JSONResponse(content=res)


@carrier_router.post("/api/loads/{load_id}/matches/{capacity_id}/status", response_class=JSONResponse)
async def api_update_match_status(request: Request, load_id: int, capacity_id: int, req: MatchStatusUpdateRequest):
    user = getattr(request.state, "user", None)
    user_id = user["id"] if user else 1
    with closing(create_connection()) as conn:
        res = update_load_match_status(
            conn,
            load_id=load_id,
            capacity_posting_id=capacity_id,
            new_status=req.status,
            user_id=user_id,
            quoted_amount=req.quoted_amount,
            notes=req.notes or "",
        )
    return JSONResponse(content=res)


@carrier_router.post("/api/loads/{load_id}/quotes", response_class=JSONResponse)
async def api_create_quote(request: Request, load_id: int, req: QuoteCreateRequest):
    user = getattr(request.state, "user", None)
    user_id = user["id"] if user else 1
    with closing(create_connection()) as conn:
        res = add_carrier_quote(
            conn,
            carrier_id=req.carrier_id,
            load_id=load_id,
            author_user_id=user_id,
            quoted_amount=req.quoted_amount,
            rate_basis=req.rate_basis,
            currency=req.currency,
            notes=req.notes or "",
            capacity_id=req.capacity_id,
        )
    return JSONResponse(status_code=201, content=res)


class CarrierQuoteCreateRequest(BaseModel):
    load_id: Optional[int] = None
    amount: Optional[float] = None
    quoted_amount: Optional[float] = None
    currency: str = "USD"
    rate_basis: str = "FLAT"
    notes: Optional[str] = ""
    capacity_id: Optional[int] = None


@carrier_router.post("/api/carriers/{carrier_id}/quotes", response_class=JSONResponse)
async def api_create_carrier_quote(request: Request, carrier_id: int, req: CarrierQuoteCreateRequest):
    user = getattr(request.state, "user", None)
    user_id = user["id"] if user else 1
    amount = req.quoted_amount if req.quoted_amount is not None else (req.amount or 0.0)
    with closing(create_connection()) as conn:
        res = add_carrier_quote(
            conn,
            carrier_id=carrier_id,
            load_id=req.load_id,
            author_user_id=user_id,
            quoted_amount=amount,
            rate_basis=req.rate_basis,
            currency=req.currency,
            notes=req.notes or "",
            capacity_id=req.capacity_id,
        )
    return JSONResponse(status_code=201, content=res)
