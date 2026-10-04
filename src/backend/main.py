"""
FreightProspecting V1 — Application Server (Stage 2.5 Preview)
FastAPI Entry Point • Read-Only Page Routes • Local Jinja2 + Alpine.js
Zero External CDN Dependencies • Zero Paid AI Keys • Local SQLite WAL
"""

import logging
import os
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import urllib.parse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from src.backend import team, calling_times
from src.backend.db.connection import check_database_health, create_connection
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
    clear_outreach_tracking,
    mark_prospect_viewed,
    promote_prospect_stage,
    check_lane_suppression_warning,
    get_universe_metadata,
)

logger = logging.getLogger("freightprospecting")

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = PROJECT_ROOT / "src" / "frontend" / "static"
TEMPLATES_DIR = PROJECT_ROOT / "src" / "frontend" / "templates"

# Initialize FastAPI Application
app = FastAPI(
    title="Shipper IQ",
    description="Local Browser Application for Freight Brokerage Prospecting & Evidence Tracking",
    version="1.0.0",
)

# Mount Static Files (CSS, local Alpine.js vendor)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount Jinja2 Templates & Register Filters
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["safe_url"] = lambda u: sanitize_url(u) or ""
templates.env.globals['calling_zone'] = calling_times.zone_for

# Shared display names for the existing outreach outcomes.
OUTREACH_LABELS = {
    "UNCONTACTED": "No Active Call Status",
    "INTERESTED": "Interested",
    "CALL_BACK": "Call Back",
    "NO_ANSWER": "No Answer",
    "NOT_INTERESTED": "Not Interested",
    "CONNECTED_DECISION_MAKER": "Spoke to Shipping Contact",
    "CONNECTED_GATEKEEPER": "Spoke to Reception",
    "LEFT_VOICEMAIL": "Left Voicemail",
    "WRONG_CONTACT": "Wrong Contact / Number",
    "FOLLOW_UP": "Follow-Up Scheduled",
    "FOLLOW_UPS": "Follow-Up Scheduled",
}
templates.env.globals["outreach_labels"] = OUTREACH_LABELS
templates.env.globals["team_snapshot"] = team.snapshot
app.state.templates = templates

from src.backend.db import carrier_schema
from src.backend.carrier_routes import carrier_router
app.include_router(carrier_router)



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
            <head><title>503 Service Unavailable — Shipper IQ</title></head>
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
    """Same-origin writes only; configured hosts support a future shared deployment."""
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(403, "Cross-site requests are strictly prohibited.")
    for name in ("origin", "referer"):
        value = request.headers.get(name)
        if value:
            parsed = urllib.parse.urlsplit(value)
            if parsed.scheme != request.url.scheme or parsed.netloc.lower() != request.headers.get("host", "").lower():
                raise HTTPException(403, "Cross-origin referer rejected" if name == "referer" else "Cross-origin request rejected")


@app.middleware("http")
async def team_security(request: Request, call_next):
    allowed = {h.strip().lower() for h in os.getenv("FP_ALLOWED_HOSTS", "localhost,127.0.0.1,::1,testserver,testclient").split(",")}
    if (request.url.hostname or "").lower() not in allowed:
        return JSONResponse({"detail": "Untrusted Host header"}, status_code=403)
    if request.url.path.startswith("/static/") or request.url.path in ("/favicon.ico", "/api/health"):
        return await call_next(request)
    try:
        team.initialize()
        carrier_schema.initialize()
        user = team.session_user(request.cookies.get(team.COOKIE))
    except FileNotFoundError as exc:
        return JSONResponse({"detail": str(exc), "healthy": False}, status_code=503)
    request.state.user = user
    public = request.url.path == "/login"
    if not public and not user:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Please log in."}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    try:
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            verify_mutation_origin(request)
        if request.url.path.startswith(("/admin", "/api/admin/")) or request.url.path.endswith("/stage"):
            team.require_admin(user)
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.state.user:
        return RedirectResponse("/prospects", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    username, password = str(form.get("username", "")), str(form.get("password", ""))
    if len(username) > 50 or len(password) > 128:
        raise HTTPException(400, "Invalid login details.")
    try:
        token = team.authenticate(username, password, request.client.host if request.client else "unknown")
    except HTTPException as exc:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": exc.detail, "username": username}, status_code=exc.status_code)
    response = RedirectResponse("/prospects", status_code=303)
    response.set_cookie(team.COOKIE, token, max_age=team.SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https" or os.getenv("FP_SECURE_COOKIES") == "1", samesite="lax")
    return response


@app.post("/logout")
async def logout(request: Request):
    with closing(create_connection()) as conn, conn:
        conn.execute("DELETE FROM team_sessions WHERE token_hash=?", (team.token_digest(request.cookies.get(team.COOKIE, "")),))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(team.COOKIE)
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    state = team.snapshot()
    accounts = team.users()
    for account in accounts:
        account["company_count"] = sum(s["owner_id"] == account["id"] for s in state.values())
    return templates.TemplateResponse(request=request, name="admin.html", context={"users": accounts, "active_nav": "admin", "counts": {}})


class CreateBrokerRequest(BaseModel):
    username: str
    password: str


class UpdateBrokerRequest(BaseModel):
    action: Literal["disable", "enable", "password", "rename"]
    password: Optional[str] = None
    target_id: Optional[int] = None
    username: Optional[str] = None


@app.post("/api/admin/users", status_code=201)
async def create_broker(req: CreateBrokerRequest):
    team.create_user(req.username, req.password)
    return {"status": "success"}


@app.post("/api/admin/users/{user_id}")
async def update_broker(request: Request, user_id: int, req: UpdateBrokerRequest):
    team.update_user(request.state.user, user_id, req.action, req.password, req.target_id, req.username)
    return {"status": "success"}


class AssignmentRequest(BaseModel):
    action: Literal["claim", "release", "transfer"]
    target_id: Optional[int] = None
    note: str = ""

    @field_validator("note")
    @classmethod
    def check_note(cls, value):
        if len(value) > 2000:
            raise ValueError("Handoff note must be 2000 characters or less.")
        return value.strip()


@app.post("/api/team/companies/{company_id}")
async def update_assignment(request: Request, company_id: int, req: AssignmentRequest):
    team.assign(request.state.user, company_id, req.action, req.target_id, req.note)
    return team.snapshot()[company_id]


@app.get("/api/team/state")
async def team_state():
    return team.snapshot()


@app.get("/api/team/users")
async def team_users():
    return team.users(active_only=True)


class RescheduleFollowUpRequest(BaseModel):
    follow_up_at: str = Field(min_length=1, max_length=100)


@app.post("/api/admin/companies/{company_id}/follow-up")
async def admin_reschedule_follow_up(request: Request, company_id: int, req: RescheduleFollowUpRequest):
    team.reschedule_follow_up(request.state.user, company_id, req.follow_up_at)
    return team.snapshot()[company_id]


class ReadNotificationsRequest(BaseModel):
    keys: Optional[List[str]] = Field(default=None, max_length=1000)
    tz: str = Field(default="UTC", max_length=100)


class AnnouncementRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("title", "message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a title and message.")
        return value.strip()


@app.get("/api/notifications")
async def notification_list(request: Request, tz: str = Query("UTC", max_length=100)):
    result = team.notifications(request.state.user, tz)
    result["items"] = result["items"][:100]
    return result


@app.post("/api/notifications/read")
async def notification_read(request: Request, req: ReadNotificationsRequest):
    team.read_notifications(request.state.user, req.keys, req.tz)
    return {"status": "success"}


@app.post("/api/admin/announcements", status_code=201)
async def announcement_create(request: Request, req: AnnouncementRequest):
    return {"status": "success", "recipients": team.announce(request.state.user, req.title, req.message)}


# ============================================================================
# Page Routes (Read-Only HTML Views)
# ============================================================================

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.get("/", response_class=HTMLResponse)
async def dashboard_cockpit_page(
    request: Request,
    tier: Optional[List[str]] = Query(None),
    opportunity: Optional[List[str]] = Query(None),
):
    """
    Screen 1 / Root: Redirects canonically (HTTP 302) to Master Directory (/prospects).
    Preserves all incoming query parameters.
    """
    query_str = request.url.query
    target_url = f"/prospects?{query_str}" if query_str else "/prospects"
    return RedirectResponse(url=target_url, status_code=302)


@app.get("/prospects", response_class=HTMLResponse)
async def master_directory_page(
    request: Request,
    view: str = "companies",
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=500),
    q: Optional[str] = None,
    stage: Optional[str] = "ALL",
    tier: Optional[List[str]] = Query(None),
    opportunity: Optional[List[str]] = Query(None),
    friction: Optional[str] = None,
    equipment: Optional[List[str]] = Query(None),
    family: Optional[List[str]] = Query(None),
    category: Optional[List[str]] = Query(None),
    seasonality: Optional[List[str]] = Query(None),
    structure: Optional[List[str]] = Query(None),
    facility_count: Optional[List[str]] = Query(None),
    fleet: Optional[List[str]] = Query(None),
    carrier: Optional[List[str]] = Query(None),
    procurement: Optional[List[str]] = Query(None),
    outreach: Optional[List[str]] = Query(None),
    sort: Optional[str] = None,
    unreviewed: bool = False,
    team_view: Literal["all", "mine", "available"] = "all",
    follow_up: Optional[Literal["all", "today", "overdue", "upcoming"]] = None,
    tz: Optional[str] = None,
    calling_zone: Optional[str] = None,
    calling_now: bool = False,
    calling_start: int = Query(9, ge=0, le=23),
    calling_end: int = Query(17, ge=1, le=24),
):
    """
    Screen 2: Master Directory (Company-Grouped & Flat Facility Views)
    Renders searchable, filterable directory with Company View (default)
    and Flat Facility View, supporting canonical multi-select filters.
    Supports server-side filtering and pagination.
    """
    effective_page = page if page is not None else 1
    effective_page_size = page_size if page_size is not None else 25
    effective_tier = tier or opportunity

    if view.lower() == "facilities":
        company_only_filters = {"outreach", "unreviewed", "structure", "facility_count", "friction"}
        if any(key in request.query_params for key in company_only_filters):
            clean_query = urllib.parse.urlencode(
                [(key, value) for key, value in request.query_params.multi_items() if key not in company_only_filters]
            )
            return RedirectResponse(f"/prospects?{clean_query}", status_code=302)

    # Compute active_nav for sidebar highlighting based on outreach filter
    active_nav = "prospects"
    if outreach:
        outreach_raw = outreach if isinstance(outreach, list) else [outreach]
        outreach_items = []
        for item in outreach_raw:
            outreach_items.extend([x.strip().upper() for x in item.split(",")])
        if "INTERESTED" in outreach_items:
            active_nav = "crm_interested"
        elif any(x in ("FOLLOW_UP", "FOLLOW_UPS", "CALLBACK", "CALL_BACK") for x in outreach_items):
            active_nav = "crm_follow_ups"
        elif "NO_ANSWER" in outreach_items:
            active_nav = "crm_no_answer"
        elif "NOT_INTERESTED" in outreach_items:
            active_nav = "crm_not_interested"

    if (request.state.user["role"] == "BROKER"
            and active_nav in {"prospects", "crm_interested", "crm_follow_ups", "crm_no_answer"}
            and "team_view" not in request.query_params):
        default_team_view = "available" if active_nav == "prospects" else "mine"
        return RedirectResponse(str(request.url.include_query_params(team_view=default_team_view)), status_code=302)

    counts = get_summary_counts()
    universe_meta = get_universe_metadata()
    team_data = team.snapshot()
    allowed_ids = team.allowed_company_ids(request.state.user, team_view, team_data)
    if calling_zone and calling_zone not in calling_times.REGIONS:
        raise HTTPException(400, 'Choose a recognized time zone.')
    if calling_end <= calling_start:
        raise HTTPException(400, 'Closing time must be after opening time.')
    allowed_ids = calling_times.matching_companies(allowed_ids, calling_zone, calling_now, calling_start, calling_end)
    prospects = get_prospects_list(
        allowed_company_ids=allowed_ids,
        lifecycle_stage=stage,
        tier=effective_tier,
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
    outreach_tokens = [token.strip().upper() for value in (outreach or []) for token in value.split(",")]
    follow_up_view = view.lower() != "facilities" and (
        follow_up is not None or bool(outreach_tokens) and all(token in ("FOLLOW_UP", "FOLLOW_UPS") for token in outreach_tokens)
    )
    follow_up_counts = {}
    company_groups = get_company_grouped_prospects(
        allowed_company_ids=allowed_ids,
        lifecycle_stage=stage,
        tier=effective_tier,
        outreach_filter=["FOLLOW_UP"] if follow_up_view else outreach,
        unreviewed_only=unreviewed,
        page=1 if follow_up_view else effective_page,
        page_size=max(1, universe_meta["universe_companies"]) if follow_up_view else effective_page_size,
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
    for group in company_groups["items"]:
        group.update(team_data.get(group["company_id"], {}))
        calling_times.annotate(group, calling_zone, calling_now, calling_start, calling_end)
    if follow_up_view:
        schedule = get_crm_follow_ups(user_timezone=tz)
        groups = company_groups["items"]
        matching_ids = {group["company_id"] for group in groups}
        buckets = {key: {item["company_id"] for item in schedule[key]} & matching_ids for key in ("today", "overdue", "upcoming")}
        follow_up_counts = {key: len(ids) for key, ids in buckets.items()}
        follow_up_counts["all"] = len(groups)
        if follow_up and follow_up != "all":
            groups = [group for group in groups if group["company_id"] in buckets[follow_up]]
        groups.sort(key=lambda group: (group["next_follow_up_at"], group["company_id"]))
        total = len(groups)
        total_pages = max(1, (total + effective_page_size - 1) // effective_page_size)
        effective_page = min(effective_page, total_pages)
        start = (effective_page - 1) * effective_page_size
        metadata = company_groups["metadata"].copy()
        metadata.update(total_companies=total, total_facilities=sum(group["facility_count"] for group in groups),
                        page=effective_page, page_size=effective_page_size, total_pages=total_pages,
                        page_start=start + 1 if total else 0, page_end=min(start + effective_page_size, total))
        company_groups.update(items=groups[start:start + effective_page_size], total_count=total,
                              page=effective_page, page_size=effective_page_size, total_pages=total_pages, metadata=metadata)
    if view.lower() == 'facilities' and (calling_now or calling_zone):
        # Facility view would otherwise include other locations of a matching company.
        return RedirectResponse(str(request.url.include_query_params(view='companies')), status_code=302)
    taxonomy_overview = get_taxonomy_overview()
    commodity_families = get_commodity_families()
    commodity_categories = get_commodity_categories()

    prospects_data = prospects.get("items", prospects) if isinstance(prospects, dict) else prospects
    for facility in prospects_data:
        facility['calling_zone'] = calling_times.zone_for(facility)
    companies_data = company_groups.get("items", company_groups) if isinstance(company_groups, dict) else company_groups
    active_results = prospects if view.lower() == "facilities" else company_groups
    pagination_info = active_results if isinstance(active_results, dict) else None
    metadata_info = company_groups.get("metadata", {}).copy() if isinstance(company_groups, dict) else {}
    if view.lower() == "facilities" and isinstance(prospects, dict):
        metadata_info["total_facilities"] = prospects["total_count"]

    return templates.TemplateResponse(
        request=request,
        name="prospects.html",
        context={
            "counts": counts,
            "prospects": prospects_data,
            "company_groups": companies_data,
            "team_view": team_view,
            "follow_up_counts": follow_up_counts,
            "follow_up_view": follow_up_view,
            "pagination": pagination_info,
            "metadata": metadata_info,
            "opportunity_counts": universe_meta.get("opportunity_counts", {}),
            "facility_opportunity_counts": universe_meta.get("facility_opportunity_counts", {}),
            "filters": {
                "q": q or "",
                "stage": stage or "ALL",
                "tier": effective_tier or "ALL",
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
                "sort": sort or "name_asc",
                "unreviewed": unreviewed,
            },
            "taxonomy_overview": taxonomy_overview,
            "commodity_families": commodity_families,
            "commodity_categories": commodity_categories,
            "active_nav": active_nav,
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
async def prospect_detail_page(request: Request, facility_id: int, return_to: str = "/prospects"):
    """
    Prospect Detail View (7-Question Structured Inspection)
    Answers Who is this, What do they make, Why care, Who to contact,
    What is known, Do we have freight, and What next.
    AUD-020: Read-only GET request; does NOT mutate viewed engagement state.
    """
    prospect = get_prospect_detail(facility_id)
    if not prospect:
        raise HTTPException(status_code=404, detail=f"Prospect facility {facility_id} not found")

    prospect["team"] = team.snapshot().get(prospect["company_id"], {})
    team.add_authors(prospect.get("outreach_history", []))
    prospect["assignment_history"] = team.assignment_history(prospect["company_id"])
    prospect["team_history"] = team.add_authors(get_outreach_history(company_id=prospect["company_id"]))
    counts = get_summary_counts()
    try:
        return_parts = urllib.parse.urlsplit(return_to)
    except ValueError:
        return_to = "/prospects"
        return_parts = urllib.parse.urlsplit(return_to)
    if return_parts.scheme or return_parts.netloc or return_parts.path != "/prospects" or "\\" in return_to:
        return_to = "/prospects"

    return templates.TemplateResponse(
        request=request,
        name="prospect_detail.html",
        context={
            "counts": counts,
            "prospect": prospect,
            "return_to": return_to,
            "active_nav": "prospects",
        },
    )


@app.get('/calling-times', response_class=HTMLResponse)
async def calling_times_page(request: Request):
    return templates.TemplateResponse(request=request, name='calling_times.html',
        context={'active_nav': 'calling_times', 'regions': calling_times.REGIONS, 'zone_labels': calling_times.LABELS,
                 'country_zones': calling_times.COUNTRY_ZONES,
                 'zone_search': {zone: ('United States USA ' if zone in calling_times.US_ZONES else 'Canada Canadian ') + calling_times.LABELS[zone] + ' ' + regions + ' ' + ' '.join(city for (state, city), value in calling_times.CITIES.items() if value == zone)
                                 for zone, regions in calling_times.REGIONS.items()}})


@app.get('/api/calling-times')
async def calling_times_clock(at: Optional[str] = None):
    from datetime import datetime
    instant = None
    if at:
        try:
            instant = datetime.fromisoformat(at.replace('Z', '+00:00'))
            if instant.tzinfo is None:
                raise ValueError('Timezone required')
        except ValueError:
            raise HTTPException(400, 'Choose a valid date with a timezone.')
    try:
        return JSONResponse(calling_times.clock_data(instant), headers={'Cache-Control': 'no-store'})
    except (ValueError, OverflowError):
        raise HTTPException(400, 'Choose a date within the supported calendar range.')



@app.get("/research", response_class=HTMLResponse)
async def research_evidence_ledger_page(request: Request, q: str = Query('', max_length=200),
                                        source_filter: Literal['all', 'primary', 'secondary'] = 'all',
                                        page: int = Query(1, ge=1)):
    """Search the recorded source library without changing research data."""
    counts = get_summary_counts()
    sources = get_evidence_sources_list()
    source_total = len(sources)
    needle = q.strip().casefold()
    sources = [s for s in sources if
               (source_filter == 'all' or bool(s['is_primary_source']) == (source_filter == 'primary')) and
               (not needle or needle in ' '.join(str(s.get(k) or '') for k in
                ('source_title_publisher', 'source_url', 'source_type')).casefold())]
    matched = len(sources)
    pages = max(1, (matched + 49) // 50)
    page = min(page, pages)
    return templates.TemplateResponse(
        request=request,
        name="research.html",
        context={
            "counts": counts,
            "sources": sources[(page - 1) * 50:page * 50],
            "source_total": source_total, "matched": matched, "page": page, "pages": pages,
            "q": q, "source_filter": source_filter,
            "page_query": urllib.parse.urlencode({'q': q, 'source_filter': source_filter}),
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
    """Screen shortcut: Interested Prospects in Master Directory."""
    return RedirectResponse(url="/prospects?outreach=INTERESTED", status_code=302)


@app.get("/crm/follow-ups", response_class=HTMLResponse)
async def crm_follow_ups_page(request: Request, tz: Optional[str] = None):
    """Screen shortcut: Follow-Ups Workflow in Master Directory."""
    return RedirectResponse(url="/prospects?outreach=FOLLOW_UP", status_code=302)


@app.get("/crm/no-answer", response_class=HTMLResponse)
async def crm_no_answer_page(request: Request):
    """Screen shortcut: No Answer Queue in Master Directory."""
    return RedirectResponse(url="/prospects?outreach=NO_ANSWER", status_code=302)


@app.get("/crm/not-interested", response_class=HTMLResponse)
async def crm_not_interested_page(request: Request):
    """Screen shortcut: Not Interested in Master Directory."""
    return RedirectResponse(url="/prospects?outreach=NOT_INTERESTED", status_code=302)


# ============================================================================
# API Endpoints (Read-Only & Stage 3C Outreach CRM Mutations)
# ============================================================================

ALLOWED_CALL_DISPOSITIONS = {
    "INTERESTED", "NOT_INTERESTED", "NO_ANSWER", "CALL_BACK",
    "CONNECTED_DECISION_MAKER", "CONNECTED_GATEKEEPER", "LEFT_VOICEMAIL", "WRONG_CONTACT"
}


class VerifiedTelephoneEvidenceInput(BaseModel):
    confirmed_by_user: bool = False
    source_person_name: Optional[str] = None
    source_person_role: Optional[str] = None
    source_role_other: Optional[str] = None
    evidence_notes: Optional[str] = None
    commercial_carrier_use: Optional[str] = "UNKNOWN"
    broker_friendly_status: Optional[str] = "UNKNOWN"
    private_fleet_present: Optional[str] = "UNKNOWN"
    freight_procurement_level: Optional[str] = "UNKNOWN"
    equipment_confirmed: Optional[List[str]] = None

    @field_validator("commercial_carrier_use")
    @classmethod
    def validate_carrier_use(cls, v: Optional[str]) -> str:
        clean = (v or "UNKNOWN").strip().upper()
        if clean not in ("YES", "NO", "UNKNOWN"):
            raise ValueError(f"Invalid commercial_carrier_use '{v}'. Allowed: YES, NO, UNKNOWN")
        return clean

    @field_validator("broker_friendly_status")
    @classmethod
    def validate_broker_status(cls, v: Optional[str]) -> str:
        clean = (v or "UNKNOWN").strip().upper()
        if clean not in ("YES", "NO", "ASSET_CARRIERS_ONLY", "UNKNOWN"):
            raise ValueError(f"Invalid broker_friendly_status '{v}'. Allowed: YES, NO, ASSET_CARRIERS_ONLY, UNKNOWN")
        return clean

    @field_validator("private_fleet_present")
    @classmethod
    def validate_private_fleet(cls, v: Optional[str]) -> str:
        clean = (v or "UNKNOWN").strip().upper()
        if clean not in ("YES", "NO", "UNKNOWN"):
            raise ValueError(f"Invalid private_fleet_present '{v}'. Allowed: YES, NO, UNKNOWN")
        return clean

    @field_validator("freight_procurement_level")
    @classmethod
    def validate_procurement_level(cls, v: Optional[str]) -> str:
        clean = (v or "UNKNOWN").strip().upper()
        if clean not in ("FACILITY_LOCAL", "CENTRAL_CORPORATE", "UNKNOWN"):
            raise ValueError(f"Invalid freight_procurement_level '{v}'. Allowed: FACILITY_LOCAL, CENTRAL_CORPORATE, UNKNOWN")
        return clean


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
    client_request_id: Optional[str] = None
    verified_evidence: Optional[VerifiedTelephoneEvidenceInput] = None

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
    request: Request,
    team_view: Literal["all", "mine", "available"] = "all",
    stage: Optional[str] = "SHORTLISTED",
    tier: Optional[List[str]] = Query(None),
    opportunity: Optional[List[str]] = Query(None),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=500),
    q: Optional[str] = None,
    equipment: Optional[List[str]] = Query(None),
    family: Optional[List[str]] = Query(None),
    category: Optional[List[str]] = Query(None),
    seasonality: Optional[List[str]] = Query(None),
    fleet: Optional[List[str]] = Query(None),
    carrier: Optional[List[str]] = Query(None),
    procurement: Optional[List[str]] = Query(None),
):
    """Returns prospect facilities filtered by lifecycle stage with pagination/search/filters."""
    effective_tier = tier or opportunity
    state = team.snapshot()
    return get_prospects_list(
        allowed_company_ids=team.allowed_company_ids(request.state.user, team_view, state),
        lifecycle_stage=stage,
        tier=effective_tier,
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
    request: Request,
    team_view: Literal["all", "mine", "available"] = "all",
    stage: Optional[str] = "ALL",
    tier: Optional[List[str]] = Query(None),
    opportunity: Optional[List[str]] = Query(None),
    outreach: Optional[List[str]] = Query(None),
    unreviewed: bool = False,
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=500),
    q: Optional[str] = None,
    friction: Optional[str] = None,
    equipment: Optional[List[str]] = Query(None),
    family: Optional[List[str]] = Query(None),
    category: Optional[List[str]] = Query(None),
    seasonality: Optional[List[str]] = Query(None),
    structure: Optional[List[str]] = Query(None),
    facility_count: Optional[List[str]] = Query(None),
    fleet: Optional[List[str]] = Query(None),
    carrier: Optional[List[str]] = Query(None),
    procurement: Optional[List[str]] = Query(None),
    calling_zone: Optional[str] = None,
    calling_now: bool = False,
    calling_start: int = Query(9, ge=0, le=23),
    calling_end: int = Query(17, ge=1, le=24),
):
    """Returns company-grouped prospects with child facilities, facts, and pagination/search/filters."""
    effective_tier = tier or opportunity
    state = team.snapshot()
    if calling_zone and calling_zone not in calling_times.REGIONS:
        raise HTTPException(400, 'Choose a recognized time zone.')
    if calling_end <= calling_start:
        raise HTTPException(400, 'Closing time must be after opening time.')
    result = get_company_grouped_prospects(
        allowed_company_ids=calling_times.matching_companies(
            team.allowed_company_ids(request.state.user, team_view, state), calling_zone, calling_now, calling_start, calling_end),
        lifecycle_stage=stage,
        tier=effective_tier,
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

    for group in result["items"] if isinstance(result, dict) else result:
        group.update(state.get(group["company_id"], {}))
        calling_times.annotate(group, calling_zone, calling_now, calling_start, calling_end)
    return result


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
async def api_log_outreach_call(request: Request, req: LogCallRequest):
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
            broker_user_id=request.state.user["id"],
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
            client_request_id=req.client_request_id,
            verified_evidence=req.verified_evidence.model_dump() if req.verified_evidence else None,
        )
        return JSONResponse(status_code=201, content={"status": "success", "data": res})
    except HTTPException:
        raise
    except SuppressionBlockedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record call: {str(e)}")


class ClearOutreachRequest(BaseModel):
    action: Literal["clear_status", "cancel_follow_up"] = "clear_status"


@app.post("/api/outreach/{company_id}/clear", dependencies=[Depends(verify_mutation_origin)])
async def api_clear_outreach_tracking(request: Request, company_id: int, req: ClearOutreachRequest):
    try:
        return {"status": "success", "data": clear_outreach_tracking(company_id, req.action, broker_user_id=request.state.user["id"])}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/outreach/history", response_class=JSONResponse)
async def api_outreach_history(company_id: Optional[int] = None, facility_id: Optional[int] = None):
    """Returns append-only outreach timeline."""
    history = get_outreach_history(company_id=company_id, facility_id=facility_id)
    return team.add_authors(history)


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
