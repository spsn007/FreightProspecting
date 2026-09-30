"""
FreightProspecting V1 — Batch #1 Discovery Pool Importer
Imports exactly 39 approved manufacturing facilities into the Discovery Pool.
Registers 3 deferred candidates in discovery_intake_audit.
Preserves exact provenance, canonical ISO-8601 timestamps, and full idempotence.
"""

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional

from src.backend.db.connection import get_db_connection
from src.backend.db.schema import init_db
from src.backend.db.claims_engine import record_claim, record_evidence_source, link_claim_evidence

OBSERVED_DATE = "2026-09-26T12:00:00Z"
BATCH_NAME = "Prospect Expansion Batch #1"


def compute_intake_fingerprint(brand: str, address: str, city: str, state_prov: str, country: str) -> str:
    """Deterministic multi-plant safe fingerprint: brand|address|city|state_prov|country"""
    raw = f"{brand}|{address}|{city}|{state_prov}|{country}"
    return re.sub(r"[^a-z0-9|]", "", raw.lower().strip())


DEFERRED_CANDIDATES = [
    {
        "company_name": "Cruse Lumber Company, Inc.",
        "facility_name": "Morganton Sawmill",
        "city": "Morganton",
        "state_prov": "GA",
        "country": "US",
        "address": "16490 Morganton Hwy, Morganton, GA 30560",
        "website_url": None,
        "reason_notes": "Relies exclusively on secondary directory listings (GFC); does not maintain an active corporate website; lacks verified email; address shifted from Blue Ridge to Morganton.",
    },
    {
        "company_name": "Woody Lumber Company",
        "facility_name": "Toomsboro Sawmill",
        "city": "Toomsboro",
        "state_prov": "GA",
        "country": "US",
        "address": "169 Branan Road, Toomsboro, GA 31090",
        "website_url": None,
        "reason_notes": "Relies exclusively on state directory listings; lacks active corporate website and email; address shifted from Gordon to Toomsboro; requires direct facility confirmation prior to Discovery Pool ingestion.",
    },
    {
        "company_name": "Claude Howard Lumber Company, Inc.",
        "facility_name": "Statesboro Yellow Pine Sawmill",
        "city": "Statesboro",
        "state_prov": "GA",
        "country": "US",
        "address": "600 Park Avenue, Statesboro, GA 30458",
        "website_url": None,
        "reason_notes": "Active standalone yellow pine sawmill since 1898, but maintains no standalone corporate website, no published email address, and requires operational distinction from retail hardware entity prior to broker outreach.",
    },
]

BATCH_1_CANDIDATES = [{'num': 1, 'brand': 'Battle Lumber Company', 'raw_brand': 'Battle Lumber Company', 'fac_name': 'Wadley Hardwood Sawmill & Multi-Plant Facility', 'address': '11261 Hwy 1 South', 'city': 'Wadley', 'state': 'GA', 'country': 'US', 'comm_cat': 'Lumber & Wood Products', 'specific_prod': 'Hardwood grade lumber, pallet cants, crane mats, railroad crossties, industrial mulch', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'General Sales Desk', 'exact_title': None, 'phone': '(478) 252-5210', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@battlelumberco.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://www.battlelumberco.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'VERIFIED', 'note': 'Verified large-volume hardwood sawmill; has dedicated export personnel and heat-treating certification.', 'sources': ['https://www.battlelumberco.com'], 'sec_sources': ['https://gatrees.org (Georgia Forestry Commission Directory)']}, {'num': 2, 'brand': 'Custom Cut Timber Products', 'raw_brand': 'Custom Cut Timber Products', 'fac_name': 'Forsyth Sawmill & Timber Yard', 'address': '701 West Main Street (Mailing: PO Box 344, Smarr, GA 31086)', 'city': 'Forsyth', 'state': 'GA', 'country': 'US', 'comm_cat': 'Heavy Industrial Timber & Mats', 'specific_prod': 'Crane mats, bridge timbers, cants, rough hardwood lumber, blocking/dunnage', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'Chris Yawn', 'exact_title': 'CEO / Manager', 'phone': '(478) 214-8688', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'custommats@yahoo.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'OPERATIONS', 'website_url': None, 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Dedicated crane mat and heavy cant producer; phone and dedicated mat sales email verified.', 'sources': ['https://gatrees.org/wp-content/uploads/2019/12/GFC-Wood-Using-Industries-Directory.pdf'], 'sec_sources': ['https://forestproductslocator.org']}, {'num': 3, 'brand': 'Lamb Brothers Lumber Company, Inc.', 'raw_brand': 'Lamb Brothers Lumber Company, Inc. (Holding Co: Lamb Lumber Holding Company)', 'fac_name': 'Wrens Hardwood Sawmill', 'address': '102 Industrial Street (Mailing: PO Box 428)', 'city': 'Wrens', 'state': 'GA', 'country': 'US', 'comm_cat': 'Lumber & Pallet Stock', 'specific_prod': 'Hardwood rough lumber, dimension/stud lumber, pallets, crossties, furniture stock, cants, blocking', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'General Office Desk', 'exact_title': None, 'phone': '(706) 547-2519', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'lamblumber@bellsouth.net', 'email_dir': 'GENERAL', 'role_cat': 'GENERAL_FACILITY', 'website_url': None, 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Registered continuous operation since 1974; multi-species hardwood breakdown.', 'sources': ['https://gatrees.org'], 'sec_sources': ['https://forestproductslocator.org']}, {'num': 4, 'brand': 'Shearouse Lumber Company', 'raw_brand': 'Shearouse Lumber Company', 'fac_name': 'Pooler Sawmill & Wood Preservation Facility', 'address': '833 West Highway 80', 'city': 'Pooler', 'state': 'GA', 'country': 'US', 'comm_cat': 'Lumber & Pressure-Treated Wood', 'specific_prod': 'Rough lumber, treated lumber, poles, pilings, tongue-and-groove flooring', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'Main Office Desk', 'exact_title': None, 'phone': '(912) 748-7244', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': None, 'email_dir': 'UNKNOWN', 'role_cat': 'GENERAL_FACILITY', 'website_url': 'http://www.shearouselumber.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Family-owned sawmill and treatment facility operating since 1926 with dry kilns and pressure-treating cylinders. Toll-free line: `(800) 548-9404`.', 'sources': ['http://www.shearouselumber.com'], 'sec_sources': ['https://gatrees.org']}, {'num': 5, 'brand': 'Leslie Forest Products Ltd.', 'raw_brand': 'Leslie Forest Products Ltd.', 'fac_name': 'Delta Remanufacturing Mill & Timber Yard', 'address': '7902 Progress Way', 'city': 'Delta', 'state': 'BC', 'country': 'CA', 'comm_cat': 'Specialty Softwood Lumber', 'specific_prod': 'Western Red Cedar, Hemlock, Douglas Fir, SPF industrial lumber packages, clear lumber', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'James Sangara', 'exact_title': 'Mill Coordinator / Cedar Sales', 'phone': '(604) 952-4537', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'shipping@leslieforest.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'COMMERCIAL_SALES', 'website_url': 'http://www.leslieforest.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': '13-acre remanufacturing operation in Tilbury Industrial Park specializing in just-in-time cross-border program business.', 'sources': ['http://www.leslieforest.com'], 'sec_sources': ['https://realcedar.com', 'https://naturallywood.com']}, {'num': 6, 'brand': 'Andersen Pacific Forest Products Ltd.', 'raw_brand': 'Andersen Pacific Forest Products Ltd. (APFP)', 'fac_name': 'Maple Ridge Specialty Sawmill', 'address': '9730 287th Street', 'city': 'Maple Ridge', 'state': 'BC', 'country': 'CA', 'comm_cat': 'Specialty Construction Timbers', 'specific_prod': 'Vertical-grain Douglas Fir, Hemlock, Western Red & Yellow Cedar, Timber Frame timbers', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'General Sales Desk', 'exact_title': None, 'phone': '(604) 462-7316', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@apfp.bc.ca', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://andersenpacific.ca', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Over 30 years in primary breakdown sawmilling; department sales email newly verified.', 'sources': ['https://andersenpacific.ca'], 'sec_sources': ['https://naturallywood.com']}, {'num': 7, 'brand': 'Mill & Timber Products Ltd. / AP Group', 'raw_brand': 'Mill & Timber Products Ltd. / AP Group', 'fac_name': 'Surrey Mill Operations / Pan-Abode Division (HQ: 95 Schooner St, Coquitlam, BC)', 'address': '12770 116th Avenue', 'city': 'Surrey', 'state': 'BC', 'country': 'CA', 'comm_cat': 'Cedar Timbers & Lumber', 'specific_prod': 'Western Red Cedar clears, decking, fascia, posts, beams, custom-cut timbers', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'Cedar Sales Desk', 'exact_title': None, 'phone': '(604) 580-2781', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'wrcsales@apgroup.ca', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'http://www.millandtimber.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Established 1951; operates as part of Aspen Planers / AP Group. Major North American cross-border exporter.', 'sources': ['http://www.millandtimber.com'], 'sec_sources': ['https://naturallywood.com']}, {'num': 8, 'brand': 'Jordan Forest Products, LLC', 'raw_brand': 'Jordan Forest Products, LLC', 'fac_name': 'Barnesville Curve-Sawing Mill', 'address': '752 Grove Street', 'city': 'Barnesville', 'state': 'GA', 'country': 'US', 'comm_cat': 'Softwood Dimension Lumber', 'specific_prod': 'Southern Yellow Pine dimension lumber, curve-sawn lumber, framing lumber', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'Larry Spillers', 'exact_title': 'Mill Manager / Sales Manager', 'phone': '(770) 358-5931', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'lspillers@jordanforestproducts.com', 'email_dir': 'DIRECT_PERSON', 'role_cat': 'COMMERCIAL_SALES', 'website_url': 'http://www.jordanlumber.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'High-volume curve-sawing sawmill acquired from Weyerhaeuser in 2004; named Mill Manager and direct email verified.', 'sources': ['http://www.jordanlumber.com'], 'sec_sources': ['https://forestproductslocator.org', 'https://usnr.com']}, {'num': 9, 'brand': 'Edwards Wood Products, Inc.', 'raw_brand': 'Edwards Wood Products, Inc.', 'fac_name': 'Marshville Multi-Mill & Pallet Complex', 'address': '2215 Old Lawyers Rd', 'city': 'Marshville', 'state': 'NC', 'country': 'US', 'comm_cat': 'Pallets, Crane Mats & Industrial Lumber', 'specific_prod': 'Industrial hardwood pallets, crane mats, railroad crossties, pipeline skids, grade lumber', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'SAWMILL', 'best_person': 'General Logistics Desk', 'exact_title': None, 'phone': '(704) 624-3270', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': None, 'email_dir': 'UNKNOWN', 'role_cat': 'UNKNOWN', 'website_url': 'https://ewpi.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'UNKNOWN', 'note': 'Large vertically integrated producer operating multiple sawmills and pallet manufacturing plants across NC.', 'sources': ['https://ewpi.com'], 'sec_sources': ['FMCSA SAFER / SCTA 2025 Fleet Safety Awards']}, {'num': 10, 'brand': 'The Universal Steel Company', 'raw_brand': 'The Universal Steel Company (Columbia National Group)', 'fac_name': 'Cleveland Flat-Rolled Processing Center', 'address': '6600 Grant Ave', 'city': 'Cleveland', 'state': 'OH', 'country': 'US', 'comm_cat': 'Flat-Rolled Carbon Steel', 'specific_prod': 'Hot-rolled, cold-rolled, coated steel master coils, slitting, cut-to-length sheets, blanking', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Customer Service Desk', 'exact_title': None, 'phone': '(216) 883-4972', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'info@univsteel.com', 'email_dir': 'GENERAL', 'role_cat': 'UNKNOWN', 'website_url': 'https://www.univsteel.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Operating since 1926 with 200,000 sq ft facility and over 50,000 tons of coil storage; acquired Chatfield Steel in 2021.', 'sources': ['https://www.univsteel.com'], 'sec_sources': ['FMA Directory']}, {'num': 11, 'brand': 'Miami Valley Steel Service, Inc.', 'raw_brand': 'Miami Valley Steel Service, Inc.', 'fac_name': 'Piqua Processing & Distribution Facility', 'address': '201 Fox Drive', 'city': 'Piqua', 'state': 'OH', 'country': 'US', 'comm_cat': 'Flat-Rolled Carbon Steel', 'specific_prod': 'Heavy/light gauge slitting, multi-blanking, cut-to-length sheets, oscillate coils, HR/CR/Galvanized', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Traffic / Shipping Department', 'exact_title': None, 'phone': '(937) 773-7127', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'traffic@miamivalleysteel.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'FREIGHT_LOGISTICS', 'website_url': 'https://www.miamivalleysteel.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'VERIFIED', 'note': 'Appointments mandatory for all pick-up and deliveries via load number and weight; exceptional operational clarity.', 'sources': ['https://www.miamivalleysteel.com/shipping/'], 'sec_sources': ['https://www.miamivalleysteel.com/traffic-application/']}, {'num': 12, 'brand': 'MidWest Materials, Inc.', 'raw_brand': 'MidWest Materials, Inc. (Reliance, Inc.)', 'fac_name': 'Perry Steel Service Center', 'address': '3687 Shepard Road', 'city': 'Perry', 'state': 'OH', 'country': 'US', 'comm_cat': 'Flat-Rolled Carbon Steel', 'specific_prod': 'Hot-rolled, pickled & oiled, cold-rolled, coated steel coils, stretcher-leveled sheets', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'General Sales Desk', 'exact_title': None, 'phone': '(440) 259-5200', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': None, 'email_dir': 'UNKNOWN', 'role_cat': 'UNKNOWN', 'website_url': 'https://midwestmaterials.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'VERIFIED', 'note': 'Acquired by Reliance, Inc. in April 2024; maintains heavy rail and common carrier truck outbound operations.', 'sources': ['https://midwestmaterials.com'], 'sec_sources': ['SEC filings (Reliance', 'Inc. acquisition April 2024)', 'Norfolk Southern Industrial Directory']}, {'num': 13, 'brand': 'Liberty Steel Products, Inc.', 'raw_brand': 'Liberty Steel Products, Inc.', 'fac_name': 'Hubbard Steel Processing Center', 'address': '7193 Hubbard-Masury Road SE', 'city': 'Hubbard', 'state': 'OH', 'country': 'US', 'comm_cat': 'Carbon Flat-Rolled Steel', 'specific_prod': 'Slit coil, cut-to-length sheets, configured blanking, pickling', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Main Switchboard', 'exact_title': None, 'phone': '(330) 534-7998', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': None, 'email_dir': 'UNKNOWN', 'role_cat': 'GENERAL_FACILITY', 'website_url': 'https://libertysteelproducts.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'VERIFIED', 'note': 'Both private fleet and commercial carrier contracts verified via official operational disclosures.', 'sources': ['https://libertysteelproducts.com'], 'sec_sources': ['Company logistics disclosures']}, {'num': 14, 'brand': 'Coil Steel Processing (CSP)', 'raw_brand': 'Coil Steel Processing (CSP)', 'fac_name': 'Toledo Stretcher Leveling & Processing Plant', 'address': '1604 Prosperity Road', 'postal_code': '43612', 'city': 'Toledo', 'state': 'OH', 'country': 'US', 'comm_cat': 'Carbon Flat-Rolled Steel', 'specific_prod': 'Stretcher-leveled cut-to-length steel sheets, floor plate, HR, CR, pickled & oiled coils', 'eq_cat': 'FLATBED', 'eq_status': 'VERIFIED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Shipping & Receiving Department', 'exact_title': None, 'phone': '(419) 269-9700', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@coilsteelprocessing.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'FREIGHT_LOGISTICS', 'website_url': 'https://coilsteelprocessing.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'VERIFIED', 'note': 'Operating facility: 1604 Prosperity Road, Toledo, OH 43612. Explicit published operational rule mandates overhead crane or sheet lifter loading; box trucks and dry vans prohibited; flatbed requirement verified. Note: planned expansion at 5601 Enterprise Blvd targeted for Q4 2026 under development (not current operating plant).', 'sources': ['https://coilsteelprocessing.com/shipping-receiving/'], 'sec_sources': ['https://coilsteelprocessing.com/contact/']}, {'num': 15, 'brand': 'H&D Steel Service Center, Inc.', 'raw_brand': 'H&D Steel Service Center, Inc.', 'fac_name': 'North Royalton Metals Processing Center', 'address': '11900 Royalton Road', 'city': 'North Royalton', 'state': 'OH', 'country': 'US', 'comm_cat': 'Coated Carbon Steel & Non-Ferrous', 'specific_prod': 'Coated carbon coil and sheet, stainless steel, aluminum, red metals, rod, bar, tubing', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Sales Desk', 'exact_title': None, 'phone': '(440) 237-3390', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@hdsteel.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'http://www.hdsteel.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'UNKNOWN', 'note': 'Dedicated fleet and sales desk email confirmed; serves multi-state industrial manufacturing accounts.', 'sources': ['http://www.hdsteel.com'], 'sec_sources': ['Metals Service Center Institute (MSCI) Directory']}, {'num': 16, 'brand': 'Taylor Steel Inc.', 'raw_brand': 'Taylor Steel Inc.', 'fac_name': 'Stoney Creek Flat-Rolled Service Center', 'address': '477 Arvin Avenue', 'city': 'Stoney Creek', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Flat-Rolled Carbon Steel', 'specific_prod': 'Slit coil, blanking, cut-to-length sheets, pickling, toll processing (automotive and industrial grades)', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'General Sales Desk', 'exact_title': None, 'phone': '(905) 662-4925', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@taylorsteel.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://taylorsteel.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'VERIFIED', 'note': 'Major Canadian coil processor operating over 30 company trucks and partnering with outside commercial carriers for US/Canada freight.', 'sources': ['https://taylorsteel.com'], 'sec_sources': ['Hamilton Chamber of Commerce Directory']}, {'num': 17, 'brand': 'Janco Steel Ltd.', 'raw_brand': 'Janco Steel Ltd.', 'fac_name': 'Stoney Creek Coil Processing Facility', 'address': '925 Arvin Avenue', 'city': 'Stoney Creek', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Flat-Rolled Carbon Steel', 'specific_prod': 'Slitting, cut-to-length, stretcher leveling, sheet and plate, master coils', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Commercial Sales Desk', 'exact_title': None, 'phone': '(905) 643-3535', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@jancosteel.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://jancosteel.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'AFFILIATED_CARRIER_ENTITY', 'commercial_carrier': 'UNKNOWN', 'note': 'Family-owned processor established 1988; operates dedicated fleet under affiliated Janco Trucking entity.', 'sources': ['https://jancosteel.com'], 'sec_sources': ['FMCSA SAFER / BrokerSnapshot records for Janco Trucking and Logistics Inc.']}, {'num': 18, 'brand': 'Imperial Metal Services', 'raw_brand': 'Imperial Metal Services', 'fac_name': 'Etobicoke Slitting & Sheeting Facility', 'address': '100 Guided Court', 'city': 'Etobicoke', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Flat-Rolled Carbon & Coated Steel', 'specific_prod': 'Master coils, slit coils, leveled sheets, blanking', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Customer Care Desk', 'exact_title': None, 'phone': '(416) 744-9988', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'info@imperialms.ca', 'email_dir': 'GENERAL', 'role_cat': 'UNKNOWN', 'website_url': 'https://www.imperialms.ca', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Head office and main processing plant in Etobicoke with additional branches in QC and NB.', 'sources': ['https://www.imperialms.ca'], 'sec_sources': ['Canadian Steel Producers Directory']}, {'num': 19, 'brand': 'AmeriSteel', 'raw_brand': 'AmeriSteel', 'fac_name': 'Warren Fabrication & Coating Division (Processing: 33900 Doreka, Fraser, MI)', 'address': '25770 Groesbeck Highway', 'city': 'Warren', 'state': 'MI', 'country': 'US', 'comm_cat': 'Steel Processing & Fabrication', 'specific_prod': 'Processed sheet and plate, laser cutting blanks, formed shapes, welded fabrications', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Commercial Sales Desk', 'exact_title': None, 'phone': '(586) 585-5250', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@ameristeel.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://www.ameristeel.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Serves defense, automotive, and industrial accounts; department sales email newly verified.', 'sources': ['https://www.ameristeel.com'], 'sec_sources': ['Michigan Manufacturers Directory']}, {'num': 20, 'brand': 'Majestic Steel USA', 'raw_brand': 'Majestic Steel USA', 'fac_name': 'Bedford Heights Flagship Service Center & Distribution Hub', 'address': '26100 Richmond Road', 'city': 'Bedford Heights', 'state': 'OH', 'country': 'US', 'comm_cat': 'Prime Carbon Flat-Rolled Steel', 'specific_prod': 'Galvanized, galvalume, aluminized, cold-rolled master coils, slit coils, cut-to-length sheets', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Transportation Scheduling / Sales Desk', 'exact_title': None, 'phone': '(440) 786-2666', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'press@majesticsteel.com', 'email_dir': 'GENERAL', 'role_cat': 'UNKNOWN', 'website_url': 'https://www.majesticsteel.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'AFFILIATED_CARRIER_ENTITY', 'commercial_carrier': 'VERIFIED', 'note': 'High-volume hub handling up to 180 trucks daily; dedicated subsidiary fleet and external carrier reliance confirmed.', 'sources': ['https://www.majesticsteel.com'], 'sec_sources': ['PR Newswire (Mercury Transport acquisition July 2022)', 'Forbes Supply Chain Review']}, {'num': 21, 'brand': 'Heidtman Steel Products, Inc.', 'raw_brand': 'Heidtman Steel Products, Inc.', 'fac_name': 'Toledo Headquarters & Processing Facility', 'address': '2401 Front St.', 'city': 'Toledo', 'state': 'OH', 'country': 'US', 'comm_cat': 'Flat-Rolled Carbon Steel', 'specific_prod': 'Hot-rolled pickled & oiled, high-strength cold-rolled, coated steel, slitting, leveling', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'STEEL_SERVICE_CENTER', 'best_person': 'Sales Desk', 'exact_title': None, 'phone': '(419) 691-4646', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'Hsp.sales@heidtman.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://heidtman.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'VERIFIED', 'note': 'Major supplier to automotive stampers; active carrier/3PL management verified; sales email newly discovered.', 'sources': ['https://heidtman.com'], 'sec_sources': ['MSCI Directory', 'JobTarget Logistics Requisitions']}, {'num': 22, 'brand': 'Mack Industries, Inc.', 'raw_brand': 'Mack Industries, Inc.', 'fac_name': 'Valley City Production Plant (HQ: 1321 Industrial Pkwy N, Brunswick, OH)', 'address': '1900 Station Road', 'city': 'Valley City', 'state': 'OH', 'country': 'US', 'comm_cat': 'Precast & Prestressed Concrete', 'specific_prod': 'Utility vaults, drainage manholes, box culverts, bridge beams, retaining walls', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'General Information Desk', 'exact_title': None, 'phone': '(330) 460-7005', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'info@mackconcrete.com', 'email_dir': 'GENERAL', 'role_cat': 'UNKNOWN', 'website_url': 'http://www.mackconcrete.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'UNKNOWN', 'note': 'Over 75 years in concrete manufacturing; operates across OH, MI, PA, and IN.', 'sources': ['http://www.mackconcrete.com'], 'sec_sources': ['Ohio Concrete Association Directory']}, {'num': 23, 'brand': 'Lindsay Precast', 'raw_brand': 'Lindsay Precast', 'fac_name': 'Canal Fulton Headquarters & Precast Plant', 'address': '6845 Erie Avenue NW', 'city': 'Canal Fulton', 'state': 'OH', 'country': 'US', 'comm_cat': 'Precast Utility & Infrastructure', 'specific_prod': 'Utility vaults, solar foundations, security barriers, box culverts, precast pump stations', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'Corporate Office Desk', 'exact_title': None, 'phone': '(330) 854-6282', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'info@lindsayprecast.com', 'email_dir': 'GENERAL', 'role_cat': 'GENERAL_FACILITY', 'website_url': 'https://lindsayprecast.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'AFFILIATED_CARRIER_ENTITY', 'commercial_carrier': 'UNKNOWN', 'note': 'Manufacturer with nationwide multi-plant network; corporate email newly verified.', 'sources': ['https://lindsayprecast.com'], 'sec_sources': ['FMCSA SAFER (USDOT 384421)']}, {'num': 24, 'brand': 'Tindall Corporation', 'raw_brand': 'Tindall Corporation', 'fac_name': 'Spartanburg Precast / Prestressed Facility', 'address': '2877 Fairforest Clevedale Rd', 'city': 'Spartanburg', 'state': 'SC', 'country': 'US', 'comm_cat': 'Structural Precast & Prestressed Concrete', 'specific_prod': 'Precast parking garage members, bridge girders, architectural wall panels, utility vaults', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'General Switchboard Desk', 'exact_title': None, 'phone': '(864) 576-3230', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': None, 'email_dir': 'UNKNOWN', 'role_cat': 'GENERAL_FACILITY', 'website_url': 'https://tindallcorp.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'AFFILIATED_CARRIER_ENTITY', 'commercial_carrier': 'UNKNOWN', 'note': 'Massive structural precast producer with verified proprietary haul and erect fleet.', 'sources': ['https://tindallcorp.com'], 'sec_sources': ['FMCSA SAFER (USDOT 359960)']}, {'num': 25, 'brand': 'High Concrete Group LLC', 'raw_brand': 'High Concrete Group LLC (High Industries Inc.)', 'fac_name': 'Denver Precast Plant & Operations', 'address': '125 Denver Road', 'city': 'Denver', 'state': 'PA', 'country': 'US', 'comm_cat': 'Architectural & Structural Precast', 'specific_prod': 'Architectural precast facades, hollowcore slabs, precast parking structures, stadium risers', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'Jamie Sweigart', 'exact_title': 'VP of Sales', 'phone': '(717) 824-1542', 'phone_dir': 'DIRECT_PERSON', 'email': 'jsweigart@high.net', 'email_dir': 'DIRECT_PERSON', 'role_cat': 'COMMERCIAL_SALES', 'website_url': 'https://www.highconcrete.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'High data density; three named sales leaders with verified direct phone numbers and emails discovered.', 'sources': ['https://www.highconcrete.com'], 'sec_sources': ['High Industries Directory']}, {'num': 26, 'brand': 'Concast Pipe Inc.', 'raw_brand': 'Concast Pipe Inc. (Con-Cast Pipe)', 'fac_name': 'Puslinch Production Facility & Head Office', 'address': '299 Brock Road South', 'city': 'Puslinch', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Precast Concrete Infrastructure', 'specific_prod': 'Reinforced concrete pipe, maintenance holes, box culverts, catch basins, utility chambers', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'Sales Desk', 'exact_title': None, 'phone': '(519) 763-8655', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@concastpipe.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://www.concastpipe.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Municipal postal address reconciled to Puslinch, ON (historically described as Guelph); verified department email.', 'sources': ['https://www.concastpipe.com'], 'sec_sources': ['Ontario Concrete Pipe Association (OCPA) Directory']}, {'num': 27, 'brand': 'Coreslab Structures (ONT) Inc.', 'raw_brand': 'Coreslab Structures (ONT) Inc.', 'fac_name': 'Dundas Precast Facility', 'address': '205 Coreslab Drive', 'city': 'Dundas', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Prestressed & Precast Concrete', 'specific_prod': 'Hollowcore floor/roof slabs, precast columns, structural beams, bridge components', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'Jordan Davidson', 'exact_title': 'Sales Manager', 'phone': '(905) 689-3993', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'SalesOntario@coreslab.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'COMMERCIAL_SALES', 'website_url': 'https://coreslab.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Three verified regional commercial sales contacts and direct emails discovered for Ontario operations.', 'sources': ['https://coreslab.com'], 'sec_sources': ['Canadian Precast Concrete Institute (CPCI)']}, {'num': 28, 'brand': 'Norwalk Concrete Industries', 'raw_brand': 'Norwalk Concrete Industries (NCI Precast)', 'fac_name': 'Norwalk Production Plant', 'address': '80 Commerce Drive', 'city': 'Norwalk', 'state': 'OH', 'country': 'US', 'comm_cat': 'Precast Concrete Infrastructure', 'specific_prod': 'Highway barrier walls, utility vaults, manholes, storm water management structures, lift stations', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'General Office Desk', 'exact_title': None, 'phone': '(419) 668-8167', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'info@nciprecast.com', 'email_dir': 'GENERAL', 'role_cat': 'GENERAL_FACILITY', 'website_url': 'https://nciprecast.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'UNKNOWN', 'note': 'Active motor carrier with in-house heavy equipment maintenance; general email and fleet newly verified.', 'sources': ['https://nciprecast.com'], 'sec_sources': ['FMCSA SAFER (USDOT 362593)']}, {'num': 29, 'brand': 'E.C. Babbert, Inc.', 'raw_brand': 'E.C. Babbert, Inc.', 'fac_name': 'Canal Winchester Precast Plant', 'address': '7415 Diley Rd. (Mailing: PO Box 203)', 'city': 'Canal Winchester', 'state': 'OH', 'country': 'US', 'comm_cat': 'Precast Concrete Products', 'specific_prod': 'Sanitary structures, storm sewer structures, grease interceptors, transformer pads, pull boxes', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'Sales Desk', 'exact_title': None, 'phone': '(614) 837-8444', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@ecbabbert.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://www.ecbabbert.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'UNKNOWN', 'note': 'Departmental sales and service emails discovered; private delivery fleet verified via FMCSA.', 'sources': ['https://www.ecbabbert.com'], 'sec_sources': ['FMCSA SAFER Database']}, {'num': 30, 'brand': 'Precon Precast Limited', 'raw_brand': 'Precon Precast Limited (OSCO Construction Group)', 'fac_name': 'Woodstock Precast Manufacturing Plant (Admin: Suite 210, 7025 Langer Drive, Mississauga, ON)', 'address': '1100 Dundas Street', 'city': 'Woodstock', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Engineered Precast Concrete', 'specific_prod': 'Precast bridge girders, architectural wall panels, structural infrastructure elements', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'PRECAST_PLANT', 'best_person': 'Sales & Project Inquiries Desk', 'exact_title': None, 'phone': '(519) 537-6288', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@pre-con.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://pre-con.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Address reconciled from historical 1977 Brampton filing to active Woodstock manufacturing plant and Mississauga administrative office; department sales email newly discovered.', 'sources': ['https://pre-con.com'], 'sec_sources': ['OSCO Construction Group Corporate Directory']}, {'num': 31, 'brand': 'Cavalier Tool & Manufacturing Ltd.', 'raw_brand': 'Cavalier Tool & Manufacturing Ltd.', 'fac_name': 'Windsor Tooling Plant', 'address': '3450 Wheelton Dr.', 'city': 'Windsor', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Precision Tooling & Industrial Molds', 'specific_prod': 'Medium-to-large plastic injection molds for automotive, commercial, and recreational vehicle sectors', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'Engineering / Commercial Sales Desk', 'exact_title': None, 'phone': '(519) 944-2144', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'molds@cavaliertool.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://www.cavaliertool.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'High-precision mold manufacturer shipping heavy tooling globally; department technical/commercial email verified.', 'sources': ['https://www.cavaliertool.com'], 'sec_sources': ['Canadian Plastics Industry Directory']}, {'num': 32, 'brand': 'Crest Mold Technology Inc.', 'raw_brand': 'Crest Mold Technology Inc.', 'fac_name': 'Oldcastle Tooling Facility', 'address': '2055 Blackacre Drive', 'city': 'Oldcastle', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Precision Injection Molds', 'specific_prod': 'High-precision plastic injection molds, tooling, prototype tooling', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'Commercial Sales Desk', 'exact_title': None, 'phone': '(519) 737-1546', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@crestmold.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'https://crestmold.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Department sales email newly discovered; active automotive mold manufacturer in Windsor-Essex corridor.', 'sources': ['https://crestmold.com'], 'sec_sources': ['Windsor-Essex Economic Development Directory']}, {'num': 33, 'brand': 'Integrity Tool & Mold, Inc.', 'raw_brand': 'Integrity Tool & Mold, Inc.', 'fac_name': 'Oldcastle Headquarters & Advanced Manufacturing Complex', 'address': "5015 O'Neil Drive", 'city': 'Oldcastle', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Automotive Plastic Injection Molds', 'specific_prod': 'Injection molds, multi-shot rotary tools, compression molds up to approximately 90,000 lbs', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'Logistics & Customs Department Desk', 'exact_title': None, 'phone': '(519) 737-2650', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': None, 'email_dir': 'UNKNOWN', 'role_cat': 'UNKNOWN', 'website_url': 'http://www.teamintegrity.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Verified dedicated logistics and customs department; handling capability supports molds up to ~90,000 lbs (operational capability note; equipment remains inferred).', 'sources': ['http://www.teamintegrity.com'], 'sec_sources': ['Automotive Tooling Industry Profiles']}, {'num': 34, 'brand': 'Omega Tool Corp.', 'raw_brand': 'Omega Tool Corp.', 'fac_name': 'Oldcastle Global Headquarters & Tooling Complex', 'address': '2045 Solar Crescent', 'city': 'Oldcastle', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Large-Scale Plastic Tooling', 'specific_prod': 'Large injection molds (frequently exceeding 50 tons) for automotive fascia, heavy truck, and consumer products', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'General Information Desk', 'exact_title': None, 'phone': '(519) 737-1201', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'info@omegatoolcorp.com', 'email_dir': 'GENERAL', 'role_cat': 'UNKNOWN', 'website_url': 'https://omegatoolcorp.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Global leader in 50+ ton injection tooling; corporate email newly verified.', 'sources': ['https://omegatoolcorp.com'], 'sec_sources': ['Canadian Tooling & Machining Association (CTMA)']}, {'num': 35, 'brand': 'Cascade Engineering', 'raw_brand': 'Cascade Engineering', 'fac_name': 'Grand Rapids World Headquarters & Manufacturing Complex', 'address': '5050 33rd Street SE', 'city': 'Grand Rapids', 'state': 'MI', 'country': 'US', 'comm_cat': 'Large-Part Plastic Injection Molding', 'specific_prod': 'Industrial roll-out waste containers, automotive exterior components, material handling pallets', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'Danielle Flores', 'exact_title': 'Director of Supply Chain and Purchasing', 'phone': '574-304-0625', 'phone_dir': 'DIRECT_PERSON', 'email': 'danielle.flores@cascadeng.com', 'email_dir': 'DIRECT_PERSON', 'role_cat': 'FREIGHT_LOGISTICS', 'website_url': 'https://cascadeng.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'VERIFIED', 'note': 'Direct supply chain leadership contact and formal freight routing protocols verified.', 'sources': ['https://cascadeng.com'], 'sec_sources': ['Cascade Engineering Supplier Information Portal & Routing Guidelines']}, {'num': 36, 'brand': 'PTI Engineered Plastics', 'raw_brand': 'PTI Engineered Plastics', 'fac_name': 'Macomb Advanced Molding Facility', 'address': '50900 Corporate Drive', 'city': 'Macomb', 'state': 'MI', 'country': 'US', 'comm_cat': 'Precision Engineered Plastics', 'specific_prod': 'Injection-molded medical device components, automotive assemblies, aerospace plastic housings', 'eq_cat': 'DRY_VAN', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'General Information Desk', 'exact_title': None, 'phone': '(586) 263-5100', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'info@teampti.com', 'email_dir': 'GENERAL', 'role_cat': 'UNKNOWN', 'website_url': 'https://teampti.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Medical and automotive injection molding facility; general inquiries email newly discovered.', 'sources': ['https://teampti.com'], 'sec_sources': ['Plastics Industry Association Directory']}, {'num': 37, 'brand': 'Bemis Manufacturing Company', 'raw_brand': 'Bemis Manufacturing Company', 'fac_name': 'Sheboygan Falls Dedicated Shipping & Receiving Center (HQ: 300 Mill St)', 'address': 'W2940 Old County Road PP', 'city': 'Sheboygan Falls', 'state': 'WI', 'country': 'US', 'comm_cat': 'Custom & Proprietary Plastic Products', 'specific_prod': 'Large custom injection-molded products, proprietary consumer/commercial products, healthcare products', 'eq_cat': 'DRY_VAN', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'Corporate Inquiries Desk', 'exact_title': None, 'phone': '(920) 467-4621', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'corp@BemisMfg.com', 'email_dir': 'GENERAL', 'role_cat': 'UNKNOWN', 'website_url': 'https://bemismfg.com', 'private_fleet_present': 'VERIFIED_PRESENT', 'fleet_rel_type': 'IN_HOUSE_OWNED', 'commercial_carrier': 'VERIFIED', 'note': 'Dedicated shipping/receiving address verified at W2940 Old County Rd PP; both private fleet and commercial TMS routing verified.', 'sources': ['https://bemismfg.com'], 'sec_sources': ['FMCSA SAFER Database', '3G TMS Case Studies']}, {'num': 38, 'brand': 'Jones Plastic & Engineering Company, LLC', 'raw_brand': 'Jones Plastic & Engineering Company, LLC', 'fac_name': 'Jeffersontown Headquarters & Molding Plant', 'address': '2410 Plantside Dr.', 'city': 'Jeffersontown', 'state': 'KY', 'country': 'US', 'comm_cat': 'High-Volume Injection Molding', 'specific_prod': 'Injection-molded appliance components, automotive interior/exterior assemblies, medical devices', 'eq_cat': 'DRY_VAN', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'Commercial Sales Desk', 'exact_title': None, 'phone': '(502) 491-3785', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'sales@jonesplastic.com', 'email_dir': 'DEPARTMENT', 'role_cat': 'UNKNOWN', 'website_url': 'http://www.jonesplastic.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'UNKNOWN', 'commercial_carrier': 'UNKNOWN', 'note': 'Multi-plant injection molder serving major appliance OEMs; sales department email newly discovered.', 'sources': ['http://www.jonesplastic.com'], 'sec_sources': ['Kentucky Cabinet for Economic Development']}, {'num': 39, 'brand': 'SyBridge Technologies', 'raw_brand': 'SyBridge Technologies (SyBridge Technologies Canada Inc.)', 'fac_name': 'Lakeshore Advanced Tooling Center', 'address': '465 Jutras Drive South', 'city': 'Lakeshore', 'state': 'ON', 'country': 'CA', 'comm_cat': 'Advanced Tooling & Injection Mold Manufacturing', 'specific_prod': 'High-precision plastic injection molds, tooling, life sciences and automotive tooling', 'eq_cat': 'FLATBED', 'eq_status': 'INFERRED', 'fac_type': 'TOOLING_PLANT', 'best_person': 'Ryan J. Hurley', 'exact_title': 'Logistics Manager', 'phone': '(519) 727-9949', 'phone_dir': 'GENERAL_SWITCHBOARD', 'email': 'info@sybridge.com', 'email_dir': 'GENERAL', 'role_cat': 'FREIGHT_LOGISTICS', 'website_url': 'https://sybridge.com', 'private_fleet_present': 'UNKNOWN', 'fleet_rel_type': 'AFFILIATED_CARRIER_ENTITY', 'commercial_carrier': 'UNKNOWN', 'note': 'Named Logistics Manager and commercial motor vehicle operating authority verified via DOT filings.', 'sources': ['https://sybridge.com'], 'sec_sources': ['USDOT / FMCSA SAFER (DOT 1229966)']}]

def classify_source(url: Optional[str], brand: str, website_url: Optional[str]) -> tuple[str, bool, str]:
    """
    Classifies evidence source based on audited URL and provenance.
    Strictly adheres to schema source_type enum:
    'COMPANY_WEBSITE', 'GOVERNMENT_REGISTRY', 'JOB_POSTING', 'INDUSTRY_DIRECTORY', 'PHONE_OUTREACH', 'EMAIL_CORRESPONDENCE'
    """
    if not url:
        return "INDUSTRY_DIRECTORY", False, f"{brand} Audited Reference"

    url_lower = url.lower()

    # Government / Regulatory registries (FMCSA, USDOT, State Forestry)
    if any(k in url_lower for k in ["gatrees.org", "fmcsa", "dot.gov", "usdot", "safer"]):
        if "gatrees.org" in url_lower:
            return "GOVERNMENT_REGISTRY", False, "Georgia Forestry Commission Directory"
        return "GOVERNMENT_REGISTRY", True, "FMCSA SAFER Licensing & Insurance Registry"

    # Official company website
    if website_url:
        domain = re.sub(r"^https?://(www\.)?", "", website_url.lower()).split("/")[0]
        if domain and domain in url_lower:
            return "COMPANY_WEBSITE", True, f"{brand} Official Website"

    # Industry trade associations & directories
    if any(k in url_lower for k in [
        "forestproductslocator", "realcedar", "naturallywood", "msci", "fma",
        "cpci", "ocpa", "ctma", "plastics", "chamber", "usnr", "jobtarget", "forbes", "prnewswire"
    ]):
        return "INDUSTRY_DIRECTORY", False, f"{brand} Industry Directory Profile"

    if url_lower.startswith("http"):
        return "COMPANY_WEBSITE", True, f"{brand} Official Website"

    return "INDUSTRY_DIRECTORY", False, f"{brand} Reference"


def import_batch1(db_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """
    Idempotently imports the 39 approved Batch #1 Discovery Pool facilities
    and registers the 3 deferred candidates in discovery_intake_audit.
    """
    init_db(db_path)

    with get_db_connection(db_path) as conn:
        # 1. Register the 3 deferred candidates idempotently in discovery_intake_audit
        deferred_registered = 0
        for d in DEFERRED_CANDIDATES:
            fp = compute_intake_fingerprint(d["company_name"], d["address"], d["city"], d["state_prov"], d["country"])
            cur = conn.execute("SELECT id FROM discovery_intake_audit WHERE intake_fingerprint = ?", (fp,))
            if not cur.fetchone():
                conn.execute(
                    """
                    INSERT INTO discovery_intake_audit (
                        batch_name, candidate_company_name, candidate_facility_name,
                        city, state_prov, country, intake_fingerprint, intake_status,
                        target_facility_id, website_url, facility_address, batch_reference,
                        reason_or_notes, reason_notes, reviewed_at, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'DEFERRED_FOR_RESEARCH', NULL, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        BATCH_NAME, d["company_name"], d["facility_name"],
                        d["city"], d["state_prov"], d["country"], fp,
                        d["website_url"], d["address"], BATCH_NAME,
                        d["reason_notes"], d["reason_notes"], OBSERVED_DATE, OBSERVED_DATE
                    )
                )
                deferred_registered += 1

        # 2. Process the 39 approved Batch #1 candidates
        inserted_count = 0
        skipped_count = 0

        for c in BATCH_1_CANDIDATES:
            fp = compute_intake_fingerprint(c["brand"], c["address"], c["city"], c["state"], c["country"])
            
            # Check idempotence
            cur = conn.execute(
                "SELECT target_facility_id FROM discovery_intake_audit WHERE intake_fingerprint = ? AND intake_status = 'APPROVED_FOR_IMPORT'",
                (fp,)
            )
            existing = cur.fetchone()
            if existing and existing["target_facility_id"]:
                skipped_count += 1
                continue

            # A. Company
            cur = conn.execute("SELECT id FROM companies WHERE operating_brand = ?", (c["brand"],))
            comp_row = cur.fetchone()
            if comp_row:
                comp_id = comp_row["id"]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO companies (operating_brand, corporate_address, website_url, notes)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        c["brand"],
                        f"{c['address']}, {c['city']}, {c['state']}" + (f" {c['postal_code']}" if c.get("postal_code") else ""),
                        c["website_url"],
                        c["note"]
                    )
                )
                comp_id = cur.lastrowid

                # Company evidence source & claim
                src_url = c["website_url"] or (c["sources"][0] if c["sources"] else None)
                c_src_type, c_is_primary, c_title = classify_source(src_url, c["brand"], c["website_url"])
                c_src = record_evidence_source(
                    conn=conn,
                    source_type=c_src_type,
                    source_title_publisher=c_title,
                    source_url=src_url,
                    is_primary_source=c_is_primary,
                    source_published_at=None,
                    event_at=None,
                    observed_at=OBSERVED_DATE,
                    notes=f"Audited corporate identity from {BATCH_NAME}.",
                )
                c_claim = record_claim(
                    conn=conn,
                    claim_field="operating_brand",
                    claimed_value=c["brand"],
                    verification_status="VERIFIED",
                    is_current_accepted=True,
                    company_id=comp_id,
                )
                link_claim_evidence(conn, c_claim, c_src, "SUPPORTS")

            # B. Facility
            cur = conn.execute(
                """
                INSERT INTO facilities (
                    company_id, facility_name, facility_type, physical_address,
                    city, state_prov, postal_code, country,
                    private_fleet_present, vehicle_asset_ownership,
                    fleet_relationship_type, commercial_carrier_use,
                    broker_friendly_status, freight_procurement_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNKNOWN', ?, ?, 'UNKNOWN', 'FACILITY_LEVEL')
                """,
                (
                    comp_id,
                    c["fac_name"],
                    c["fac_type"],
                    c["address"],
                    c["city"],
                    c["state"],
                    c.get("postal_code"),
                    c["country"],
                    c["private_fleet_present"],
                    c["fleet_rel_type"],
                    c["commercial_carrier"],
                )
            )
            fac_id = cur.lastrowid

            # Facility Evidence & Claim
            f_src_url = c["sources"][0] if c["sources"] else c["website_url"]
            f_src_type, f_is_primary, f_title = classify_source(f_src_url, c["brand"], c["website_url"])
            f_src = record_evidence_source(
                conn=conn,
                source_type=f_src_type,
                source_title_publisher=f"{c['fac_name']} Verification Record ({f_title})",
                source_url=f_src_url,
                is_primary_source=f_is_primary,
                source_published_at=None,
                event_at=None,
                observed_at=OBSERVED_DATE,
                notes=c["note"],
            )
            addr_claim_val = f"{c['address']}, {c['city']}, {c['state']}"
            if c.get("postal_code"):
                addr_claim_val += f" {c['postal_code']}"
            addr_claim_val += f", {c['country']}"

            f_claim = record_claim(
                conn=conn,
                claim_field="physical_address",
                claimed_value=addr_claim_val,
                verification_status="VERIFIED",
                is_current_accepted=True,
                facility_id=fac_id,
            )
            link_claim_evidence(conn, f_claim, f_src, "SUPPORTS")

            # Fleet presence claim
            f_fleet_claim = record_claim(
                conn=conn,
                claim_field="private_fleet_present",
                claimed_value=c["private_fleet_present"],
                verification_status="VERIFIED" if c["private_fleet_present"] == "VERIFIED_PRESENT" else "UNKNOWN",
                is_current_accepted=True,
                claim_notes=f"Fleet presence: {c['private_fleet_present']}.",
                facility_id=fac_id,
            )
            link_claim_evidence(conn, f_fleet_claim, f_src, "SUPPORTS" if c["private_fleet_present"] == "VERIFIED_PRESENT" else "CONTEXT")

            # Materialized non-UNKNOWN fleet_relationship_type claim
            if c["fleet_rel_type"] in ("IN_HOUSE_OWNED", "AFFILIATED_CARRIER_ENTITY"):
                fleet_src = f_src
                if c.get("sec_sources") and any("SAFER" in str(s) or "USDOT" in str(s) or "DOT" in str(s) for s in c["sec_sources"]):
                    sec_title = [s for s in c["sec_sources"] if "SAFER" in str(s) or "USDOT" in str(s) or "DOT" in str(s)][0]
                    fleet_src = record_evidence_source(
                        conn=conn,
                        source_type="GOVERNMENT_REGISTRY",
                        source_title_publisher=str(sec_title),
                        source_url=None,
                        is_primary_source=True,
                        source_published_at=None,
                        event_at=None,
                        observed_at=OBSERVED_DATE,
                        notes=f"Audited motor carrier registration for {c['brand']}.",
                    )
                rel_claim = record_claim(
                    conn=conn,
                    claim_field="fleet_relationship_type",
                    claimed_value=c["fleet_rel_type"],
                    verification_status="VERIFIED",
                    is_current_accepted=True,
                    claim_notes=f"Fleet relationship: {c['fleet_rel_type']}.",
                    facility_id=fac_id,
                )
                link_claim_evidence(conn, rel_claim, fleet_src, "SUPPORTS")

            # Materialized non-UNKNOWN commercial_carrier_use claim
            if c["commercial_carrier"] == "VERIFIED":
                carrier_claim = record_claim(
                    conn=conn,
                    claim_field="commercial_carrier_use",
                    claimed_value="VERIFIED",
                    verification_status="VERIFIED",
                    is_current_accepted=True,
                    claim_notes=f"Commercial carrier use verified for {c['brand']}.",
                    facility_id=fac_id,
                )
                link_claim_evidence(conn, carrier_claim, f_src, "SUPPORTS")

            # C. Facility Commodities
            trailer_specs = None
            securement_notes = None
            if c["num"] == 14:  # Coil Steel Processing (CSP) explicit audited requirements
                trailer_specs = "Flatbeds only; overhead crane or sheet lifter loading; dry vans/box trucks cannot be loaded."
                securement_notes = None

            cur = conn.execute(
                """
                INSERT INTO facility_commodities (
                    facility_id, commodity_category, specific_products,
                    equipment_category, equipment_usage_status,
                    trailer_specs_notes, securement_tarp_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fac_id,
                    c["comm_cat"],
                    c["specific_prod"],
                    c["eq_cat"],
                    c["eq_status"],
                    trailer_specs,
                    securement_notes,
                )
            )
            comm_id = cur.lastrowid
            comm_claim = record_claim(
                conn=conn,
                claim_field="equipment_category",
                claimed_value=c["eq_cat"],
                verification_status=c["eq_status"],
                is_current_accepted=True,
                claim_notes=f"Equipment category {c['eq_cat']} ({c['eq_status']}). Operational fit from {c['comm_cat']}.",
                facility_commodity_id=comm_id,
            )
            link_claim_evidence(conn, comm_claim, f_src, "SUPPORTS" if c["eq_status"] == "VERIFIED" else "CONTEXT")

            # D. Contacts
            person_name = c["best_person"]
            exact_title = c["exact_title"]
            dept_name = None

            if person_name and any(k in person_name.lower() for k in ["department", "desk", "office", "dispatch"]):
                contact_identity = "DEPARTMENT"
                dept_name = person_name
                person_name = None
            elif person_name and any(k in person_name.lower() for k in ["switchboard", "reception"]):
                contact_identity = "GENERAL_FACILITY"
                dept_name = person_name
                person_name = None
            elif person_name:
                contact_identity = "NAMED_PERSON"
            else:
                contact_identity = "GENERAL_FACILITY"

            cur = conn.execute(
                """
                INSERT INTO contacts (
                    facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_directness, email_address, email_directness,
                    role_category, outbound_shipping_procurement_relevance,
                    broker_procurement_relevance, is_primary_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNKNOWN', 'UNKNOWN', 1)
                """,
                (
                    fac_id,
                    contact_identity,
                    person_name,
                    exact_title,
                    dept_name,
                    c["phone"],
                    c["phone_dir"],
                    c["email"],
                    c["email_dir"],
                    c["role_cat"],
                )
            )
            cont_id = cur.lastrowid
            cont_claim = record_claim(
                conn=conn,
                claim_field="phone_directness",
                claimed_value=c["phone_dir"],
                verification_status="VERIFIED" if c["phone_dir"] != "UNKNOWN" else "UNKNOWN",
                is_current_accepted=True,
                claim_notes=f"Published contact route: {c['phone']} ({c['phone_dir']}).",
                contact_id=cont_id,
            )
            link_claim_evidence(conn, cont_claim, f_src, "SUPPORTS")

            # Secondary contacts for special multi-contact candidates
            # Coreslab secondary contacts
            if c["num"] == 27:
                conn.execute(
                    """
                    INSERT INTO contacts (
                        facility_id, contact_identity, person_name, exact_published_title,
                        department, phone_number, phone_directness, email_address, email_directness,
                        role_category, outbound_shipping_procurement_relevance,
                        broker_procurement_relevance, is_primary_contact
                    ) VALUES
                    (?, 'NAMED_PERSON', 'Jacob Cammisoli', 'Sales Consultant GTA', 'Sales', '(905) 689-3993', 'GENERAL_SWITCHBOARD', 'jcammisoli@coreslab.com', 'DIRECT_PERSON', 'COMMERCIAL_SALES', 'UNKNOWN', 'UNKNOWN', 0),
                    (?, 'NAMED_PERSON', 'Tom Beasley', 'Sales Consultant Niagara', 'Sales', '(905) 689-3993', 'GENERAL_SWITCHBOARD', 'tbeasley@coreslab.com', 'DIRECT_PERSON', 'COMMERCIAL_SALES', 'UNKNOWN', 'UNKNOWN', 0),
                    (?, 'DEPARTMENT', NULL, 'Sales Ontario Desk', 'Sales', '(905) 689-3993', 'GENERAL_SWITCHBOARD', 'SalesOntario@coreslab.com', 'DEPARTMENT', 'COMMERCIAL_SALES', 'UNKNOWN', 'UNKNOWN', 0)
                    """,
                    (fac_id, fac_id, fac_id)
                )

            # High Concrete secondary contacts
            if c["num"] == 25:
                conn.execute(
                    """
                    INSERT INTO contacts (
                        facility_id, contact_identity, person_name, exact_published_title,
                        department, phone_number, phone_directness, email_address, email_directness,
                        role_category, outbound_shipping_procurement_relevance,
                        broker_procurement_relevance, is_primary_contact
                    ) VALUES
                    (?, 'NAMED_PERSON', 'Alexandra "Ace" Clayton', 'Business Development', 'Sales', '(717) 538-8078', 'DIRECT_PERSON', 'aclayton@high.net', 'DIRECT_PERSON', 'COMMERCIAL_SALES', 'UNKNOWN', 'UNKNOWN', 0),
                    (?, 'NAMED_PERSON', 'Eric Rowits', 'Sales Representative', 'Sales', '(717) 336-9300', 'GENERAL_SWITCHBOARD', 'erowits@high.net', 'DIRECT_PERSON', 'COMMERCIAL_SALES', 'UNKNOWN', 'UNKNOWN', 0),
                    (?, 'DEPARTMENT', NULL, 'Inquiry Desk', 'Sales', '(717) 336-9300', 'GENERAL_SWITCHBOARD', 'concrete.answers@high.net', 'DEPARTMENT', 'COMMERCIAL_SALES', 'UNKNOWN', 'UNKNOWN', 0)
                    """,
                    (fac_id, fac_id, fac_id)
                )

            # Miami Valley Steel secondary direct contact
            if c["num"] == 11:
                conn.execute(
                    """
                    INSERT INTO contacts (
                        facility_id, contact_identity, person_name, exact_published_title,
                        department, phone_number, phone_directness, email_address, email_directness,
                        role_category, outbound_shipping_procurement_relevance,
                        broker_procurement_relevance, is_primary_contact
                    ) VALUES
                    (?, 'NAMED_PERSON', 'Doug Fenter', NULL, 'Shipping / Sales', '(937) 773-7127', 'GENERAL_SWITCHBOARD', 'doug.fenter@miamivalleysteel.com', 'DIRECT_PERSON', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', 0)
                    """,
                    (fac_id,)
                )

            # Leslie Forest secondary shipping email
            if c["num"] == 5:
                conn.execute(
                    """
                    INSERT INTO contacts (
                        facility_id, contact_identity, person_name, exact_published_title,
                        department, phone_number, phone_directness, email_address, email_directness,
                        role_category, outbound_shipping_procurement_relevance,
                        broker_procurement_relevance, is_primary_contact
                    ) VALUES
                    (?, 'DEPARTMENT', NULL, 'Shipping Department', 'Shipping', '(604) 952-4537', 'GENERAL_SWITCHBOARD', 'shipping@leslieforest.com', 'DEPARTMENT', 'FREIGHT_LOGISTICS', 'UNKNOWN', 'UNKNOWN', 0)
                    """,
                    (fac_id,)
                )

            # E. Prospect Lifecycle (DISCOVERY ONLY)
            conn.execute(
                """
                INSERT INTO prospect_lifecycle (
                    facility_id, stage, entered_discovery_at, discovered_at,
                    qualified_at, shortlisted_at, archived_at, qualification_notes, notes, created_at, updated_at
                ) VALUES (?, 'DISCOVERY', ?, ?, NULL, NULL, NULL, NULL, 'Imported from Prospect Expansion Batch #1', ?, ?)
                """,
                (fac_id, OBSERVED_DATE, OBSERVED_DATE, OBSERVED_DATE, OBSERVED_DATE)
            )

            # F. Discovery Intake Audit
            conn.execute(
                """
                INSERT INTO discovery_intake_audit (
                    batch_name, candidate_company_name, candidate_facility_name,
                    city, state_prov, country, intake_fingerprint, intake_status,
                    target_facility_id, website_url, facility_address, batch_reference,
                    reason_or_notes, reason_notes, reviewed_at, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'APPROVED_FOR_IMPORT', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    BATCH_NAME, c["brand"], c["fac_name"], c["city"], c["state"], c["country"],
                    fp, fac_id, c["website_url"], c["address"], BATCH_NAME,
                    c["note"], c["note"], OBSERVED_DATE, OBSERVED_DATE
                )
            )
            inserted_count += 1

        # 3. Final Verification
        fk_errors = conn.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key integrity check failed after Batch #1 import: {fk_errors}")
        integrity = conn.execute("PRAGMA integrity_check;").fetchall()
        if not integrity or integrity[0][0] != "ok":
            raise RuntimeError(f"Database integrity check failed after Batch #1 import: {integrity}")

        # Counts
        total_prospects = conn.execute("SELECT count(*) FROM prospect_lifecycle").fetchone()[0]
        shortlisted = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
        discovery = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
        qualified = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'QUALIFIED'").fetchone()[0]

        return {
            "inserted_discovery": inserted_count,
            "skipped_existing": skipped_count,
            "deferred_registered": deferred_registered,
            "total_lifecycle": total_prospects,
            "shortlisted_count": shortlisted,
            "discovery_count": discovery,
            "qualified_count": qualified,
        }


if __name__ == "__main__":
    res = import_batch1()
    print("Batch #1 import completed successfully:", res)
