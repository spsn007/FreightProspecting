"""
FreightProspecting V1 — Frozen Relational DDL (Revision 4.1 Authority)
Full idempotent SQLite schema creation matching docs/ARCHITECTURE.md.
"""

from pathlib import Path
import sqlite3
from typing import Optional

from src.backend.db.connection import get_db_connection

SCHEMA_DDL = """
-- ============================================================================
-- 1. COMPANIES & DATED CORPORATE RELATIONSHIPS
-- ============================================================================
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operating_brand TEXT NOT NULL,
    legal_name TEXT,
    corporate_address TEXT,
    website_url TEXT,
    notes TEXT,
    company_footprint_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(company_footprint_status IN ('SINGLE_SITE_VERIFIED', 'MULTI_SITE_VERIFIED', 'UNKNOWN')),
    verified_operating_location_count INTEGER DEFAULT NULL,
    footprint_source_notes TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS company_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    child_company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL, -- 'ACQUISITION', 'SUBSIDIARY', 'DIVISION', 'HOLDING'
    valid_from DATE,
    valid_to DATE,                   -- NULL indicates currently active relationship
    is_current BOOLEAN NOT NULL DEFAULT 1,
    verification_status TEXT NOT NULL CHECK(verification_status IN ('VERIFIED', 'INFERRED', 'UNKNOWN')),
    notes TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ============================================================================
-- 2. OPERATING FACILITIES
-- ============================================================================
CREATE TABLE IF NOT EXISTS facilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    facility_name TEXT NOT NULL,
    facility_type TEXT NOT NULL,     -- 'SAWMILL', 'STEEL_SERVICE_CENTER', 'PRECAST_PLANT', 'TOOLING_PLANT'
    physical_address TEXT NOT NULL,
    city TEXT NOT NULL,
    state_prov TEXT NOT NULL,
    postal_code TEXT,
    country TEXT NOT NULL CHECK(country IN ('US', 'CA')),
    latitude REAL,
    longitude REAL,
    -- Materialized operational fields synchronized with accepted claims
    private_fleet_present TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(private_fleet_present IN ('VERIFIED_PRESENT', 'VERIFIED_NO_FLEET', 'UNKNOWN')),
    vehicle_asset_ownership TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(vehicle_asset_ownership IN ('VERIFIED_OWNED', 'VERIFIED_LEASED', 'UNKNOWN')),
    fleet_relationship_type TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(fleet_relationship_type IN ('IN_HOUSE_OWNED', 'AFFILIATED_CARRIER_ENTITY', 'UNKNOWN')),
    commercial_carrier_use TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(commercial_carrier_use IN ('VERIFIED', 'UNKNOWN')),
    broker_friendly_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(broker_friendly_status IN ('VERIFIED_ACCEPTS', 'VERIFIED_DIRECT_ONLY', 'UNKNOWN')),
    freight_procurement_level TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(freight_procurement_level IN ('FACILITY_LEVEL', 'CORPORATE_PARENT', 'UNKNOWN')),
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ============================================================================
-- 3. FACILITY COMMODITIES & EQUIPMENT USAGE
-- ============================================================================
CREATE TABLE IF NOT EXISTS facility_commodities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    commodity_category TEXT NOT NULL,
    specific_products TEXT NOT NULL,
    equipment_category TEXT NOT NULL CHECK(equipment_category IN ('FLATBED', 'STEP_DECK', 'DRY_VAN')),
    equipment_usage_status TEXT NOT NULL CHECK(equipment_usage_status IN ('VERIFIED', 'INFERRED', 'UNKNOWN')),
    trailer_specs_notes TEXT,       -- e.g. '48-ft standard', 'pipe bunks', 'chains & coil racks'
    securement_tarp_notes TEXT,     -- e.g. '4-ft lumber tarps', 'steel tarps'
    commodity_category_id INTEGER REFERENCES commodity_categories(id),
    category_code TEXT,
    seasonality_profile TEXT DEFAULT NULL,
    peak_months TEXT DEFAULT NULL,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS commodity_families (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_code TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS commodity_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER NOT NULL REFERENCES commodity_families(id),
    category_code TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    typical_equipment_fit TEXT NOT NULL,
    seasonality_profile TEXT NOT NULL DEFAULT 'YEAR_ROUND',
    peak_months TEXT,
    operating_characteristics TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    deferred_status_note TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS facility_commodity_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES commodity_categories(id) ON DELETE CASCADE,
    source_evidence_notes TEXT,
    is_primary INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(facility_id, category_id)
);

-- ============================================================================
-- 4. GENERALIZED CONTACTS (SHIPPER & CARRIER)
-- ============================================================================
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    facility_id INTEGER REFERENCES facilities(id) ON DELETE CASCADE,
    carrier_id INTEGER REFERENCES carriers(id) ON DELETE CASCADE,
    contact_identity TEXT NOT NULL CHECK(contact_identity IN ('NAMED_PERSON', 'DEPARTMENT', 'GENERAL_FACILITY')),
    person_name TEXT,
    exact_published_title TEXT,
    department TEXT,
    phone_number TEXT,
    phone_extension TEXT,
    fax_number TEXT,
    phone_directness TEXT NOT NULL CHECK(phone_directness IN ('DIRECT_PERSON', 'DEPARTMENT_LINE', 'GENERAL_SWITCHBOARD', 'RECEPTION', 'TOLL_FREE', 'UNKNOWN')),
    email_address TEXT,
    email_directness TEXT NOT NULL CHECK(email_directness IN ('DIRECT_PERSON', 'DEPARTMENT', 'GENERAL', 'UNKNOWN')),
    role_category TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(role_category IN ('FREIGHT_LOGISTICS', 'COMMERCIAL_SALES', 'OPERATIONS', 'GENERAL_FACILITY', 'UNKNOWN')),
    outbound_shipping_procurement_relevance TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(outbound_shipping_procurement_relevance IN ('VERIFIED', 'INFERRED', 'UNKNOWN')),
    broker_procurement_relevance TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(broker_procurement_relevance IN ('VERIFIED', 'INFERRED', 'UNKNOWN')),
    is_primary_contact BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (
        (CASE WHEN company_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN facility_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN carrier_id IS NOT NULL THEN 1 ELSE 0 END) = 1
    )
);

-- ============================================================================
-- 5. CLAIMS LEDGER (10 PROVENANCE SUBJECTS & SINGLE CURRENT CLAIM ENFORCED)
-- ============================================================================
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    company_relationship_id INTEGER REFERENCES company_relationships(id) ON DELETE CASCADE,
    facility_id INTEGER REFERENCES facilities(id) ON DELETE CASCADE,
    facility_commodity_id INTEGER REFERENCES facility_commodities(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    freight_demand_signal_id INTEGER REFERENCES freight_demand_signals(id) ON DELETE CASCADE,
    load_opportunity_id INTEGER REFERENCES load_opportunities(id) ON DELETE CASCADE,
    carrier_id INTEGER REFERENCES carriers(id) ON DELETE CASCADE,
    carrier_lane_activity_id INTEGER REFERENCES carrier_lane_activity(id) ON DELETE CASCADE,
    capacity_posting_id INTEGER REFERENCES capacity_postings(id) ON DELETE CASCADE,
    claim_field TEXT NOT NULL,
    claimed_value TEXT NOT NULL,
    verification_status TEXT NOT NULL CHECK(verification_status IN ('VERIFIED', 'INFERRED', 'UNKNOWN')),
    is_current_accepted BOOLEAN NOT NULL DEFAULT 1,
    claim_notes TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (
        (CASE WHEN company_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN company_relationship_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN facility_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN facility_commodity_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN contact_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN freight_demand_signal_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN load_opportunity_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN carrier_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN carrier_lane_activity_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN capacity_posting_id IS NOT NULL THEN 1 ELSE 0 END) = 1
    )
);

-- Partial unique indexes: Exactly one current accepted claim per subject + field
CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_company 
    ON claims(company_id, claim_field) 
    WHERE is_current_accepted = 1 AND company_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_comp_rel 
    ON claims(company_relationship_id, claim_field) 
    WHERE is_current_accepted = 1 AND company_relationship_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_facility 
    ON claims(facility_id, claim_field) 
    WHERE is_current_accepted = 1 AND facility_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_commodity 
    ON claims(facility_commodity_id, claim_field) 
    WHERE is_current_accepted = 1 AND facility_commodity_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_contact 
    ON claims(contact_id, claim_field) 
    WHERE is_current_accepted = 1 AND contact_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_fgt_sig 
    ON claims(freight_demand_signal_id, claim_field) 
    WHERE is_current_accepted = 1 AND freight_demand_signal_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_load 
    ON claims(load_opportunity_id, claim_field) 
    WHERE is_current_accepted = 1 AND load_opportunity_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_carrier 
    ON claims(carrier_id, claim_field) 
    WHERE is_current_accepted = 1 AND carrier_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_lane_act 
    ON claims(carrier_lane_activity_id, claim_field) 
    WHERE is_current_accepted = 1 AND carrier_lane_activity_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_current_claim_capacity 
    ON claims(capacity_posting_id, claim_field) 
    WHERE is_current_accepted = 1 AND capacity_posting_id IS NOT NULL;

-- General query indexes on claims
CREATE INDEX IF NOT EXISTS idx_claims_field ON claims(claim_field);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(verification_status);

-- ============================================================================
-- 6. EVIDENCE SOURCES & LINK TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS evidence_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK(source_type IN (
        'COMPANY_WEBSITE', 'FIRST_PARTY', 'GOVERNMENT_REGISTRY', 'GOVERNMENT_REGULATOR',
        'TRADE_ASSOCIATION', 'INDUSTRY_DIRECTORY', 'DIRECTORY_AGGREGATOR', 'JOB_POSTING',
        'PHONE_OUTREACH', 'EMAIL_CORRESPONDENCE', 'OTHER_SECONDARY', 'MANUAL_USER_OBSERVED'
    )),
    source_title_publisher TEXT NOT NULL,
    source_url TEXT,                 -- NULLABLE: Phone outreach and offline sources have no URL
    is_primary_source BOOLEAN,       -- NULLABLE: Set when applicable
    source_published_at DATETIME,    -- Publication timestamp (NULL if unknown)
    event_at DATETIME,               -- Timestamp when event occurred/applies (NULL if persistent fact)
    observed_at DATETIME NOT NULL,   -- Timestamp when researcher/system inspected source
    outreach_log_id INTEGER REFERENCES outreach_logs(id) ON DELETE SET NULL,
    notes TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS claim_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    evidence_source_id INTEGER NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    relationship TEXT NOT NULL CHECK(relationship IN ('SUPPORTS', 'CONTRADICTS', 'CONTEXT')),
    relationship_notes TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ============================================================================
-- 7. FREIGHT DEMAND SIGNALS (SEPARATED FROM DISCRETE LOADS)
-- ============================================================================
CREATE TABLE IF NOT EXISTS freight_demand_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    signal_type TEXT NOT NULL CHECK(signal_type IN ('RFP', 'TENDER', 'DATED_LOAD_POSTING', 'QUOTE_REQUEST', 'SHIPMENT_PROCUREMENT_NOTICE', 'DIRECT_CONFIRMATION')),
    signal_status TEXT NOT NULL CHECK(signal_status IN ('HISTORICAL_SIGNAL', 'SIGNAL_LAST_30_DAYS', 'EXPIRED')),
    origin_city TEXT,
    origin_state_prov TEXT,
    origin_country TEXT CHECK(origin_country IS NULL OR origin_country IN ('US', 'CA')),
    dest_city TEXT,
    dest_state_prov TEXT,
    dest_country TEXT CHECK(dest_country IS NULL OR dest_country IN ('US', 'CA')),
    commodity_notes TEXT,
    equipment_indication TEXT CHECK(equipment_indication IS NULL OR equipment_indication IN ('FLATBED', 'STEP_DECK', 'DRY_VAN')),
    event_at DATETIME,               -- NULLABLE for undated historical signals; MANDATORY for SIGNAL_LAST_30_DAYS
    observed_at DATETIME NOT NULL,   -- Date/time signal was checked
    expires_at DATETIME,             -- Signal expiration timestamp
    notes TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (
        signal_status != 'SIGNAL_LAST_30_DAYS' OR event_at IS NOT NULL
    )
);

-- ============================================================================
-- 8. LOAD OPPORTUNITIES (STATE-DEPENDENT VALIDATION)
-- ============================================================================
CREATE TABLE IF NOT EXISTS load_opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
    load_status TEXT NOT NULL CHECK(load_status IN ('IDENTIFIED', 'CONFIRMED_AVAILABLE_NOW', 'COVERED', 'LOST', 'CANCELLED', 'EXPIRED')),
    origin_city TEXT,                -- NULLABLE in IDENTIFIED; Enforced NOT NULL in CONFIRMED_AVAILABLE_NOW
    origin_state_prov TEXT,          -- NULLABLE in IDENTIFIED; Enforced NOT NULL in CONFIRMED_AVAILABLE_NOW
    origin_country TEXT CHECK(origin_country IS NULL OR origin_country IN ('US', 'CA')),
    dest_city TEXT,                  -- NULLABLE in IDENTIFIED; Enforced NOT NULL in CONFIRMED_AVAILABLE_NOW
    dest_state_prov TEXT,            -- NULLABLE in IDENTIFIED; Enforced NOT NULL in CONFIRMED_AVAILABLE_NOW
    dest_country TEXT CHECK(dest_country IS NULL OR dest_country IN ('US', 'CA')),
    pickup_date_earliest DATE,       -- Enforced NOT NULL in CONFIRMED_AVAILABLE_NOW
    pickup_date_latest DATE,
    delivery_date_earliest DATE,
    delivery_date_latest DATE,
    equipment_required TEXT CHECK(equipment_required IS NULL OR equipment_required IN ('FLATBED', 'STEP_DECK', 'DRY_VAN')),
    trailer_specs_required TEXT,
    weight_lbs INTEGER,
    dimensions_notes TEXT,
    securement_tarps_notes TEXT,
    shipper_target_rate NUMERIC,     -- NULLABLE: Margin is UNKNOWN if NULL
    carrier_target_cost NUMERIC,     -- NULLABLE: Margin is UNKNOWN if NULL
    gross_margin NUMERIC,            -- Synchronized: shipper_target_rate - carrier_target_cost
    margin_pct NUMERIC,              -- Synchronized: (gross_margin / shipper_target_rate) * 100
    confirmed_at DATETIME,           -- Mandatory in CONFIRMED_AVAILABLE_NOW
    last_reconfirmed_at DATETIME,
    expires_at DATETIME,             -- Mandatory in CONFIRMED_AVAILABLE_NOW
    event_at DATETIME,               -- Mandatory in CONFIRMED_AVAILABLE_NOW
    observed_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (
        load_status != 'CONFIRMED_AVAILABLE_NOW' OR (
            origin_city IS NOT NULL AND
            origin_state_prov IS NOT NULL AND
            origin_country IS NOT NULL AND
            dest_city IS NOT NULL AND
            dest_state_prov IS NOT NULL AND
            dest_country IS NOT NULL AND
            pickup_date_earliest IS NOT NULL AND
            equipment_required IS NOT NULL AND
            confirmed_at IS NOT NULL AND
            expires_at IS NOT NULL AND
            event_at IS NOT NULL
        )
    )
);

-- ============================================================================
-- 9. CARRIERS, HISTORICAL LANE ACTIVITY, & CAPACITY POSTINGS
-- ============================================================================
CREATE TABLE IF NOT EXISTS carriers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    legal_name TEXT NOT NULL,
    dba_name TEXT,
    usdot_number TEXT UNIQUE,
    mc_number TEXT,
    physical_city TEXT,
    physical_state_prov TEXT,
    country TEXT NOT NULL CHECK(country IN ('US', 'CA')),
    safety_rating TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(safety_rating IN ('VERIFIED_SATISFACTORY', 'VERIFIED_CONDITIONAL', 'VERIFIED_UNSATISFACTORY', 'VERIFIED_NOT_RATED', 'UNKNOWN')),
    operating_status TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(operating_status IN ('VERIFIED_AUTHORIZED', 'VERIFIED_NOT_AUTHORIZED', 'VERIFIED_OUT_OF_SERVICE', 'UNKNOWN')),
    cross_border_capability TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(cross_border_capability IN ('US_ONLY', 'CANADA_ONLY', 'US_CANADA_CAPABLE', 'UNKNOWN')),
    primary_equipment_types TEXT,    -- JSON array: ['FLATBED', 'STEP_DECK']
    fleet_power_units INTEGER,
    preferred_lanes_notes TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS carrier_lane_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier_id INTEGER NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
    origin_country TEXT CHECK(origin_country IS NULL OR origin_country IN ('US', 'CA')),
    origin_region TEXT NOT NULL,     -- State, province, or geographic corridor
    dest_country TEXT CHECK(dest_country IS NULL OR dest_country IN ('US', 'CA')),
    dest_region TEXT NOT NULL,
    equipment_type TEXT CHECK(equipment_type IS NULL OR equipment_type IN ('FLATBED', 'STEP_DECK', 'DRY_VAN')),
    activity_type TEXT NOT NULL CHECK(activity_type IN ('HISTORICAL_MOVE', 'INSPECTION_RECORD', 'DISPATCHER_PREFERRED')),
    observed_at DATETIME NOT NULL,
    notes TEXT,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS capacity_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier_id INTEGER NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
    dispatcher_contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    capacity_status TEXT NOT NULL CHECK(capacity_status IN ('POSTED_TENTATIVE', 'TRUCK_CONFIRMED_AVAILABLE_NOW', 'COVERED_BOOKED', 'EXPIRED')),
    available_city TEXT NOT NULL,
    available_state_prov TEXT NOT NULL,
    available_country TEXT NOT NULL CHECK(available_country IN ('US', 'CA')),
    available_date_start DATE NOT NULL,
    available_date_end DATE,
    equipment_type TEXT NOT NULL CHECK(equipment_type IN ('FLATBED', 'STEP_DECK', 'DRY_VAN')),
    trailer_specs_capability TEXT,
    weight_capability_lbs INTEGER,   -- NULLABLE: Not forced into unknown state
    destination_preference_notes TEXT,
    confirmed_at DATETIME,           -- Mandatory when TRUCK_CONFIRMED_AVAILABLE_NOW
    last_reconfirmed_at DATETIME,
    expires_at DATETIME,             -- Mandatory when TRUCK_CONFIRMED_AVAILABLE_NOW
    event_at DATETIME NOT NULL,      -- Actual truck readiness date/window
    observed_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (
        capacity_status != 'TRUCK_CONFIRMED_AVAILABLE_NOW' OR (
            confirmed_at IS NOT NULL AND
            expires_at IS NOT NULL
        )
    )
);

-- ============================================================================
-- 10. SPECIFIC LOAD <-> CAPACITY MATCHES (TRI-STATE COMPATIBILITY)
-- ============================================================================
CREATE TABLE IF NOT EXISTS load_capacity_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    load_opportunity_id INTEGER NOT NULL REFERENCES load_opportunities(id) ON DELETE CASCADE,
    capacity_posting_id INTEGER NOT NULL REFERENCES capacity_postings(id) ON DELETE CASCADE,
    match_status TEXT NOT NULL DEFAULT 'PROPOSED' CHECK(match_status IN ('PROPOSED', 'ACCEPTED', 'REJECTED', 'EXPIRED')),
    equipment_compatibility TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(equipment_compatibility IN ('COMPATIBLE', 'INCOMPATIBLE', 'UNKNOWN')),
    lane_compatibility TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(lane_compatibility IN ('COMPATIBLE', 'INCOMPATIBLE', 'UNKNOWN')),
    timing_compatibility TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(timing_compatibility IN ('COMPATIBLE', 'INCOMPATIBLE', 'UNKNOWN')),
    weight_dim_compatibility TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(weight_dim_compatibility IN ('COMPATIBLE', 'INCOMPATIBLE', 'UNKNOWN')),
    cross_border_compatibility TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(cross_border_compatibility IN ('COMPATIBLE', 'INCOMPATIBLE', 'UNKNOWN')),
    estimated_carrier_cost NUMERIC,
    match_reasoning TEXT NOT NULL,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ============================================================================
-- 11. SCOPED SUPPRESSIONS (EXPANDED LANE SCOPE & GEOGRAPHY)
-- ============================================================================
CREATE TABLE IF NOT EXISTS suppressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('COMPANY', 'FACILITY', 'COMPANY_LANE', 'FACILITY_LANE', 'GLOBAL_LANE')),
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    facility_id INTEGER REFERENCES facilities(id) ON DELETE CASCADE,
    origin_country TEXT CHECK(origin_country IS NULL OR origin_country IN ('US', 'CA')),
    origin_state_prov TEXT,
    origin_city TEXT,
    dest_country TEXT CHECK(dest_country IS NULL OR dest_country IN ('US', 'CA')),
    dest_state_prov TEXT,
    dest_city TEXT,
    suppression_status TEXT NOT NULL CHECK(suppression_status IN ('NORMAL_PROSPECT', 'EXISTING_CUSTOMER', 'ALREADY_ROUTED', 'DO_NOT_CONTACT')),
    reason_notes TEXT NOT NULL,
    assigned_by TEXT NOT NULL DEFAULT 'USER',
    effective_date DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (
        (scope_type = 'COMPANY' AND company_id IS NOT NULL AND facility_id IS NULL AND origin_state_prov IS NULL) OR
        (scope_type = 'FACILITY' AND facility_id IS NOT NULL AND company_id IS NULL AND origin_state_prov IS NULL) OR
        (scope_type = 'COMPANY_LANE' AND company_id IS NOT NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL) OR
        (scope_type = 'FACILITY_LANE' AND facility_id IS NOT NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL) OR
        (scope_type = 'GLOBAL_LANE' AND company_id IS NULL AND facility_id IS NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL)
    )
);

-- ============================================================================
-- 12. GENERALIZED OUTREACH LOGS & SETTINGS
-- ============================================================================
CREATE TABLE IF NOT EXISTS outreach_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    facility_id INTEGER REFERENCES facilities(id) ON DELETE CASCADE,
    carrier_id INTEGER REFERENCES carriers(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    freight_demand_signal_id INTEGER REFERENCES freight_demand_signals(id) ON DELETE SET NULL,
    load_opportunity_id INTEGER REFERENCES load_opportunities(id) ON DELETE SET NULL,
    capacity_posting_id INTEGER REFERENCES capacity_postings(id) ON DELETE SET NULL,
    outreach_channel TEXT NOT NULL DEFAULT 'PHONE' CHECK(outreach_channel IN ('PHONE', 'EMAIL', 'IN_PERSON')),
    outcome TEXT NOT NULL CHECK(outcome IN ('INTERESTED', 'NOT_INTERESTED', 'NO_ANSWER', 'CALL_BACK', 'CONNECTED_DECISION_MAKER', 'CONNECTED_GATEKEEPER', 'LEFT_VOICEMAIL', 'WRONG_CONTACT')),
    disposition TEXT CHECK(disposition IS NULL OR disposition IN ('INTERESTED', 'NOT_INTERESTED', 'NO_ANSWER', 'CALL_BACK', 'CONNECTED_DECISION_MAKER', 'CONNECTED_GATEKEEPER', 'LEFT_VOICEMAIL', 'WRONG_CONTACT')),
    feedback_notes TEXT,
    notes TEXT,
    shipping_procurement_findings TEXT,
    broker_policy_findings TEXT,
    private_fleet_findings TEXT,
    contacted_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    follow_up_date DATE,
    follow_up_at DATETIME,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (
        company_id IS NOT NULL OR
        facility_id IS NOT NULL OR
        carrier_id IS NOT NULL
    )
);

CREATE TABLE IF NOT EXISTS prospect_engagement_state (
    company_id INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    current_outreach_status TEXT NOT NULL DEFAULT 'UNCONTACTED' CHECK(current_outreach_status IN (
        'UNCONTACTED', 'INTERESTED', 'NOT_INTERESTED', 'NO_ANSWER', 'CALL_BACK',
        'CONNECTED_DECISION_MAKER', 'CONNECTED_GATEKEEPER', 'LEFT_VOICEMAIL', 'WRONG_CONTACT'
    )),
    status_source_outreach_log_id INTEGER REFERENCES outreach_logs(id) ON DELETE SET NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_contacted_at DATETIME,
    next_follow_up_at DATETIME,
    last_facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
    last_feedback_notes TEXT,
    is_viewed INTEGER NOT NULL DEFAULT 0,
    first_viewed_at DATETIME,
    last_viewed_at DATETIME,
    created_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    value_type TEXT NOT NULL CHECK(value_type IN ('BOOLEAN', 'INTEGER', 'FLOAT', 'STRING', 'JSON')),
    description TEXT
);

-- Foreign Key Performance Indexes
CREATE INDEX IF NOT EXISTS idx_facilities_company ON facilities(company_id);
CREATE INDEX IF NOT EXISTS idx_fac_commodities_facility ON facility_commodities(facility_id);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_contacts_facility ON contacts(facility_id);
CREATE INDEX IF NOT EXISTS idx_contacts_carrier ON contacts(carrier_id);
CREATE INDEX IF NOT EXISTS idx_demand_signals_facility ON freight_demand_signals(facility_id);
CREATE INDEX IF NOT EXISTS idx_load_opps_facility ON load_opportunities(facility_id);
CREATE INDEX IF NOT EXISTS idx_carrier_lane_carrier ON carrier_lane_activity(carrier_id);
CREATE INDEX IF NOT EXISTS idx_capacity_carrier ON capacity_postings(carrier_id);
CREATE INDEX IF NOT EXISTS idx_matches_load ON load_capacity_matches(load_opportunity_id);
CREATE INDEX IF NOT EXISTS idx_matches_capacity ON load_capacity_matches(capacity_posting_id);
CREATE INDEX IF NOT EXISTS idx_outreach_company ON outreach_logs(company_id);
CREATE INDEX IF NOT EXISTS idx_outreach_facility ON outreach_logs(facility_id);
CREATE INDEX IF NOT EXISTS idx_outreach_carrier ON outreach_logs(carrier_id);
CREATE INDEX IF NOT EXISTS idx_outreach_contacted_at ON outreach_logs(contacted_at);
CREATE INDEX IF NOT EXISTS idx_outreach_outcome ON outreach_logs(outcome);
CREATE INDEX IF NOT EXISTS idx_engagement_status ON prospect_engagement_state(current_outreach_status);
CREATE INDEX IF NOT EXISTS idx_engagement_follow_up ON prospect_engagement_state(next_follow_up_at);
CREATE INDEX IF NOT EXISTS idx_engagement_viewed ON prospect_engagement_state(is_viewed);
CREATE INDEX IF NOT EXISTS idx_suppression_company ON suppressions(company_id);
CREATE INDEX IF NOT EXISTS idx_suppression_facility ON suppressions(facility_id);

-- Outreach Logs Append-Only Protection Triggers (AUD-025: Unconditional)
CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_update
BEFORE UPDATE ON outreach_logs
BEGIN
    SELECT RAISE(ABORT, 'outreach_logs is append-only: UPDATE operations are strictly prohibited.');
END;

CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_delete
BEFORE DELETE ON outreach_logs
BEGIN
    SELECT RAISE(ABORT, 'outreach_logs is append-only: DELETE operations are strictly prohibited.');
END;

CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_replace
BEFORE INSERT ON outreach_logs
FOR EACH ROW
WHEN NEW.id IS NOT NULL AND EXISTS (SELECT 1 FROM outreach_logs WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'outreach_logs is append-only: replacing or reusing existing id is strictly forbidden');
END;

-- Load Opportunities Rate & Margin Integrity Triggers (AUD-014)
CREATE TRIGGER IF NOT EXISTS trg_load_opps_validate_rates_insert
BEFORE INSERT ON load_opportunities
BEGIN
    SELECT RAISE(ABORT, 'shipper_target_rate cannot be negative')
    WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate < 0;
    
    SELECT RAISE(ABORT, 'carrier_target_cost cannot be negative')
    WHERE NEW.carrier_target_cost IS NOT NULL AND NEW.carrier_target_cost < 0;
END;

CREATE TRIGGER IF NOT EXISTS trg_load_opps_validate_rates_update
BEFORE UPDATE ON load_opportunities
BEGIN
    SELECT RAISE(ABORT, 'shipper_target_rate cannot be negative')
    WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate < 0;
    
    SELECT RAISE(ABORT, 'carrier_target_cost cannot be negative')
    WHERE NEW.carrier_target_cost IS NOT NULL AND NEW.carrier_target_cost < 0;
END;

CREATE TRIGGER IF NOT EXISTS trg_load_opps_validate_margin_insert
BEFORE INSERT ON load_opportunities
BEGIN
    SELECT RAISE(ABORT, 'gross_margin must be NULL when rates are missing')
    WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
      AND NEW.gross_margin IS NOT NULL;
      
    SELECT RAISE(ABORT, 'gross_margin does not match shipper_target_rate - carrier_target_cost')
    WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
      AND NEW.gross_margin IS NOT NULL
      AND ROUND(NEW.gross_margin, 2) != ROUND(NEW.shipper_target_rate - NEW.carrier_target_cost, 2);
END;

CREATE TRIGGER IF NOT EXISTS trg_load_opps_validate_margin_update
BEFORE UPDATE ON load_opportunities
BEGIN
    SELECT RAISE(ABORT, 'gross_margin must be NULL when rates are missing')
    WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
      AND NEW.gross_margin IS NOT NULL;
      
    SELECT RAISE(ABORT, 'gross_margin does not match shipper_target_rate - carrier_target_cost')
    WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
      AND NEW.gross_margin IS NOT NULL
      AND ROUND(NEW.gross_margin, 2) != ROUND(NEW.shipper_target_rate - NEW.carrier_target_cost, 2);
END;

-- ============================================================================
-- 18. PROSPECT LIFECYCLE (STAGE 3A 1:1 FACILITY EXTENSION)
-- ============================================================================
CREATE TABLE IF NOT EXISTS prospect_lifecycle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL UNIQUE REFERENCES facilities(id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK(stage IN ('DISCOVERY', 'QUALIFIED', 'SHORTLISTED', 'ARCHIVED')),
    entered_discovery_at TEXT NOT NULL,
    discovered_at TEXT,
    qualified_at TEXT,
    shortlisted_at TEXT,
    archived_at TEXT,
    qualification_notes TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prospect_lifecycle_stage ON prospect_lifecycle(stage);
CREATE INDEX IF NOT EXISTS idx_prospect_lifecycle_fac ON prospect_lifecycle(facility_id);

-- ============================================================================
-- 19. DISCOVERY INTAKE AUDIT (STAGE 3A INGESTION & DEDUPLICATION LEDGER)
-- ============================================================================
CREATE TABLE IF NOT EXISTS discovery_intake_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_name TEXT NOT NULL,
    candidate_company_name TEXT NOT NULL,
    candidate_facility_name TEXT NOT NULL,
    city TEXT NOT NULL,
    state_prov TEXT NOT NULL,
    country TEXT NOT NULL CHECK(country IN ('US', 'CA')),
    intake_fingerprint TEXT NOT NULL UNIQUE,
    intake_status TEXT NOT NULL CHECK(intake_status IN ('APPROVED_FOR_IMPORT', 'IMPORTED_DISCOVERY', 'DEFERRED_FOR_RESEARCH', 'REJECTED_OUT_OF_SCOPE', 'DUPLICATE_REMOVED', 'DUPLICATE_SUPPRESSED')),
    target_facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
    website_url TEXT,
    facility_address TEXT,
    batch_reference TEXT,
    reason_or_notes TEXT,
    reason_notes TEXT,
    reviewed_at TEXT,
    imported_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_discovery_intake_status ON discovery_intake_audit(intake_status);
CREATE INDEX IF NOT EXISTS idx_discovery_intake_fingerprint ON discovery_intake_audit(intake_fingerprint);
"""

# Default system settings
DEFAULT_SETTINGS = [
    ("alaska_enabled", "false", "BOOLEAN", "Toggle to enable Alaska territory matching (Decision A default: false)"),
    ("phone_first_preferred", "true", "BOOLEAN", "Prioritize phone outreach over email (Decision B)"),
    ("signal_fresh_threshold_days", "30", "INTEGER", "Days before demand signal decays to aging"),
    ("signal_stale_threshold_days", "60", "INTEGER", "Days before demand signal decays to stale"),
    ("app_version", "1.0.0", "STRING", "FreightProspecting V1 version"),
    ("ai_api_enabled", "false", "BOOLEAN", "Strict zero-paid-AI standard: V1 executes 100% locally without AI keys (Decision H)")
]


def _migrate_legacy_suppressions_if_needed(conn: sqlite3.Connection) -> None:
    """Migrate legacy suppression_status_records table/view to suppressions if present."""
    cur = conn.cursor()
    cur.execute("SELECT type, name FROM sqlite_master WHERE name IN ('suppression_status_records', 'suppressions')")
    objs = {r["name"]: r["type"] for r in cur.fetchall()}

    # Drop legacy view if it exists
    if objs.get("suppressions") == "view":
        conn.execute("DROP VIEW IF EXISTS suppressions;")

    # If legacy table exists, ensure suppressions physical table exists and migrate rows
    if objs.get("suppression_status_records") == "table":
        # Create physical suppressions table if not yet present
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS suppressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_type TEXT NOT NULL CHECK(scope_type IN ('COMPANY', 'FACILITY', 'COMPANY_LANE', 'FACILITY_LANE', 'GLOBAL_LANE')),
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                facility_id INTEGER REFERENCES facilities(id) ON DELETE CASCADE,
                origin_country TEXT CHECK(origin_country IS NULL OR origin_country IN ('US', 'CA')),
                origin_state_prov TEXT,
                origin_city TEXT,
                dest_country TEXT CHECK(dest_country IS NULL OR dest_country IN ('US', 'CA')),
                dest_state_prov TEXT,
                dest_city TEXT,
                suppression_status TEXT NOT NULL CHECK(suppression_status IN ('NORMAL_PROSPECT', 'EXISTING_CUSTOMER', 'ALREADY_ROUTED', 'DO_NOT_CONTACT')),
                reason_notes TEXT NOT NULL,
                assigned_by TEXT NOT NULL DEFAULT 'USER',
                effective_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                CHECK (
                    (scope_type = 'COMPANY' AND company_id IS NOT NULL AND facility_id IS NULL AND origin_state_prov IS NULL) OR
                    (scope_type = 'FACILITY' AND facility_id IS NOT NULL AND company_id IS NULL AND origin_state_prov IS NULL) OR
                    (scope_type = 'COMPANY_LANE' AND company_id IS NOT NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL) OR
                    (scope_type = 'FACILITY_LANE' AND facility_id IS NOT NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL) OR
                    (scope_type = 'GLOBAL_LANE' AND company_id IS NULL AND facility_id IS NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL)
                )
            );
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO suppressions (
                id, scope_type, company_id, facility_id,
                origin_country, origin_state_prov, origin_city,
                dest_country, dest_state_prov, dest_city,
                suppression_status, reason_notes, assigned_by, effective_date
            )
            SELECT
                id, scope_type, company_id, facility_id,
                origin_country, origin_state_prov, origin_city,
                dest_country, dest_state_prov, dest_city,
                suppression_status, reason_notes, assigned_by, effective_date
            FROM suppression_status_records;
            """
        )
        conn.execute("DROP INDEX IF EXISTS idx_suppression_company;")
        conn.execute("DROP INDEX IF EXISTS idx_suppression_facility;")
        conn.execute("DROP TABLE suppression_status_records;")


def _migrate_stage3a_if_needed(conn: sqlite3.Connection) -> None:
    """
    Safely migrates existing database to Stage 3A:
    1. Adds fleet_relationship_type and commercial_carrier_use to facilities if missing.
    2. Rebuilds contacts table if role_category is missing or enums need updating.
    3. Creates prospect_lifecycle and discovery_intake_audit tables.
    4. Backfills the 4 seed facilities into prospect_lifecycle as SHORTLISTED.
    5. Backfills the 6 audited seed contacts with exact role_category and directness.
    6. Runs foreign_key_check and integrity_check.
    """
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='facilities'")
    if not cur.fetchone():
        return

    # 1. Check facilities columns
    cur.execute("PRAGMA table_info(facilities)")
    fac_cols = {r["name"] for r in cur.fetchall()}
    if fac_cols:
        if "fleet_relationship_type" not in fac_cols:
            conn.execute(
                "ALTER TABLE facilities ADD COLUMN fleet_relationship_type TEXT NOT NULL DEFAULT 'UNKNOWN' "
                "CHECK(fleet_relationship_type IN ('IN_HOUSE_OWNED', 'AFFILIATED_CARRIER_ENTITY', 'UNKNOWN'))"
            )
        if "commercial_carrier_use" not in fac_cols:
            conn.execute(
                "ALTER TABLE facilities ADD COLUMN commercial_carrier_use TEXT NOT NULL DEFAULT 'UNKNOWN' "
                "CHECK(commercial_carrier_use IN ('VERIFIED', 'UNKNOWN'))"
            )

    # 2. Check contacts table
    cur.execute("PRAGMA table_info(contacts)")
    cont_cols = {r["name"] for r in cur.fetchall()}
    if cont_cols and "role_category" not in cont_cols:
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute(
            """
            CREATE TABLE contacts_stage3a (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                facility_id INTEGER REFERENCES facilities(id) ON DELETE CASCADE,
                carrier_id INTEGER REFERENCES carriers(id) ON DELETE CASCADE,
                contact_identity TEXT NOT NULL CHECK(contact_identity IN ('NAMED_PERSON', 'DEPARTMENT', 'GENERAL_FACILITY')),
                person_name TEXT,
                exact_published_title TEXT,
                department TEXT,
                phone_number TEXT,
                phone_extension TEXT,
                phone_directness TEXT NOT NULL CHECK(phone_directness IN ('DIRECT_PERSON', 'DEPARTMENT_LINE', 'GENERAL_SWITCHBOARD', 'RECEPTION', 'TOLL_FREE', 'UNKNOWN')),
                email_address TEXT,
                email_directness TEXT NOT NULL CHECK(email_directness IN ('DIRECT_PERSON', 'DEPARTMENT', 'GENERAL', 'UNKNOWN')),
                role_category TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(role_category IN ('FREIGHT_LOGISTICS', 'COMMERCIAL_SALES', 'OPERATIONS', 'GENERAL_FACILITY', 'UNKNOWN')),
                outbound_shipping_procurement_relevance TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(outbound_shipping_procurement_relevance IN ('VERIFIED', 'INFERRED', 'UNKNOWN')),
                broker_procurement_relevance TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK(broker_procurement_relevance IN ('VERIFIED', 'INFERRED', 'UNKNOWN')),
                is_primary_contact BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CHECK (
                    (CASE WHEN company_id IS NOT NULL THEN 1 ELSE 0 END +
                     CASE WHEN facility_id IS NOT NULL THEN 1 ELSE 0 END +
                     CASE WHEN carrier_id IS NOT NULL THEN 1 ELSE 0 END) = 1
                )
            );
            """
        )

        existing_contacts = conn.execute("SELECT * FROM contacts").fetchall()
        for c in existing_contacts:
            c_dict = dict(c)
            p_dir = c_dict.get("phone_directness") or "UNKNOWN"
            if p_dir == "DEPARTMENTAL":
                p_dir = "DEPARTMENT_LINE"

            e_dir = c_dict.get("email_directness") or "UNKNOWN"
            if e_dir == "DEPARTMENTAL":
                e_dir = "DEPARTMENT"
            elif e_dir == "GENERAL_INBOX":
                e_dir = "GENERAL"

            role_cat = "UNKNOWN"
            cid = c_dict["id"]
            if cid == 1:  # Phil Clements (Sawmill Manager)
                role_cat = "OPERATIONS"
                p_dir = "GENERAL_SWITCHBOARD"
            elif cid == 2:  # Mark Joiner (Logistics Manager)
                role_cat = "FREIGHT_LOGISTICS"
                p_dir = "DIRECT_PERSON"
            elif cid == 3:  # Kenwal Main Switchboard
                role_cat = "GENERAL_FACILITY"
                p_dir = "GENERAL_SWITCHBOARD"
            elif cid == 4:  # DECAST Main Reception
                role_cat = "GENERAL_FACILITY"
                p_dir = "RECEPTION"
                e_dir = "GENERAL"
            elif cid == 5:  # DECAST Toll-Free Customer Line
                role_cat = "GENERAL_FACILITY"
                p_dir = "TOLL_FREE"
            elif cid == 6:  # WMG Tooling Division Reception
                role_cat = "GENERAL_FACILITY"
                p_dir = "RECEPTION"

            conn.execute(
                """
                INSERT INTO contacts_stage3a (
                    id, company_id, facility_id, carrier_id, contact_identity,
                    person_name, exact_published_title, department, phone_number,
                    phone_extension, phone_directness, email_address, email_directness,
                    role_category, outbound_shipping_procurement_relevance,
                    broker_procurement_relevance, is_primary_contact, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid, c_dict.get("company_id"), c_dict.get("facility_id"), c_dict.get("carrier_id"),
                    c_dict.get("contact_identity"), c_dict.get("person_name"), c_dict.get("exact_published_title"),
                    c_dict.get("department"), c_dict.get("phone_number"), c_dict.get("phone_extension"),
                    p_dir, c_dict.get("email_address"), e_dir, role_cat,
                    c_dict.get("outbound_shipping_procurement_relevance", "UNKNOWN"),
                    c_dict.get("broker_procurement_relevance", "UNKNOWN"),
                    c_dict.get("is_primary_contact", 0), c_dict.get("created_at")
                )
            )

        conn.execute("DROP TABLE contacts;")
        conn.execute("ALTER TABLE contacts_stage3a RENAME TO contacts;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_facility ON contacts(facility_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_carrier ON contacts(carrier_id);")
        conn.execute("PRAGMA foreign_keys = ON;")

        # Update corresponding claims for contacts 4, 5, 6
        conn.execute("UPDATE claims SET claimed_value = 'RECEPTION' WHERE contact_id = 4 AND claim_field = 'phone_directness';")
        conn.execute("UPDATE claims SET claimed_value = 'TOLL_FREE' WHERE contact_id = 5 AND claim_field = 'phone_directness';")
        conn.execute("UPDATE claims SET claimed_value = 'RECEPTION' WHERE contact_id = 6 AND claim_field = 'phone_directness';")

    # 3. Ensure prospect_lifecycle and discovery_intake_audit tables exist
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prospect_lifecycle (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_id INTEGER NOT NULL UNIQUE REFERENCES facilities(id) ON DELETE CASCADE,
            stage TEXT NOT NULL CHECK(stage IN ('DISCOVERY', 'QUALIFIED', 'SHORTLISTED', 'ARCHIVED')),
            entered_discovery_at TEXT NOT NULL,
            discovered_at TEXT,
            qualified_at TEXT,
            shortlisted_at TEXT,
            archived_at TEXT,
            qualification_notes TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prospect_lifecycle_stage ON prospect_lifecycle(stage);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prospect_lifecycle_fac ON prospect_lifecycle(facility_id);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_intake_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_name TEXT NOT NULL,
            candidate_company_name TEXT NOT NULL,
            candidate_facility_name TEXT NOT NULL,
            city TEXT NOT NULL,
            state_prov TEXT NOT NULL,
            country TEXT NOT NULL CHECK(country IN ('US', 'CA')),
            intake_fingerprint TEXT NOT NULL UNIQUE,
            intake_status TEXT NOT NULL CHECK(intake_status IN ('APPROVED_FOR_IMPORT', 'IMPORTED_DISCOVERY', 'DEFERRED_FOR_RESEARCH', 'REJECTED_OUT_OF_SCOPE', 'DUPLICATE_REMOVED', 'DUPLICATE_SUPPRESSED')),
            target_facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
            website_url TEXT,
            facility_address TEXT,
            batch_reference TEXT,
            reason_or_notes TEXT,
            reason_notes TEXT,
            reviewed_at TEXT,
            imported_at TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_intake_status ON discovery_intake_audit(intake_status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discovery_intake_fingerprint ON discovery_intake_audit(intake_fingerprint);")

    # 4. Backfill existing seed facilities (1, 2, 3, 4) into prospect_lifecycle as SHORTLISTED
    cur.execute("SELECT id FROM facilities WHERE id <= 4")
    seed_fac_ids = [r["id"] for r in cur.fetchall()]
    migration_ts = "2026-09-26T12:00:00Z"
    for fac_id in seed_fac_ids:
        conn.execute(
            """
            INSERT OR IGNORE INTO prospect_lifecycle (
                facility_id, stage, entered_discovery_at, discovered_at,
                qualified_at, shortlisted_at, archived_at, qualification_notes, notes, created_at, updated_at
            ) VALUES (?, 'SHORTLISTED', ?, ?, ?, ?, NULL, 'Audited seed prospect family', 'Audited seed prospect family', ?, ?)
            """,
            (fac_id, migration_ts, migration_ts, migration_ts, migration_ts, migration_ts, migration_ts)
        )

    # 5. Integrity & Foreign Key verification
    fk_errors = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if fk_errors:
        raise RuntimeError(f"Foreign key integrity check failed after Stage 3A migration: {fk_errors}")
    integrity = conn.execute("PRAGMA integrity_check;").fetchall()
    if not integrity or integrity[0][0] != "ok":
        raise RuntimeError(f"Database integrity check failed after Stage 3A migration: {integrity}")


def _migrate_stage3c_outreach_if_needed(conn: sqlite3.Connection) -> None:
    """
    Stage 3C CRM Migration:
    1. Recreate outreach_logs if needed to expand outcome CHECK constraint to include
       'INTERESTED', 'CALL_BACK', etc., and add feedback_notes, follow_up_at, created_at, disposition.
    2. Create prospect_engagement_state table if not exists.
    3. Ensure performance indexes exist.
    4. Initialize prospect_engagement_state for all existing companies as UNCONTACTED, attempt_count=0, is_viewed=0.
    5. Verify FK and database integrity.
    """
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='outreach_logs'")
    if not cur.fetchone():
        return  # Fresh DB; SCHEMA_DDL will create updated tables

    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='outreach_logs'")
    row = cur.fetchone()
    if row and ("'INTERESTED'" not in row[0]):
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute("ALTER TABLE outreach_logs RENAME TO outreach_logs_old;")
        conn.execute("""
        CREATE TABLE outreach_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
            facility_id INTEGER REFERENCES facilities(id) ON DELETE CASCADE,
            carrier_id INTEGER REFERENCES carriers(id) ON DELETE CASCADE,
            contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
            freight_demand_signal_id INTEGER REFERENCES freight_demand_signals(id) ON DELETE SET NULL,
            load_opportunity_id INTEGER REFERENCES load_opportunities(id) ON DELETE SET NULL,
            capacity_posting_id INTEGER REFERENCES capacity_postings(id) ON DELETE SET NULL,
            outreach_channel TEXT NOT NULL DEFAULT 'PHONE' CHECK(outreach_channel IN ('PHONE', 'EMAIL', 'IN_PERSON')),
            outcome TEXT NOT NULL CHECK(outcome IN ('INTERESTED', 'NOT_INTERESTED', 'NO_ANSWER', 'CALL_BACK', 'CONNECTED_DECISION_MAKER', 'CONNECTED_GATEKEEPER', 'LEFT_VOICEMAIL', 'WRONG_CONTACT')),
            disposition TEXT CHECK(disposition IS NULL OR disposition IN ('INTERESTED', 'NOT_INTERESTED', 'NO_ANSWER', 'CALL_BACK', 'CONNECTED_DECISION_MAKER', 'CONNECTED_GATEKEEPER', 'LEFT_VOICEMAIL', 'WRONG_CONTACT')),
            feedback_notes TEXT,
            notes TEXT,
            shipping_procurement_findings TEXT,
            broker_policy_findings TEXT,
            private_fleet_findings TEXT,
            contacted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            follow_up_date DATE,
            follow_up_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            CHECK (
                company_id IS NOT NULL OR
                facility_id IS NOT NULL OR
                carrier_id IS NOT NULL
            )
        );
        """)
        conn.execute("""
        INSERT INTO outreach_logs (id, company_id, facility_id, carrier_id, contact_id, freight_demand_signal_id, load_opportunity_id, capacity_posting_id, outreach_channel, outcome, shipping_procurement_findings, broker_policy_findings, private_fleet_findings, notes, contacted_at, follow_up_date)
        SELECT id, company_id, facility_id, carrier_id, contact_id, freight_demand_signal_id, load_opportunity_id, capacity_posting_id, outreach_channel, outcome, shipping_procurement_findings, broker_policy_findings, private_fleet_findings, notes, contacted_at, follow_up_date
        FROM outreach_logs_old;
        """)
        conn.execute("DROP TABLE outreach_logs_old;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_outreach_company ON outreach_logs(company_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_outreach_facility ON outreach_logs(facility_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_outreach_contacted_at ON outreach_logs(contacted_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_outreach_outcome ON outreach_logs(outcome);")
        conn.execute("PRAGMA foreign_keys = ON;")

    # Ensure prospect_engagement_state exists and supports all 8 dispositions
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='prospect_engagement_state'")
    pes_row = cur.fetchone()
    if not pes_row:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS prospect_engagement_state (
            company_id INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            current_outreach_status TEXT NOT NULL DEFAULT 'UNCONTACTED' CHECK(current_outreach_status IN (
                'UNCONTACTED', 'INTERESTED', 'NOT_INTERESTED', 'NO_ANSWER', 'CALL_BACK',
                'CONNECTED_DECISION_MAKER', 'CONNECTED_GATEKEEPER', 'LEFT_VOICEMAIL', 'WRONG_CONTACT'
            )),
            status_source_outreach_log_id INTEGER REFERENCES outreach_logs(id) ON DELETE SET NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_contacted_at DATETIME,
            next_follow_up_at DATETIME,
            last_facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
            last_feedback_notes TEXT,
            is_viewed INTEGER NOT NULL DEFAULT 0,
            first_viewed_at DATETIME,
            last_viewed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_status ON prospect_engagement_state(current_outreach_status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_follow_up ON prospect_engagement_state(next_follow_up_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_viewed ON prospect_engagement_state(is_viewed);")
        conn.execute("""
        INSERT OR IGNORE INTO prospect_engagement_state (company_id, current_outreach_status, attempt_count, is_viewed, created_at, updated_at)
        SELECT id, 'UNCONTACTED', 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM companies;
        """)
    elif "'CONNECTED_DECISION_MAKER'" not in pes_row[0]:
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute("PRAGMA legacy_alter_table = ON;")
        conn.execute("ALTER TABLE prospect_engagement_state RENAME TO prospect_engagement_state_old;")
        conn.execute("""
        CREATE TABLE prospect_engagement_state (
            company_id INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            current_outreach_status TEXT NOT NULL DEFAULT 'UNCONTACTED' CHECK(current_outreach_status IN (
                'UNCONTACTED', 'INTERESTED', 'NOT_INTERESTED', 'NO_ANSWER', 'CALL_BACK',
                'CONNECTED_DECISION_MAKER', 'CONNECTED_GATEKEEPER', 'LEFT_VOICEMAIL', 'WRONG_CONTACT'
            )),
            status_source_outreach_log_id INTEGER REFERENCES outreach_logs(id) ON DELETE SET NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_contacted_at DATETIME,
            next_follow_up_at DATETIME,
            last_facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
            last_feedback_notes TEXT,
            is_viewed INTEGER NOT NULL DEFAULT 0,
            first_viewed_at DATETIME,
            last_viewed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("""
        INSERT INTO prospect_engagement_state (
            company_id, current_outreach_status, status_source_outreach_log_id,
            attempt_count, last_contacted_at, next_follow_up_at, last_facility_id,
            last_feedback_notes, is_viewed, first_viewed_at, last_viewed_at, created_at, updated_at
        )
        SELECT 
            company_id, current_outreach_status, status_source_outreach_log_id,
            attempt_count, last_contacted_at, next_follow_up_at, last_facility_id,
            last_feedback_notes, is_viewed, first_viewed_at, last_viewed_at, created_at, updated_at
        FROM prospect_engagement_state_old;
        """)
        conn.execute("DROP TABLE prospect_engagement_state_old;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_status ON prospect_engagement_state(current_outreach_status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_follow_up ON prospect_engagement_state(next_follow_up_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_viewed ON prospect_engagement_state(is_viewed);")
        conn.execute("PRAGMA legacy_alter_table = OFF;")
        conn.execute("PRAGMA foreign_keys = ON;")

    # Ensure evidence_sources supports expanded source types
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence_sources'")
    es_row = cur.fetchone()
    if es_row and ("'TRADE_ASSOCIATION'" not in es_row[0]):
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute("PRAGMA legacy_alter_table = ON;")
        conn.execute("ALTER TABLE evidence_sources RENAME TO evidence_sources_old;")
        conn.execute("""
        CREATE TABLE evidence_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL CHECK(source_type IN (
                'COMPANY_WEBSITE', 'FIRST_PARTY', 'GOVERNMENT_REGISTRY', 'GOVERNMENT_REGULATOR',
                'TRADE_ASSOCIATION', 'INDUSTRY_DIRECTORY', 'DIRECTORY_AGGREGATOR', 'JOB_POSTING',
                'PHONE_OUTREACH', 'EMAIL_CORRESPONDENCE', 'OTHER_SECONDARY', 'MANUAL_USER_OBSERVED'
            )),
            source_title_publisher TEXT NOT NULL,
            source_url TEXT,
            is_primary_source BOOLEAN,
            source_published_at DATETIME,
            event_at DATETIME,
            observed_at DATETIME NOT NULL,
            outreach_log_id INTEGER REFERENCES outreach_logs(id) ON DELETE SET NULL,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("""
        INSERT INTO evidence_sources (
            id, source_type, source_title_publisher, source_url, is_primary_source,
            source_published_at, event_at, observed_at, outreach_log_id, notes, created_at
        )
        SELECT 
            id, source_type, source_title_publisher, source_url, is_primary_source,
            source_published_at, event_at, observed_at, outreach_log_id, notes, created_at
        FROM evidence_sources_old;
        """)
        conn.execute("DROP TABLE evidence_sources_old;")
        conn.execute("PRAGMA legacy_alter_table = OFF;")
        conn.execute("PRAGMA foreign_keys = ON;")

    fk_errors = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if fk_errors:
        raise RuntimeError(f"Foreign key integrity check failed after Stage 3C migration: {fk_errors}")
    integrity = conn.execute("PRAGMA integrity_check;").fetchall()
    if not integrity or integrity[0][0] != "ok":
        raise RuntimeError(f"Database integrity check failed after Stage 3C migration: {integrity}")


def init_db(db_path: Optional[str | Path] = None) -> None:
    """
    Initialize SQLite schema idempotently.
    Creates all physical tables, partial unique indexes, and default settings.
    Handles legacy table/view migration if present. Safe to run repeatedly.
    """
    with get_db_connection(db_path, create_if_missing=True) as conn:
        _migrate_legacy_suppressions_if_needed(conn)
        _migrate_stage3a_if_needed(conn)
        _migrate_stage3c_outreach_if_needed(conn)
        conn.executescript(SCHEMA_DDL)

        # Seed default settings idempotently
        for key, val, vtype, desc in DEFAULT_SETTINGS:
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (setting_key, setting_value, value_type, description)
                VALUES (?, ?, ?, ?)
                """,
                (key, val, vtype, desc)
            )


if __name__ == "__main__":
    init_db()
    print("Database schema successfully initialized.")
