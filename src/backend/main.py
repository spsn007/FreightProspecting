"""
FreightProspecting V1 — Application Server (Stage 2.5 Preview)
FastAPI Entry Point • Read-Only Page Routes • Local Jinja2 + Alpine.js
Zero External CDN Dependencies • Zero Paid AI Keys • Local SQLite WAL
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from src.backend.db.connection import check_database_health
from src.backend.db.validators import normalize_to_utc_iso, validate_date_string, sanitize_url, validate_iso_timestamp
from src.backend.db.queries import (
    SuppressionBlockedError,
    evaluate_qualification_readiness,
    get_company_grouped_prospects,
    get_crm_counts,
    get_crm_follow_ups,
    get_crm_prospects,
    get_evidence_sources_list,
    get_outreach_history,
    get_prospect_detail,
    get_prospects_list,
    get_summary_counts,
    get_system_settings,
    get_taxonomy_overview,
    get_commodity_families,
    get_commodity_categories,
    log_outreach_call,
    mark_prospect_viewed,
    promote_prospect_stage,
    check_lane_suppression_warning,
    get_universe_metadata,
)

logger = logging.getLogger("freightprospecting")

# Project paths
PROJECT_ROOT = Path("D:/FreightProspecting")
STATIC_DIR = PROJECT_ROOT / "src" / "frontend" / "static"
TEMPLATES_DIR = PROJECT_ROOT / "src" / "frontend" / "templates"

# Initialize FastAPI Application
app = FastAPI(
    title="FreightProspecting V1",
    description="Local Browser Application for Freight Brokerage Prospecting & Evidence Tracking",
    version="1.0.0",
)

# Mount Static Files (CSS, local Alpine.js vendor)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount Jinja2 Templates & Register Filters
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["safe_url"] = lambda u: sanitize_url(u) or ""


@app.exception_handler(FileNotFoundError)
async def file_not_found_exception_handler(request: Request, exc: FileNotFoundError):
    """
    AUD-021: Handle missing database file gracefully without creating empty files.
    Returns HTTP 503 Service Unavailable across all routes.
    """
    err_msg = str(exc)
    if "prospects.db" in err_msg or "Database file not found" in err_msg:
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=503, content={"error": err_msg, "healthy": False})
        return HTMLResponse(
            status_code=503,
            content=f"""
            <!DOCTYPE html>
            <html>
            <head><title>503 Service Unavailable — FreightProspecting</title></head>
            <body style="font-family:sans-serif; padding:40px; text-align:center; background:#f8fafc; color:#1e293b;">
                <h1>503 Service Unavailable</h1>
                <p><strong>{err_msg}</strong></p>
                <p>Please initialize the database or restore from a validated backup before accessing the application.</p>
            </body>
            </html>
            """
        )
    raise exc


def verify_mutation_origin(request: Request) -> None:
    """
    AUD-013: Security boundary on mutating endpoints.
    Protects against Cross-Site Request Forgery (CSRF) and untrusted origin calls.
    Ensures mutating requests come from local loopback with matching Origin/Host.
    Hardened against Host header injection / forgery.
    """
    client_host = request.client.host if request.client else "127.0.0.1"
    is_loopback = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
    if not is_loopback:
        raise HTTPException(status_code=403, detail="Mutating endpoints are restricted to local loopback access.")

    # Modern Fetch Metadata boundary: reject any request explicitly tagged cross-site
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site and sec_fetch_site.lower() == "cross-site":
        raise HTTPException(status_code=403, detail="Cross-site requests are strictly prohibited.")

    LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1", "testclient", "testserver"}

    host = request.headers.get("host")
    if host:
        host_hostname = host.split(":")[0].strip().lower()
        if host_hostname not in LOOPBACK_HOSTS:
            raise HTTPException(
                status_code=403,
                detail=f"Untrusted Host header '{host}'. Mutating requests must target local loopback host."
            )

    origin = request.headers.get("origin")
    if origin:
        try:
            origin_parsed = urllib.parse.urlparse(origin)
            origin_hostname = (origin_parsed.hostname or origin.split("://")[-1].split(":")[0]).strip().lower()
            if origin_hostname not in LOOPBACK_HOSTS:
                raise HTTPException(
                    status_code=403,
                    detail=f"Cross-origin request rejected: Origin '{origin}' is not a local loopback origin."
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=403, detail="Malformed origin header.")

    referer = request.headers.get("referer")
    if referer:
        try:
            ref_parsed = urllib.parse.urlparse(referer)
            ref_hostname = (ref_parsed.hostname or referer.split("://")[-1].split(":")[0]).strip().lower()
            if ref_hostname not in LOOPBACK_HOSTS:
                raise HTTPException(
                    status_code=403,
                    detail=f"Cross-origin referer rejected: Referer '{referer}' is not a local loopback referer."
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=403, detail="Malformed referer header.")


# ============================================================================
# Page Routes (Read-Only HTML Views)
# ============================================================================

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def dashboard_cockpit_page(
    request: Request,
    tier: Optional[str] = None,
):
    """
    Screen 1: Shortlist Cockpit (Hero Dashboard)
    Renders top metrics and the curated broker priority shortlist (default: Tier A Priority Prospects).
    """
    counts = get_summary_counts()
    universe_meta = get_universe_metadata()
    actionable_tiers = {"TIER_A_PRIORITY", "TIER_B_WORTH_CALLING", "TIER_C_SECONDARY"}
    all_facs = get_prospects_list(lifecycle_stage="ALL")
    actionable_facs = [f for f in all_facs if f.get("opportunity_tier") in actionable_tiers]
    default_tier = tier.upper() if tier else "TIER_A_PRIORITY"

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "counts": counts,
            "prospects": actionable_facs,
            "active_nav": "cockpit",
            "active_tier": default_tier,
            "opportunity_counts": universe_meta.get("opportunity_counts", {}),
            "facility_opportunity_counts": universe_meta.get("facility_opportunity_counts", {}),
        },
    )


@app.get("/prospects", response_class=HTMLResponse)
async def master_directory_page(
    request: Request,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=500),
    q: Optional[str] = None,
    stage: Optional[str] = "ALL",
    tier: Optional[str] = None,
    friction: Optional[str] = None,
    equipment: Optional[str] = None,
    family: Optional[str] = None,
    category: Optional[str] = None,
    seasonality: Optional[str] = None,
    structure: Optional[str] = None,
    facility_count: Optional[str] = None,
    fleet: Optional[str] = None,
    carrier: Optional[str] = None,
    procurement: Optional[str] = None,
    outreach: Optional[str] = None,
    unreviewed: bool = False,
):
    """
    Screen 2: Master Directory (Company-Grouped & Flat Facility Views)
    Renders searchable, filterable directory with Company View (default)
    and Flat Facility View, supporting Broker Access Friction heuristic.
    Supports server-side filtering and pagination.
    """
    effective_page = page if page is not None else 1
    effective_page_size = page_size if page_size is not None else 25

    counts = get_summary_counts()
    universe_meta = get_universe_metadata()
    prospects = get_prospects_list(
        lifecycle_stage=stage,
        tier=tier,
        page=effective_page,
        page_size=effective_page_size,
        search=q,
        equipment=equipment,
        family=family,
        category=category,
        seasonality=seasonality,
        fleet=fleet,
        carrier=carrier,
        procurement=procurement,
    )
    company_groups = get_company_grouped_prospects(
        lifecycle_stage=stage,
        tier=tier,
        outreach_filter=outreach,
        unreviewed_only=unreviewed,
        page=effective_page,
        page_size=effective_page_size,
        search=q,
        friction=friction,
        equipment=equipment,
        family=family,
        category=category,
        seasonality=seasonality,
        structure=structure,
        facility_count=facility_count,
        fleet=fleet,
        carrier=carrier,
        procurement=procurement,
    )
    taxonomy_overview = get_taxonomy_overview()
    commodity_families = get_commodity_families()
    commodity_categories = get_commodity_categories()

    prospects_data = prospects.get("items", prospects) if isinstance(prospects, dict) else prospects
    companies_data = company_groups.get("items", company_groups) if isinstance(company_groups, dict) else company_groups
    pagination_info = company_groups if isinstance(company_groups, dict) else None
    metadata_info = company_groups.get("metadata", {}) if isinstance(company_groups, dict) else {}

    return templates.TemplateResponse(
        request=request,
        name="prospects.html",
        context={
            "counts": counts,
            "prospects": prospects_data,
            "company_groups": companies_data,
            "pagination": pagination_info,
            "metadata": metadata_info,
            "opportunity_counts": universe_meta.get("opportunity_counts", {}),
            "facility_opportunity_counts": universe_meta.get("facility_opportunity_counts", {}),
            "filters": {
                "q": q or "",
                "stage": stage or "ALL",
                "tier": tier or "ALL",
                "friction": friction or "ALL",
                "equipment": equipment or "ALL",
                "family": family or "ALL",
                "category": category or "ALL",
                "seasonality": seasonality or "ALL",
                "structure": structure or "ALL",
                "facility_count": facility_count or "ALL",
                "fleet": fleet or "ALL",
                "carrier": carrier or "ALL",
                "procurement": procurement or "ALL",
                "outreach": outreach or "ALL",
                "unreviewed": unreviewed,
            },
            "taxonomy_overview": taxonomy_overview,
            "commodity_families": commodity_families,
            "commodity_categories": commodity_categories,
            "active_nav": "prospects",
        },
    )


@app.get("/api/taxonomy/overview", response_class=JSONResponse)
async def api_taxonomy_overview():
    """
    Returns full hierarchical taxonomy overview with family & category metrics.
    """
    return JSONResponse(content=get_taxonomy_overview())


@app.get("/api/taxonomy/families", response_class=JSONResponse)
async def api_commodity_families(include_inactive: bool = False):
    """
    Returns active commodity families list.
    """
    return JSONResponse(content=get_commodity_families(include_inactive=include_inactive))


@app.get("/api/taxonomy/categories", response_class=JSONResponse)
async def api_commodity_categories(family_code: Optional[str] = None, include_deferred: bool = False):
    """
    Returns commodity categories list, optionally filtered by family_code.
    """
    return JSONResponse(content=get_commodity_categories(family_code=family_code, include_deferred=include_deferred))


@app.get("/prospects/{facility_id}", response_class=HTMLResponse)
async def prospect_detail_page(request: Request, facility_id: int):
    """
    Prospect Detail View (7-Question Structured Inspection)
    Answers Who is this, What do they make, Why care, Who to contact,
    What is known, Do we have freight, and What next.
    AUD-020: Read-only GET request; does NOT mutate viewed engagement state.
    """
    prospect = get_prospect_detail(facility_id)
    if not prospect:
        raise HTTPException(status_code=404, detail=f"Prospect facility {facility_id} not found")

    counts = get_summary_counts()

    return templates.TemplateResponse(
        request=request,
        name="prospect_detail.html",
        context={
            "counts": counts,
            "prospect": prospect,
            "active_nav": "prospects",
        },
    )


@app.get("/loads", response_class=HTMLResponse)
async def loads_margins_page(request: Request):
    """
    Screen 3: Loads & Margins (Discrete Opportunities)
    Renders truthful, honest empty state with zero fake loads.
    """
    counts = get_summary_counts()
    return templates.TemplateResponse(
        request=request,
        name="loads.html",
        context={
            "counts": counts,
            "active_nav": "loads",
        },
    )


@app.get("/carriers", response_class=HTMLResponse)
async def carriers_capacity_page(request: Request):
    """
    Screen 4: Carriers & Capacity Postings
    Renders truthful, honest empty state with zero fake trucks.
    """
    counts = get_summary_counts()
    return templates.TemplateResponse(
        request=request,
        name="carriers.html",
        context={
            "counts": counts,
            "active_nav": "carriers",
        },
    )


@app.get("/research", response_class=HTMLResponse)
async def research_evidence_ledger_page(request: Request):
    """
    Screen 5/Research: Evidence Sources & Provenance Ledger
    Displays all 10 verified primary evidence records.
    """
    counts = get_summary_counts()
    sources = get_evidence_sources_list()
    return templates.TemplateResponse(
        request=request,
        name="research.html",
        context={
            "counts": counts,
            "sources": sources,
            "active_nav": "research",
        },
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_controls_page(request: Request):
    """
    Screen 5: Settings & Geo Controls
    Displays system settings, Decision A (Alaska), Decision B (Phone-First), Decision H (No-Paid-AI).
    """
    settings = get_system_settings()
    counts = get_summary_counts()
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "settings": settings,
            "counts": counts,
            "active_nav": "settings",
        },
    )


# ============================================================================
# Stage 3C — CRM Workflow Page Routes
# ============================================================================

@app.get("/crm/interested", response_class=HTMLResponse)
async def crm_interested_page(request: Request):
    """Screen: Interested Prospects (Confirmed interest in freight brokerage)."""
    counts = get_summary_counts()
    prospects = get_crm_prospects(status="INTERESTED")
    return templates.TemplateResponse(
        request=request,
        name="crm_workflow.html",
        context={
            "counts": counts,
            "prospects": prospects,
            "workflow_status": "INTERESTED",
            "workflow_title": "Interested Prospects",
            "workflow_desc": "Shippers with confirmed interest in working with freight brokerage.",
            "active_nav": "crm_interested",
        },
    )


@app.get("/crm/follow-ups", response_class=HTMLResponse)
async def crm_follow_ups_page(request: Request, tz: Optional[str] = None):
    """Screen: Follow-Ups Workflow (Categorized into Overdue, Today, Upcoming)."""
    counts = get_summary_counts()
    follow_ups = get_crm_follow_ups(user_timezone=tz)
    return templates.TemplateResponse(
        request=request,
        name="crm_follow_ups.html",
        context={
            "counts": counts,
            "follow_ups": follow_ups,
            "user_timezone": tz or follow_ups.get("user_timezone", "local"),
            "active_nav": "crm_follow_ups",
        },
    )


@app.get("/crm/no-answer", response_class=HTMLResponse)
async def crm_no_answer_page(request: Request):
    """Screen: No Answer Queue (Shows verified attempt count and last attempt date)."""
    counts = get_summary_counts()
    prospects = get_crm_prospects(status="NO_ANSWER")
    return templates.TemplateResponse(
        request=request,
        name="crm_workflow.html",
        context={
            "counts": counts,
            "prospects": prospects,
            "workflow_status": "NO_ANSWER",
            "workflow_title": "No Answer Queue",
            "workflow_desc": "Prospects where calls went unanswered or voicemail was left. Shows verified attempt counter.",
            "active_nav": "crm_no_answer",
        },
    )


@app.get("/crm/not-interested", response_class=HTMLResponse)
async def crm_not_interested_page(request: Request):
    """Screen: Not Interested (Preserved for future re-engagement; NOT suppressed / NOT DNC)."""
    counts = get_summary_counts()
    prospects = get_crm_prospects(status="NOT_INTERESTED")
    return templates.TemplateResponse(
        request=request,
        name="crm_workflow.html",
        context={
            "counts": counts,
            "prospects": prospects,
            "workflow_status": "NOT_INTERESTED",
            "workflow_title": "Not Interested (Active / Not DNC)",
            "workflow_desc": "Shippers who declined at this time. Preserved for future check-ins; NOT placed on Do-Not-Contact or suppressed.",
            "active_nav": "crm_not_interested",
        },
    )


# ============================================================================
# API Endpoints (Read-Only & Stage 3C Outreach CRM Mutations)
# ============================================================================

ALLOWED_CALL_DISPOSITIONS = {
    "INTERESTED", "NOT_INTERESTED", "NO_ANSWER", "CALL_BACK",
    "CONNECTED_DECISION_MAKER", "CONNECTED_GATEKEEPER", "LEFT_VOICEMAIL", "WRONG_CONTACT"
}


class LogCallRequest(BaseModel):
    company_id: int
    facility_id: Optional[int] = None
    contact_id: Optional[int] = None
    disposition: str = "NO_ANSWER"
    feedback_notes: Optional[str] = None
    follow_up_date: Optional[str] = None
    follow_up_time: Optional[str] = None
    follow_up_at: Optional[str] = None
    contacted_at: Optional[str] = None
    channel: str = "PHONE"
    origin_state_prov: Optional[str] = None
    dest_state_prov: Optional[str] = None
    user_timezone: Optional[str] = None

    @field_validator("disposition")
    @classmethod
    def validate_disposition(cls, v: str) -> str:
        clean = (v or "").strip().upper()
        if clean not in ALLOWED_CALL_DISPOSITIONS:
            raise ValueError(f"Invalid disposition '{v}'. Allowed: {sorted(ALLOWED_CALL_DISPOSITIONS)}")
        return clean

    @field_validator("contacted_at")
    @classmethod
    def validate_contacted_at(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return normalize_to_utc_iso(v, "contacted_at")
        return None

    @field_validator("follow_up_date")
    @classmethod
    def validate_follow_up_date(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return validate_date_string(v, "follow_up_date")
        return None

    @field_validator("follow_up_at")
    @classmethod
    def validate_follow_up_at(cls, v: Optional[str]) -> Optional[str]:
        if v:
            validate_iso_timestamp(v, "follow_up_at")
            return v.strip()
        return None

    @field_validator("feedback_notes")
    @classmethod
    def validate_feedback_notes(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v) > 5000:
            raise ValueError("feedback_notes exceeds maximum length of 5000 characters")
        return v


@app.get("/api/health", response_class=JSONResponse)
async def api_health():
    """AUD-021: Returns database health status and diagnostic checks."""
    health = check_database_health()
    status_code = 200 if health["healthy"] else 503
    return JSONResponse(status_code=status_code, content=health)


@app.get("/api/summary", response_class=JSONResponse)
async def api_summary_counts():
    """Returns actual summary counts as JSON."""
    health = check_database_health()
    if not health["healthy"]:
        raise HTTPException(status_code=503, detail=health["error"])
    return get_summary_counts()


@app.get("/api/prospects", response_class=JSONResponse)
async def api_prospects_list(
    stage: Optional[str] = "SHORTLISTED",
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=500),
    q: Optional[str] = None,
    equipment: Optional[str] = None,
    family: Optional[str] = None,
    category: Optional[str] = None,
    seasonality: Optional[str] = None,
    fleet: Optional[str] = None,
    carrier: Optional[str] = None,
    procurement: Optional[str] = None,
):
    """Returns prospect facilities filtered by lifecycle stage (default: SHORTLISTED) with pagination/search/filters."""
    return get_prospects_list(
        lifecycle_stage=stage,
        page=page,
        page_size=page_size,
        search=q,
        equipment=equipment,
        family=family,
        category=category,
        seasonality=seasonality,
        fleet=fleet,
        carrier=carrier,
        procurement=procurement,
    )


@app.get("/api/companies", response_class=JSONResponse)
async def api_companies_list(
    stage: Optional[str] = "ALL",
    outreach: Optional[str] = None,
    unreviewed: bool = False,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=500),
    q: Optional[str] = None,
    friction: Optional[str] = None,
    equipment: Optional[str] = None,
    family: Optional[str] = None,
    category: Optional[str] = None,
    seasonality: Optional[str] = None,
    structure: Optional[str] = None,
    facility_count: Optional[str] = None,
    fleet: Optional[str] = None,
    carrier: Optional[str] = None,
    procurement: Optional[str] = None,
):
    """Returns company-grouped prospects with child facilities, facts, and broker access friction with pagination/search/filters."""
    return get_company_grouped_prospects(
        lifecycle_stage=stage,
        outreach_filter=outreach,
        unreviewed_only=unreviewed,
        page=page,
        page_size=page_size,
        search=q,
        friction=friction,
        equipment=equipment,
        family=family,
        category=category,
        seasonality=seasonality,
        structure=structure,
        facility_count=facility_count,
        fleet=fleet,
        carrier=carrier,
        procurement=procurement,
    )


@app.get("/api/prospects/{facility_id}", response_class=JSONResponse)
async def api_prospect_detail(facility_id: int):
    """
    Returns full prospect profile and claims ledger as JSON.
    Note: API read does not mutate viewed engagement state; to record operator view,
    explicitly call POST /api/viewed/{company_id}.
    """
    prospect = get_prospect_detail(facility_id)
    if not prospect:
        raise HTTPException(status_code=404, detail=f"Prospect facility {facility_id} not found")
    return prospect


@app.get("/api/prospects/{facility_id}/qualification", response_class=JSONResponse)
async def api_prospect_qualification(facility_id: int):
    """Returns deterministic qualification readiness evaluation for a facility."""
    readiness = evaluate_qualification_readiness(facility_id)
    return readiness


@app.post("/api/outreach", response_class=JSONResponse, dependencies=[Depends(verify_mutation_origin)])
async def api_log_outreach_call(req: LogCallRequest):
    """
    Stage 3C CRM: Log an outreach call (append-only history + engagement state projection).
    Blocks with HTTP 403 Forbidden if prospect is suppressed (DNC / protected / restricted)
    or if origin violates local loopback boundary.
    """
    try:
        fu_at = req.follow_up_at
        if not fu_at and req.follow_up_date:
            time_part = req.follow_up_time or "09:00"
            fu_at = f"{req.follow_up_date}T{time_part}:00"

        res = log_outreach_call(
            company_id=req.company_id,
            facility_id=req.facility_id,
            contact_id=req.contact_id,
            disposition=req.disposition,
            feedback_notes=req.feedback_notes,
            follow_up_at=fu_at,
            contacted_at=req.contacted_at,
            channel=req.channel,
            origin_state_prov=req.origin_state_prov,
            dest_state_prov=req.dest_state_prov,
            user_timezone=req.user_timezone,
        )
        return JSONResponse(status_code=201, content={"status": "success", "data": res})
    except SuppressionBlockedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record call: {str(e)}")


@app.get("/api/outreach/history", response_class=JSONResponse)
async def api_outreach_history(company_id: Optional[int] = None, facility_id: Optional[int] = None):
    """Returns append-only outreach timeline."""
    history = get_outreach_history(company_id=company_id, facility_id=facility_id)
    return history


@app.post("/api/viewed/{company_id}", response_class=JSONResponse, dependencies=[Depends(verify_mutation_origin)])
async def api_mark_viewed(company_id: int):
    """
    Marks a company prospect as viewed in the engagement projection.
    Protected by local origin verification.
    """
    try:
        res = mark_prospect_viewed(company_id=company_id)
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class StageUpdateRequest(BaseModel):
    stage: str
    notes: Optional[str] = None


@app.post("/api/prospects/{facility_id}/stage", response_class=JSONResponse, dependencies=[Depends(verify_mutation_origin)])
async def api_update_prospect_stage(facility_id: int, req: StageUpdateRequest):
    """
    Promotes or updates lifecycle stage for a prospect facility.
    Enforces strict qualification readiness guard for QUALIFIED and SHORTLISTED stages.
    Protected by local loopback origin verification.
    """
    try:
        res = promote_prospect_stage(
            facility_id=facility_id,
            target_stage=req.stage,
            notes=req.notes,
        )
        return JSONResponse(status_code=200, content={"status": "success", "data": res})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update stage: {str(e)}")


@app.get("/api/suppressions/check", response_class=JSONResponse)
async def api_check_lane_suppression(
    company_id: Optional[int] = Query(None),
    facility_id: Optional[int] = Query(None),
    origin: Optional[str] = Query(None),
    destination: Optional[str] = Query(None),
    origin_state: Optional[str] = Query(None),
    dest_state: Optional[str] = Query(None),
):
    """
    Checks for active company, facility, or lane suppressions.
    Returns warning message and restriction status for outreach operator safety.
    """
    orig = origin or origin_state
    dest = destination or dest_state
    res = check_lane_suppression_warning(
        company_id=company_id,
        facility_id=facility_id,
        origin_state_prov=orig,
        dest_state_prov=dest,
    )
    return JSONResponse(status_code=200, content=res)
