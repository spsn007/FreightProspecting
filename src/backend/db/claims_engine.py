"""
FreightProspecting V1 — Claims & Provenance Engine
Enforces the 10-subject provenance model, exact-1 subject constraint, and the
Single Current Accepted Claim Invariant (is_current_accepted = 1).
"""

from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.backend.db.validators import validate_iso_timestamp

# The exact 10 subject foreign key column names in the claims table
SUBJECT_FOREIGN_KEYS = [
    "company_id",
    "company_relationship_id",
    "facility_id",
    "facility_commodity_id",
    "contact_id",
    "freight_demand_signal_id",
    "load_opportunity_id",
    "carrier_id",
    "carrier_lane_activity_id",
    "capacity_posting_id",
]


def validate_single_subject(**kwargs) -> Tuple[str, int]:
    """
    Validate that exactly one subject foreign key is provided and non-null.
    Returns (subject_fk_column, subject_id).
    Raises ValueError if zero or multiple subject FKs are present.
    """
    populated = []
    for fk in SUBJECT_FOREIGN_KEYS:
        val = kwargs.get(fk)
        if val is not None:
            populated.append((fk, val))

    if len(populated) == 0:
        raise ValueError(
            "Exactly one subject reference must be provided for a claim. Found 0."
        )
    if len(populated) > 1:
        names = [k for k, _ in populated]
        raise ValueError(
            f"Exactly one subject reference must be provided for a claim. Found {len(populated)}: {names}"
        )

    return populated[0]


def record_evidence_source(
    conn: sqlite3.Connection,
    source_type: str,
    source_title_publisher: str,
    observed_at: str,
    source_url: Optional[str] = None,
    is_primary_source: Optional[bool] = None,
    source_published_at: Optional[str] = None,
    event_at: Optional[str] = None,
    outreach_log_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> int:
    """
    Record an evidence source.
    Enforces ISO-8601 validation for timestamps and permits nullable source_url for offline outreach.
    """
    valid_types = {
        "COMPANY_WEBSITE", "GOVERNMENT_REGISTRY", "JOB_POSTING",
        "INDUSTRY_DIRECTORY", "PHONE_OUTREACH", "EMAIL_CORRESPONDENCE"
    }
    if source_type not in valid_types:
        raise ValueError(f"Invalid source_type '{source_type}'. Allowed: {valid_types}")

    norm_observed_at = validate_iso_timestamp(observed_at, "observed_at")
    if not norm_observed_at:
        raise ValueError("observed_at is mandatory for evidence sources.")

    norm_published_at = validate_iso_timestamp(source_published_at, "source_published_at")
    norm_event_at = validate_iso_timestamp(event_at, "event_at")

    cursor = conn.execute(
        """
        INSERT INTO evidence_sources (
            source_type, source_title_publisher, source_url, is_primary_source,
            source_published_at, event_at, observed_at, outreach_log_id, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_type,
            source_title_publisher,
            source_url,
            1 if is_primary_source else (0 if is_primary_source is False else None),
            norm_published_at,
            norm_event_at,
            norm_observed_at,
            outreach_log_id,
            notes,
        ),
    )
    return cursor.lastrowid


def record_claim(
    conn: sqlite3.Connection,
    claim_field: str,
    claimed_value: str,
    verification_status: str,
    is_current_accepted: bool = True,
    claim_notes: Optional[str] = None,
    **subject_kwargs: Any,
) -> int:
    """
    Record a claim against exactly one subject.
    If is_current_accepted is True:
      - Atomically updates any currently accepted claim for this (subject, claim_field) to is_current_accepted = 0.
      - Sets the new claim to is_current_accepted = 1.
    Historical claims are never deleted.
    """
    if verification_status not in ("VERIFIED", "INFERRED", "UNKNOWN"):
        raise ValueError(f"Invalid verification_status '{verification_status}'. Must be VERIFIED, INFERRED, or UNKNOWN.")

    subject_col, subject_id = validate_single_subject(**subject_kwargs)

    # If accepting as the new current claim, supersede prior current claim atomically
    if is_current_accepted:
        conn.execute(
            f"""
            UPDATE claims
            SET is_current_accepted = 0, updated_at = CURRENT_TIMESTAMP
            WHERE {subject_col} = ? AND claim_field = ? AND is_current_accepted = 1
            """,
            (subject_id, claim_field),
        )

    # Build insert parameters for the 10 subject FKs
    params: Dict[str, Any] = {fk: None for fk in SUBJECT_FOREIGN_KEYS}
    params[subject_col] = subject_id
    params["claim_field"] = claim_field
    params["claimed_value"] = str(claimed_value)
    params["verification_status"] = verification_status
    params["is_current_accepted"] = 1 if is_current_accepted else 0
    params["claim_notes"] = claim_notes

    cols = ", ".join(params.keys())
    placeholders = ", ".join(":" + k for k in params.keys())

    cursor = conn.execute(
        f"INSERT INTO claims ({cols}) VALUES ({placeholders})",
        params,
    )
    return cursor.lastrowid


def link_claim_evidence(
    conn: sqlite3.Connection,
    claim_id: int,
    evidence_source_id: int,
    relationship: str = "SUPPORTS",
    relationship_notes: Optional[str] = None,
) -> int:
    """
    Link a claim to an evidence source with relationship: SUPPORTS, CONTRADICTS, or CONTEXT.
    """
    if relationship not in ("SUPPORTS", "CONTRADICTS", "CONTEXT"):
        raise ValueError(f"Invalid relationship '{relationship}'. Allowed: SUPPORTS, CONTRADICTS, CONTEXT.")

    cursor = conn.execute(
        """
        INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, relationship_notes)
        VALUES (?, ?, ?, ?)
        """,
        (claim_id, evidence_source_id, relationship, relationship_notes),
    )
    return cursor.lastrowid


def get_current_accepted_claims(
    conn: sqlite3.Connection,
    subject_col: str,
    subject_id: int,
) -> List[sqlite3.Row]:
    """Retrieve all current accepted claims for a specific subject entity."""
    if subject_col not in SUBJECT_FOREIGN_KEYS:
        raise ValueError(f"Unknown subject column '{subject_col}'.")

    cursor = conn.execute(
        f"""
        SELECT * FROM claims
        WHERE {subject_col} = ? AND is_current_accepted = 1
        ORDER BY claim_field ASC
        """,
        (subject_id,),
    )
    return cursor.fetchall()


def get_claim_history(
    conn: sqlite3.Connection,
    subject_col: str,
    subject_id: int,
    claim_field: str,
) -> List[sqlite3.Row]:
    """Retrieve full audit ledger for a specific subject and field, newest first."""
    if subject_col not in SUBJECT_FOREIGN_KEYS:
        raise ValueError(f"Unknown subject column '{subject_col}'.")

    cursor = conn.execute(
        f"""
        SELECT * FROM claims
        WHERE {subject_col} = ? AND claim_field = ?
        ORDER BY created_at DESC, id DESC
        """,
        (subject_id, claim_field),
    )
    return cursor.fetchall()
