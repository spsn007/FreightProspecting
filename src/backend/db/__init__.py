"""
FreightProspecting V1 — Database Package
Exports connection, schema, claims engine, and seed functions.
"""

from src.backend.db.connection import (
    create_connection,
    get_db_connection,
    get_db_path,
)
from src.backend.db.schema import (
    DEFAULT_SETTINGS,
    SCHEMA_DDL,
    init_db,
)
from src.backend.db.validators import (
    calculate_gross_margin,
    validate_date_string,
    validate_iso_timestamp,
)
from src.backend.db.claims_engine import (
    get_claim_history,
    get_current_accepted_claims,
    link_claim_evidence,
    record_claim,
    record_evidence_source,
    validate_single_subject,
)
from src.backend.db.backup import create_backup
from src.backend.db.seed import seed_database

__all__ = [
    "create_connection",
    "get_db_connection",
    "get_db_path",
    "SCHEMA_DDL",
    "DEFAULT_SETTINGS",
    "init_db",
    "validate_iso_timestamp",
    "validate_date_string",
    "calculate_gross_margin",
    "validate_single_subject",
    "record_claim",
    "record_evidence_source",
    "link_claim_evidence",
    "get_current_accepted_claims",
    "get_claim_history",
    "create_backup",
    "seed_database",
]
