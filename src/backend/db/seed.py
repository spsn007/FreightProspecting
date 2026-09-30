"""
FreightProspecting V1 — Audited Seed Ingestion Engine (Stage 2)
Seeds strictly the 4 approved audited candidate families:
1. Beasley Forest Products / Beasley Group
2. Kenwal Steel Corp.
3. DECAST Ltd.
4. WMG Technologies

Enforces zero fake loads, zero fake capacity, zero fake demand signals,
full claims/evidence provenance, and strict idempotency.
"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Optional

from src.backend.db.claims_engine import (
    link_claim_evidence,
    record_claim,
    record_evidence_source,
)
from src.backend.db.connection import get_db_connection
from src.backend.db.schema import init_db

OBSERVED_DATE = "2026-09-26T12:00:00Z"


def seed_database(db_path: Optional[str | Path] = None) -> None:
    """
    Idempotent seeding of the 4 approved audited seed families.
    If the companies already exist, the seeding operation skips insertion to avoid duplication.
    """
    init_db(db_path)

    with get_db_connection(db_path) as conn:
        # Check if already seeded
        existing_companies = {
            row["operating_brand"]
            for row in conn.execute("SELECT operating_brand FROM companies").fetchall()
        }

        # =====================================================================
        # SEED 1: Beasley Forest Products / Beasley Group
        # =====================================================================
        if "Beasley Forest Products" not in existing_companies:
            # 1. Company
            cur = conn.execute(
                """
                INSERT INTO companies (operating_brand, legal_name, corporate_address, website_url, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "Beasley Forest Products",
                    "Beasley Forest Products, Inc.",
                    "770 Uvalda Hwy, Hazlehurst, GA 31539, USA",
                    "https://www.beasleyforestproducts.com",
                    "Part of The Beasley Group. Operates sawmills, crane mat, and pallet lumber manufacturing.",
                ),
            )
            beasley_comp_id = cur.lastrowid

            # Company Evidence Source
            b_src_id = record_evidence_source(
                conn=conn,
                source_type="COMPANY_WEBSITE",
                source_title_publisher="Beasley Forest Products Official Homepage",
                source_url="https://www.beasleyforestproducts.com",
                is_primary_source=True,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="Primary corporate website for Beasley Forest Products / Beasley Group. Hazlehurst Sawmill operating site verified at 770 Uvalda Hwy, Hazlehurst, GA 31539 (confirmed by official contact directory, OSHA 2024 inspection, and Georgia corporate registry).",
            )

            # Company Claim
            b_claim_brand = record_claim(
                conn=conn,
                claim_field="operating_brand",
                claimed_value="Beasley Forest Products",
                verification_status="VERIFIED",
                is_current_accepted=True,
                company_id=beasley_comp_id,
            )
            link_claim_evidence(conn, b_claim_brand, b_src_id, "SUPPORTS")

            # 2. Facility
            cur = conn.execute(
                """
                INSERT INTO facilities (
                    company_id, facility_name, facility_type, physical_address,
                    city, state_prov, postal_code, country,
                    private_fleet_present, vehicle_asset_ownership,
                    fleet_relationship_type, commercial_carrier_use,
                    broker_friendly_status, freight_procurement_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    beasley_comp_id,
                    "Hazlehurst Sawmill",
                    "SAWMILL",
                    "770 Uvalda Hwy",
                    "Hazlehurst",
                    "GA",
                    "31539",
                    "US",
                    "VERIFIED_PRESENT",
                    "VERIFIED_OWNED",
                    "IN_HOUSE_OWNED",
                    "UNKNOWN",
                    "UNKNOWN",
                    "CORPORATE_PARENT",
                ),
            )
            beasley_fac_id = cur.lastrowid

            b_claim_addr = record_claim(
                conn=conn,
                claim_field="physical_address",
                claimed_value="770 Uvalda Hwy, Hazlehurst, GA 31539, US",
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes="Verified operating facility address of Beasley Forest Products Hazlehurst Sawmill (confirmed by official corporate website, OSHA 2024 inspection, and Georgia corporate registry).",
                facility_id=beasley_fac_id,
            )
            link_claim_evidence(conn, b_claim_addr, b_src_id, "SUPPORTS")

            # Facility Fleet Evidence (Beasley Logistics fleet)
            b_logistics_src = record_evidence_source(
                conn=conn,
                source_type="COMPANY_WEBSITE",
                source_title_publisher="Beasley Group Logistics Division Profile",
                source_url="https://www.beasleygroup.com",
                is_primary_source=True,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="Audited evidence: Beasley Logistics operates >100 tractors and 400 trailers.",
            )
            b_claim_fleet = record_claim(
                conn=conn,
                claim_field="private_fleet_present",
                claimed_value="VERIFIED_PRESENT",
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes="Operates Beasley Logistics private fleet (>100 tractors / 400 trailers). Outside commercial carrier use unverified.",
                facility_id=beasley_fac_id,
            )
            link_claim_evidence(conn, b_claim_fleet, b_logistics_src, "SUPPORTS")

            b_claim_fleet_rel = record_claim(
                conn=conn,
                claim_field="fleet_relationship_type",
                claimed_value="IN_HOUSE_OWNED",
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes="Operates Beasley Logistics as an in-house motor carrier division.",
                facility_id=beasley_fac_id,
            )
            link_claim_evidence(conn, b_claim_fleet_rel, b_logistics_src, "SUPPORTS")

            # 3. Facility Commodities
            cur = conn.execute(
                """
                INSERT INTO facility_commodities (
                    facility_id, commodity_category, specific_products,
                    equipment_category, equipment_usage_status,
                    trailer_specs_notes, securement_tarp_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    beasley_fac_id,
                    "Forest Products",
                    "Hardwood lumber, pallet cants, crane mats, timber mats, railroad crossties",
                    "FLATBED",
                    "VERIFIED",
                    None,
                    None,
                ),
            )
            beasley_comm_id = cur.lastrowid

            b_claim_comm = record_claim(
                conn=conn,
                claim_field="equipment_category",
                claimed_value="FLATBED",
                verification_status="VERIFIED",
                is_current_accepted=True,
                facility_commodity_id=beasley_comm_id,
            )
            link_claim_evidence(conn, b_claim_comm, b_src_id, "SUPPORTS")

            # 4. Contacts (Preserving named person != direct line distinction)
            # Contact 1: Phil Clements (Sawmill Manager, general switchboard)
            cur = conn.execute(
                """
                INSERT INTO contacts (
                    facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_directness, email_directness,
                    role_category, outbound_shipping_procurement_relevance,
                    broker_procurement_relevance, is_primary_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    beasley_fac_id,
                    "NAMED_PERSON",
                    "Phil Clements",
                    "Sawmill Manager",
                    "Operations",
                    "(912) 375-5174",
                    "GENERAL_SWITCHBOARD",
                    "UNKNOWN",
                    "OPERATIONS",
                    "UNKNOWN",
                    "UNKNOWN",
                    0,
                ),
            )
            c1_id = cur.lastrowid
            c1_claim = record_claim(
                conn=conn,
                claim_field="phone_directness",
                claimed_value="GENERAL_SWITCHBOARD",
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes="Published via general mill switchboard; direct extension unconfirmed. Broker procurement policy UNKNOWN.",
                contact_id=c1_id,
            )
            link_claim_evidence(conn, c1_claim, b_src_id, "SUPPORTS")

            # Contact 2: Mark Joiner (Logistics Manager, direct line)
            b_joiner_src = record_evidence_source(
                conn=conn,
                source_type="INDUSTRY_DIRECTORY",
                source_title_publisher="Verified Industry Logistics Listing / Direct Confirmation",
                source_url=None,  # Offline/directory evidence without persistent URL
                is_primary_source=False,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="Audited logistics contact for Beasley Group: (912) 347-5930.",
            )
            cur = conn.execute(
                """
                INSERT INTO contacts (
                    facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_directness, email_directness,
                    role_category, outbound_shipping_procurement_relevance,
                    broker_procurement_relevance, is_primary_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    beasley_fac_id,
                    "NAMED_PERSON",
                    "Mark Joiner",
                    "Logistics Manager",
                    "Logistics",
                    "(912) 347-5930",
                    "DIRECT_PERSON",
                    "UNKNOWN",
                    "FREIGHT_LOGISTICS",
                    "VERIFIED",
                    "UNKNOWN",
                    1,
                ),
            )
            c2_id = cur.lastrowid
            c2_claim = record_claim(
                conn=conn,
                claim_field="phone_directness",
                claimed_value="DIRECT_PERSON",
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes="Direct telephone number verified. Manages internal fleet; outside freight broker policy remains UNKNOWN.",
                contact_id=c2_id,
            )
            link_claim_evidence(conn, c2_claim, b_joiner_src, "SUPPORTS")

        # =====================================================================
        # SEED 2: Kenwal Steel Corp.
        # =====================================================================
        if "Kenwal Steel Corp." not in existing_companies:
            # 1. Company
            cur = conn.execute(
                """
                INSERT INTO companies (operating_brand, legal_name, corporate_address, website_url, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "Kenwal Steel Corp.",
                    "Kenwal Steel Corp.",
                    "8223 W. Warren, Dearborn, MI 48126, USA",
                    "https://www.kenwal.com",
                    "Flat-rolled steel service center specializing in automotive and industrial steel processing.",
                ),
            )
            kenwal_comp_id = cur.lastrowid

            k_src_id = record_evidence_source(
                conn=conn,
                source_type="COMPANY_WEBSITE",
                source_title_publisher="Kenwal Steel Official Website",
                source_url="https://www.kenwal.com",
                is_primary_source=True,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="Primary corporate site for Kenwal Steel Corp. Dearborn Service Center.",
            )

            k_claim_brand = record_claim(
                conn=conn,
                claim_field="operating_brand",
                claimed_value="Kenwal Steel Corp.",
                verification_status="VERIFIED",
                is_current_accepted=True,
                company_id=kenwal_comp_id,
            )
            link_claim_evidence(conn, k_claim_brand, k_src_id, "SUPPORTS")

            # 2. Facility
            cur = conn.execute(
                """
                INSERT INTO facilities (
                    company_id, facility_name, facility_type, physical_address,
                    city, state_prov, postal_code, country,
                    private_fleet_present, vehicle_asset_ownership,
                    fleet_relationship_type, commercial_carrier_use,
                    broker_friendly_status, freight_procurement_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kenwal_comp_id,
                    "Dearborn Steel Service Center",
                    "STEEL_SERVICE_CENTER",
                    "8223 W. Warren",
                    "Dearborn",
                    "MI",
                    "48126",
                    "US",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "FACILITY_LEVEL",
                ),
            )
            kenwal_fac_id = cur.lastrowid

            # Private fleet invariant: Lack of FMCSA entry != No private fleet
            k_claim_fleet = record_claim(
                conn=conn,
                claim_field="private_fleet_present",
                claimed_value="UNKNOWN",
                verification_status="UNKNOWN",
                is_current_accepted=True,
                claim_notes="Absence of evidence is not evidence of absence. Lack of public carrier listing does not prove absence of fleet.",
                facility_id=kenwal_fac_id,
            )
            link_claim_evidence(conn, k_claim_fleet, k_src_id, "CONTEXT")

            # 3. Facility Commodities
            cur = conn.execute(
                """
                INSERT INTO facility_commodities (
                    facility_id, commodity_category, specific_products,
                    equipment_category, equipment_usage_status,
                    trailer_specs_notes, securement_tarp_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kenwal_fac_id,
                    "Steel Processing",
                    "Flat-rolled steel coils, slit coils, master coils",
                    "FLATBED",
                    "VERIFIED",
                    None,
                    None,
                ),
            )
            kenwal_comm_id = cur.lastrowid
            k_claim_comm = record_claim(
                conn=conn,
                claim_field="equipment_category",
                claimed_value="FLATBED",
                verification_status="VERIFIED",
                is_current_accepted=True,
                facility_commodity_id=kenwal_comm_id,
            )
            link_claim_evidence(conn, k_claim_comm, k_src_id, "SUPPORTS")

            # 4. Contacts (General Switchboard only; direct traffic contact UNKNOWN)
            cur = conn.execute(
                """
                INSERT INTO contacts (
                    facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_directness, email_directness,
                    role_category, outbound_shipping_procurement_relevance,
                    broker_procurement_relevance, is_primary_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kenwal_fac_id,
                    "GENERAL_FACILITY",
                    None,
                    "Main Switchboard",
                    "Corporate / Reception",
                    "(313) 739-1000",
                    "GENERAL_SWITCHBOARD",
                    "UNKNOWN",
                    "GENERAL_FACILITY",
                    "UNKNOWN",
                    "UNKNOWN",
                    1,
                ),
            )
            k_contact_id = cur.lastrowid
            k_contact_claim = record_claim(
                conn=conn,
                claim_field="phone_directness",
                claimed_value="GENERAL_SWITCHBOARD",
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes="Direct shipping/traffic coordinator contact is UNKNOWN. Outreach must navigate switchboard.",
                contact_id=k_contact_id,
            )
            link_claim_evidence(conn, k_contact_claim, k_src_id, "SUPPORTS")

        # =====================================================================
        # SEED 3: DECAST Ltd.
        # =====================================================================
        if "DECAST Ltd." not in existing_companies:
            # 1. Company
            cur = conn.execute(
                """
                INSERT INTO companies (operating_brand, legal_name, corporate_address, website_url, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "DECAST Ltd.",
                    "DECAST Ltd.",
                    "8807 County Road 56, Utopia, ON L0M 1T0, Canada",
                    "https://decastltd.com",
                    "Leading Canadian precast concrete infrastructure manufacturer.",
                ),
            )
            decast_comp_id = cur.lastrowid

            d_src_id = record_evidence_source(
                conn=conn,
                source_type="COMPANY_WEBSITE",
                source_title_publisher="DECAST Ltd. Official Website",
                source_url="https://decastltd.com",
                is_primary_source=True,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="Corporate homepage and facility overview for DECAST Ltd.",
            )
            d_claim_brand = record_claim(
                conn=conn,
                claim_field="operating_brand",
                claimed_value="DECAST Ltd.",
                verification_status="VERIFIED",
                is_current_accepted=True,
                company_id=decast_comp_id,
            )
            link_claim_evidence(conn, d_claim_brand, d_src_id, "SUPPORTS")

            # 2. Facility
            cur = conn.execute(
                """
                INSERT INTO facilities (
                    company_id, facility_name, facility_type, physical_address,
                    city, state_prov, postal_code, country,
                    private_fleet_present, vehicle_asset_ownership,
                    fleet_relationship_type, commercial_carrier_use,
                    broker_friendly_status, freight_procurement_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decast_comp_id,
                    "Utopia Precast Plant",
                    "PRECAST_PLANT",
                    "8807 County Road 56",
                    "Utopia",
                    "ON",
                    "L0M 1T0",
                    "CA",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "FACILITY_LEVEL",
                ),
            )
            decast_fac_id = cur.lastrowid

            # Job Ad as Category A operational evidence (NOT a freight demand signal, NOT proof of fleet ownership)
            d_job_src = record_evidence_source(
                conn=conn,
                source_type="JOB_POSTING",
                source_title_publisher="DECAST Careers — AZ Float Driver Posting",
                source_url="https://decastltd.com/careers/",
                is_primary_source=False,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="Category A operational evidence: AZ Driver hiring proves internal transport capability; does NOT constitute a freight demand signal or proof of fleet asset ownership.",
            )
            d_claim_fleet = record_claim(
                conn=conn,
                claim_field="private_fleet_present",
                claimed_value="UNKNOWN",
                verification_status="UNKNOWN",
                is_current_accepted=True,
                claim_notes="AZ Float Driver hiring proves internal transport operation/driver activity, but does not prove private fleet asset ownership; vehicle ownership remains UNKNOWN.",
                facility_id=decast_fac_id,
            )
            link_claim_evidence(conn, d_claim_fleet, d_job_src, "SUPPORTS")

            # 3. Facility Commodities
            cur = conn.execute(
                """
                INSERT INTO facility_commodities (
                    facility_id, commodity_category, specific_products,
                    equipment_category, equipment_usage_status,
                    trailer_specs_notes, securement_tarp_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decast_fac_id,
                    "Precast Concrete Products",
                    "Precast concrete drainage, bridge girders, concrete pressure pipes, tunnel segments",
                    "STEP_DECK",
                    "INFERRED",
                    None,
                    None,
                ),
            )
            decast_comm_id = cur.lastrowid
            d_claim_comm = record_claim(
                conn=conn,
                claim_field="equipment_category",
                claimed_value="STEP_DECK",
                verification_status="INFERRED",
                is_current_accepted=True,
                claim_notes="Suitability inference based on precast concrete infrastructure dimensions and AZ Float Driver recruitment; actual step deck bill of lading not verified.",
                facility_commodity_id=decast_comm_id,
            )
            link_claim_evidence(conn, d_claim_comm, d_src_id, "CONTEXT")

            # 4. Contacts
            # Contact 1: Main Reception
            cur = conn.execute(
                """
                INSERT INTO contacts (
                    facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_directness, email_address, email_directness,
                    role_category, outbound_shipping_procurement_relevance,
                    broker_procurement_relevance, is_primary_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decast_fac_id,
                    "GENERAL_FACILITY",
                    None,
                    "Main Reception",
                    "General Administration",
                    "(705) 734-2892",
                    "RECEPTION",
                    "info@decastltd.com",
                    "GENERAL",
                    "GENERAL_FACILITY",
                    "UNKNOWN",
                    "UNKNOWN",
                    1,
                ),
            )
            d_contact1_id = cur.lastrowid
            d_c1_claim = record_claim(
                conn=conn,
                claim_field="phone_directness",
                claimed_value="RECEPTION",
                verification_status="VERIFIED",
                is_current_accepted=True,
                contact_id=d_contact1_id,
            )
            link_claim_evidence(conn, d_c1_claim, d_src_id, "SUPPORTS")

            # Contact 2: Toll-Free Line
            cur = conn.execute(
                """
                INSERT INTO contacts (
                    facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_directness, email_address, email_directness,
                    role_category, outbound_shipping_procurement_relevance,
                    broker_procurement_relevance, is_primary_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decast_fac_id,
                    "GENERAL_FACILITY",
                    None,
                    "Toll-Free Customer Line",
                    "Inquiries",
                    "(800) 461-5632",
                    "TOLL_FREE",
                    None,
                    "UNKNOWN",
                    "GENERAL_FACILITY",
                    "UNKNOWN",
                    "UNKNOWN",
                    0,
                ),
            )
            d_contact2_id = cur.lastrowid
            d_c2_claim = record_claim(
                conn=conn,
                claim_field="phone_directness",
                claimed_value="TOLL_FREE",
                verification_status="VERIFIED",
                is_current_accepted=True,
                contact_id=d_contact2_id,
            )
            link_claim_evidence(conn, d_c2_claim, d_src_id, "SUPPORTS")

        # =====================================================================
        # SEED 4: WMG Technologies (with audited 2026 verification)
        # =====================================================================
        if "WMG Technologies" not in existing_companies:
            # 1. Company Parent: ABC Technologies Holdings Inc.
            cur = conn.execute(
                """
                INSERT INTO companies (operating_brand, legal_name, corporate_address, website_url, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "ABC Technologies",
                    "ABC Technologies Holdings Inc.",
                    "Toronto, ON, Canada / Auburn Hills, MI, USA",
                    "https://abctechnologies.com",
                    "Global automotive Tier-1 supplier. Rebranded commercially as TI Automotive following April 2025 TI Fluid Systems acquisition.",
                ),
            )
            abc_comp_id = cur.lastrowid

            # 2. Company: WMG Technologies
            cur = conn.execute(
                """
                INSERT INTO companies (operating_brand, legal_name, corporate_address, website_url, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "WMG Technologies",
                    "Windsor Mold Inc.",
                    "4035 Malden Road, Windsor, ON N9C 2G4, Canada",
                    "https://wmgtec.com",
                    "Automotive tooling and injection mold solutions provider (formerly Windsor Mold Group). Acquired 2023 by ABC Technologies.",
                ),
            )
            wmg_comp_id = cur.lastrowid

            wmg_src_id = record_evidence_source(
                conn=conn,
                source_type="COMPANY_WEBSITE",
                source_title_publisher="WMG Technologies Official Website",
                source_url="https://wmgtec.com",
                is_primary_source=True,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="Primary website for WMG Technologies (copyright 2026). Tooling and molded products operations in Windsor, ON.",
            )

            wmg_claim_brand = record_claim(
                conn=conn,
                claim_field="operating_brand",
                claimed_value="WMG Technologies",
                verification_status="VERIFIED",
                is_current_accepted=True,
                company_id=wmg_comp_id,
            )
            link_claim_evidence(conn, wmg_claim_brand, wmg_src_id, "SUPPORTS")

            # Verified Legal Name from active PO Terms & Conditions
            wmg_terms_src = record_evidence_source(
                conn=conn,
                source_type="COMPANY_WEBSITE",
                source_title_publisher="WMG Technologies Purchase Order Terms & Conditions",
                source_url="https://wmgtec.com/for-suppliers/",
                is_primary_source=True,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="Purchase order terms confirm Windsor Mold Inc. as active Canadian contracting legal entity.",
            )
            wmg_claim_legal = record_claim(
                conn=conn,
                claim_field="legal_name",
                claimed_value="Windsor Mold Inc.",
                verification_status="VERIFIED",
                is_current_accepted=True,
                company_id=wmg_comp_id,
            )
            link_claim_evidence(conn, wmg_claim_legal, wmg_terms_src, "SUPPORTS")

            # Corporate Relationship (Acquisition March 1, 2023 verified; exact current internal tier UNKNOWN)
            wmg_acq_src = record_evidence_source(
                conn=conn,
                source_type="INDUSTRY_DIRECTORY",
                source_title_publisher="ABC Technologies Acquisition Completion Announcement",
                source_url="https://www.businesswire.com/news/home/20230301006137/en/",
                is_primary_source=False,
                source_published_at="2023-03-01T12:00:00Z",
                event_at="2023-03-01T12:00:00Z",
                observed_at=OBSERVED_DATE,
                notes="ABC Technologies completed acquisition of 100% shares of WMG Technologies Holdings Inc. on March 1, 2023.",
            )

            cur = conn.execute(
                """
                INSERT INTO company_relationships (
                    parent_company_id, child_company_id, relationship_type,
                    valid_from, valid_to, is_current, verification_status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    abc_comp_id,
                    wmg_comp_id,
                    "ACQUISITION",
                    "2023-03-01",
                    None,
                    1,
                    "VERIFIED",
                    "Acquired 100% shares on March 1, 2023. Operates within TI Automotive group umbrella. Exact 2026 intermediate holding tier remains UNKNOWN.",
                ),
            )
            rel_id = cur.lastrowid
            wmg_rel_claim = record_claim(
                conn=conn,
                claim_field="relationship_type",
                claimed_value="ACQUISITION",
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes="Dated 2023 acquisition verified. Exact present-day legal subsidiary chain inside TI Automotive is unlisted/UNKNOWN.",
                company_relationship_id=rel_id,
            )
            link_claim_evidence(conn, wmg_rel_claim, wmg_acq_src, "SUPPORTS")

            # 3. Facility (4035 Malden Road)
            cur = conn.execute(
                """
                INSERT INTO facilities (
                    company_id, facility_name, facility_type, physical_address,
                    city, state_prov, postal_code, country,
                    private_fleet_present, vehicle_asset_ownership,
                    fleet_relationship_type, commercial_carrier_use,
                    broker_friendly_status, freight_procurement_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wmg_comp_id,
                    "Tooling Division (Malden Location)",
                    "TOOLING_PLANT",
                    "4035 Malden Road",
                    "Windsor",
                    "ON",
                    "N9C 2G4",
                    "CA",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                    "UNKNOWN",
                ),
            )
            wmg_fac_id = cur.lastrowid

            wmg_contact_src = record_evidence_source(
                conn=conn,
                source_type="COMPANY_WEBSITE",
                source_title_publisher="WMG Technologies Contact Directory",
                source_url="https://wmgtec.com/contact-us/",
                is_primary_source=True,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes="4035 Malden Rd confirmed as Tooling Division facility; phone (519) 972-9032.",
            )
            wmg_fac_claim = record_claim(
                conn=conn,
                claim_field="physical_address",
                claimed_value="4035 Malden Road, Windsor, ON N9C 2G4",
                verification_status="VERIFIED",
                is_current_accepted=True,
                facility_id=wmg_fac_id,
            )
            link_claim_evidence(conn, wmg_fac_claim, wmg_contact_src, "SUPPORTS")

            # 4. Facility Commodities (Inferred equipment suitability, NOT verified usage)
            cur = conn.execute(
                """
                INSERT INTO facility_commodities (
                    facility_id, commodity_category, specific_products,
                    equipment_category, equipment_usage_status,
                    trailer_specs_notes, securement_tarp_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wmg_fac_id,
                    "Tooling & Molded Products",
                    "Automotive injection molds, tooling solutions, optic inserts, exterior/interior molded components",
                    "FLATBED",
                    "INFERRED",
                    None,
                    None,
                ),
            )
            wmg_comm_id = cur.lastrowid
            wmg_comm_claim = record_claim(
                conn=conn,
                claim_field="equipment_category",
                claimed_value="FLATBED",
                verification_status="INFERRED",
                is_current_accepted=True,
                claim_notes="Suitability inference based on industrial tooling/mold dimensions; bills of lading not verified.",
                facility_commodity_id=wmg_comm_id,
            )
            link_claim_evidence(conn, wmg_comm_claim, wmg_src_id, "CONTEXT")

            # 5. Contacts (Direct logistics desk UNKNOWN; general facility reception only)
            cur = conn.execute(
                """
                INSERT INTO contacts (
                    facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_directness, email_directness,
                    role_category, outbound_shipping_procurement_relevance,
                    broker_procurement_relevance, is_primary_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    wmg_fac_id,
                    "GENERAL_FACILITY",
                    None,
                    "Tooling Division Reception",
                    "Tooling Division",
                    "(519) 972-9032",
                    "RECEPTION",
                    "UNKNOWN",
                    "GENERAL_FACILITY",
                    "UNKNOWN",
                    "UNKNOWN",
                    1,
                ),
            )
            wmg_cont_id = cur.lastrowid
            wmg_cont_claim = record_claim(
                conn=conn,
                claim_field="phone_directness",
                claimed_value="RECEPTION",
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes="Published main plant telephone. Direct outbound shipping/traffic coordinator contact is UNKNOWN.",
                contact_id=wmg_cont_id,
            )
            link_claim_evidence(conn, wmg_cont_claim, wmg_contact_src, "SUPPORTS")

        # Ensure all 4 seed facilities are populated in prospect_lifecycle as SHORTLISTED
        cur = conn.execute("SELECT id FROM facilities WHERE id <= 4")
        for row in cur.fetchall():
            fac_id = row["id"]
            conn.execute(
                """
                INSERT OR IGNORE INTO prospect_lifecycle (
                    facility_id, stage, entered_discovery_at, discovered_at,
                    qualified_at, shortlisted_at, archived_at, qualification_notes, notes, created_at, updated_at
                ) VALUES (?, 'SHORTLISTED', ?, ?, ?, ?, NULL, 'Audited seed prospect family', 'Audited seed prospect family', ?, ?)
                """,
                (fac_id, OBSERVED_DATE, OBSERVED_DATE, OBSERVED_DATE, OBSERVED_DATE, OBSERVED_DATE, OBSERVED_DATE)
            )


if __name__ == "__main__":
    seed_database()
    print("Audited seed records successfully ingested.")
