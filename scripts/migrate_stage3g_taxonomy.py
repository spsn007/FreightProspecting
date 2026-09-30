"""
FreightProspecting V1 — Stage 3G Taxonomy & Seasonality Migration Script
Additive taxonomy expansion introducing:
- Seasonal & Opportunity Freight
- Regional Specialty Manufacturing
- Packaging & High-Cube Industrial
- Core Existing Families (Lumber, Metals, Concrete, Plastics, Building Materials, Industrial Mfg)
- Deferred Bulk Grain note
- Facility-level multi-category associations
- Invariant: Zero changes to lifecycle, zero fake operational records, verified equipment strictly [1, 2, 18].
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

DB_PATH = Path("data/prospects.db")


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


COMMODITY_FAMILIES = [
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "display_name": "Seasonal & Opportunity Freight",
        "description": "High-volume seasonal peaks, weather-sensitive, holiday, and landscaping/harvest surge categories.",
        "sort_order": 1,
        "is_active": 1,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "display_name": "Regional Specialty Manufacturing",
        "description": "Regional manufacturing with specialized equipment fit, awkward dimensions, and project delivery.",
        "sort_order": 2,
        "is_active": 1,
    },
    {
        "family_code": "PACKAGING_HIGH_CUBE",
        "display_name": "Packaging & High-Cube Industrial",
        "description": "High-cube, lightweight or bulky packaging materials primarily moving on dry van equipment.",
        "sort_order": 3,
        "is_active": 1,
    },
    {
        "family_code": "FOREST_PRODUCTS",
        "display_name": "Lumber & Forest Products",
        "description": "Dimension lumber, hardwoods, timbers, wood residuals, and primary forest products.",
        "sort_order": 4,
        "is_active": 1,
    },
    {
        "family_code": "METALS_STEEL",
        "display_name": "Steel & Metal Products",
        "description": "Flat-rolled coils, structural steel, plate, bar, pipe, and non-ferrous metals.",
        "sort_order": 5,
        "is_active": 1,
    },
    {
        "family_code": "CONCRETE_PRECAST",
        "display_name": "Concrete & Precast Products",
        "description": "Precast structural panels, architectural concrete, drainage, pipe, and infrastructure components.",
        "sort_order": 6,
        "is_active": 1,
    },
    {
        "family_code": "PLASTICS_TOOLING",
        "display_name": "Plastics & Industrial Tooling",
        "description": "Injection molded plastics, precision tooling, dies, and custom composite components.",
        "sort_order": 7,
        "is_active": 1,
    },
    {
        "family_code": "BUILDING_MATERIALS",
        "display_name": "Building Materials & Construction Products",
        "description": "Siding, insulation, gypsum, shingles, and general commercial/residential building supplies.",
        "sort_order": 8,
        "is_active": 1,
    },
    {
        "family_code": "INDUSTRIAL_MFG",
        "display_name": "Industrial Manufacturing & Equipment",
        "description": "Commercial equipment, machinery, automotive stampings, and heavy industrial assemblies.",
        "sort_order": 9,
        "is_active": 1,
    },
    {
        "family_code": "BULK_AGRICULTURE",
        "display_name": "Bulk Agriculture",
        "description": "Bulk grain, soybeans, corn, wheat — DEFERRED in V1 (requires Hopper/Bulk equipment family).",
        "sort_order": 10,
        "is_active": 0,  # Explicitly inactive / deferred
    },
]


COMMODITY_CATEGORIES = [
    # ----------------------------------------------------
    # FAMILY: Seasonal & Opportunity Freight (8 Categories)
    # ----------------------------------------------------
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "category_code": "CHRISTMAS_TREES",
        "display_name": "Christmas Trees",
        "description": "Live cut Christmas trees moving in high volume during late fall to retail lots and distribution hubs.",
        "typical_equipment_fit": "DRY_VAN / FLATBED",
        "seasonality_profile": "HOLIDAY_PEAK",
        "peak_months": "Holiday Peak — Nov–Dec",
        "operating_characteristics": "SEASONAL, WEATHER_SENSITIVE, HIGH_CUBE",
        "sort_order": 1,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "category_code": "NURSERY_TREES_SHRUBS",
        "display_name": "Nursery Trees & Shrubs",
        "description": "Hardy nursery field stock, containerized trees, and shrubs moving to commercial growers, landscaping hubs, and garden centers. Hardy outdoor stock compatible with non-reefer equipment where operationally appropriate.",
        "typical_equipment_fit": "FLATBED / STEP_DECK / DRY_VAN",
        "seasonality_profile": "MULTI_SEASON",
        "peak_months": "Mar–Jun, Sep–Nov",
        "operating_characteristics": "SEASONAL, WEATHER_SENSITIVE, REGIONAL",
        "sort_order": 2,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "category_code": "HARDY_OUTDOOR_PLANTS",
        "display_name": "Hardy Outdoor Plants / Balled-and-Burlapped Stock",
        "description": "Balled-and-burlapped (B&B) trees, root-pruned hardy outdoor nursery stock, and heavy landscaping perennials. Hardy outdoor stock compatible with non-reefer equipment where operationally appropriate.",
        "typical_equipment_fit": "FLATBED / STEP_DECK / DRY_VAN",
        "seasonality_profile": "SPRING_PEAK",
        "peak_months": "Mar–May",
        "operating_characteristics": "SEASONAL, WEATHER_SENSITIVE, BULKY",
        "sort_order": 3,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "category_code": "HAY_STRAW",
        "display_name": "Hay & Straw / Compressed Bales",
        "description": "Alfalfa, timothy, orchard grass, and compressed straw bales for agricultural, equestrian, and export markets.",
        "typical_equipment_fit": "FLATBED / DRY_VAN",
        "seasonality_profile": "HARVEST_DRIVEN",
        "peak_months": "Jun–Oct",
        "operating_characteristics": "SEASONAL, HARVEST_DRIVEN, BULKY",
        "sort_order": 4,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "category_code": "WOOD_PELLETS_FIREWOOD",
        "display_name": "Wood Pellets / Packaged Firewood",
        "description": "Bagged hardwood/softwood fuel pellets, kiln-dried bundled firewood, and biomass heating fuel.",
        "typical_equipment_fit": "DRY_VAN / FLATBED",
        "seasonality_profile": "WINTER_PEAK",
        "peak_months": "Sep–Feb",
        "operating_characteristics": "SEASONAL, WEATHER_SENSITIVE, HEAVY",
        "sort_order": 5,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "category_code": "PACKAGED_ICE_MELT",
        "display_name": "Packaged Ice Melt / Bagged Road Salt",
        "description": "Palletized bagged rock salt, calcium chloride pellets, and specialized runway/commercial de-icing blends. Non-bulk packaged goods only.",
        "typical_equipment_fit": "DRY_VAN / FLATBED",
        "seasonality_profile": "WINTER_PEAK",
        "peak_months": "Nov–Mar",
        "operating_characteristics": "SEASONAL, WEATHER_DRIVEN, HEAVY",
        "sort_order": 6,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "category_code": "BAGGED_MULCH_SOIL",
        "display_name": "Bagged Mulch / Soil / Landscape Products",
        "description": "Bagged bark mulch, premium potting soils, peat blends, and bulk landscape supplies on pallets.",
        "typical_equipment_fit": "FLATBED / DRY_VAN",
        "seasonality_profile": "SPRING_PEAK",
        "peak_months": "Mar–Jun",
        "operating_characteristics": "SEASONAL, BULKY, HEAVY",
        "sort_order": 7,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "SEASONAL_OPPORTUNITY",
        "category_code": "PAVERS_LANDSCAPE_STONE",
        "display_name": "Pavers / Landscape Blocks / Brick / Manufactured Stone",
        "description": "Interlocking concrete pavers, retaining wall blocks, architectural brick, and manufactured veneer stone.",
        "typical_equipment_fit": "FLATBED",
        "seasonality_profile": "PROJECT_DRIVEN",
        "peak_months": "Apr–Oct",
        "operating_characteristics": "PROJECT_DRIVEN, HEAVY, JOB_SITE_DELIVERY",
        "sort_order": 8,
        "is_active": 1,
        "deferred_status_note": None,
    },

    # ---------------------------------------------------------
    # FAMILY: Regional Specialty Manufacturing (11 Categories)
    # ---------------------------------------------------------
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "PALLETS_CRATES_DUNNAGE",
        "display_name": "Wood Pallets / Crates / Skids / Dunnage",
        "description": "New and reconditioned wooden GMA pallets, custom heavy machinery crates, skids, and industrial dunnage.",
        "typical_equipment_fit": "FLATBED / DRY_VAN",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "REGIONAL, BULKY, HIGH_CUBE",
        "sort_order": 9,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "ROOF_TRUSSES_WALL_PANELS",
        "display_name": "Roof Trusses / Wall Panels / Engineered Components",
        "description": "Engineered wood and light-gauge steel roof trusses, prefabricated wall panels, and floor cassette systems.",
        "typical_equipment_fit": "FLATBED / STEP_DECK",
        "seasonality_profile": "PROJECT_DRIVEN",
        "peak_months": "Apr–Nov",
        "operating_characteristics": "PROJECT_DRIVEN, ODD_DIMENSIONS, JOB_SITE_DELIVERY",
        "sort_order": 10,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "HDPE_PVC_PIPE",
        "display_name": "HDPE / PVC Pipe / Conduit / Irrigation Pipe",
        "description": "High-density polyethylene, PVC drainage/sewer pipe, electrical conduit, and agricultural irrigation tubing.",
        "typical_equipment_fit": "FLATBED",
        "seasonality_profile": "PROJECT_DRIVEN",
        "peak_months": "Apr–Oct",
        "operating_characteristics": "REGIONAL, BULKY, ODD_DIMENSIONS",
        "sort_order": 11,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "FENCING_GATES_POSTS",
        "display_name": "Fencing / Gates / Posts",
        "description": "Treated wooden agricultural posts, wire field fencing, ornamental steel gates, and industrial chain link.",
        "typical_equipment_fit": "FLATBED",
        "seasonality_profile": "MULTI_SEASON",
        "peak_months": "Apr–Sep",
        "operating_characteristics": "REGIONAL, BULKY, PROJECT_DRIVEN",
        "sort_order": 12,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "METAL_ROOFING_SIDING",
        "display_name": "Metal Roofing / Siding / Roll-Formed Panels",
        "description": "Standing seam architectural metal roof panels, corrugated agricultural siding, trims, and flashings.",
        "typical_equipment_fit": "FLATBED",
        "seasonality_profile": "PROJECT_DRIVEN",
        "peak_months": "Apr–Nov",
        "operating_characteristics": "PROJECT_DRIVEN, ODD_DIMENSIONS, JOB_SITE_DELIVERY",
        "sort_order": 13,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "PORTABLE_BUILDINGS",
        "display_name": "Portable Buildings / Sheds / Modular Cabins",
        "description": "Prefabricated wooden/steel storage sheds, mobile site offices, hunting cabins, and modular utility structures.",
        "typical_equipment_fit": "FLATBED / STEP_DECK",
        "seasonality_profile": "SPRING_PEAK",
        "peak_months": "Apr–Oct",
        "operating_characteristics": "ODD_DIMENSIONS, BULKY, REGIONAL",
        "sort_order": 14,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "AG_EQUIPMENT",
        "display_name": "Agricultural Implements / Farm Equipment",
        "description": "Tillage tools, planters, sprayers, grain augers, hay equipment, and tractor attachments.",
        "typical_equipment_fit": "FLATBED / STEP_DECK",
        "seasonality_profile": "HARVEST_DRIVEN",
        "peak_months": "Mar–May, Aug–Oct",
        "operating_characteristics": "HEAVY, ODD_DIMENSIONS, REGIONAL",
        "sort_order": 15,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "USED_MACHINERY",
        "display_name": "Used Machinery & Industrial Equipment",
        "description": "Surplus metalworking CNC machinery, stamping presses, industrial processing gear, and plant relocations.",
        "typical_equipment_fit": "FLATBED / STEP_DECK",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "HEAVY, ODD_DIMENSIONS, PROJECT_DRIVEN",
        "sort_order": 16,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "HVAC_EQUIPMENT",
        "display_name": "HVAC, Rooftop Units & Industrial Cooling",
        "description": "Commercial packaged rooftop HVAC units, cooling towers, industrial chillers, and air handling equipment.",
        "typical_equipment_fit": "FLATBED / STEP_DECK / DRY_VAN",
        "seasonality_profile": "MULTI_SEASON",
        "peak_months": "May–Aug, Oct–Dec",
        "operating_characteristics": "BULKY, PROJECT_DRIVEN, REGIONAL",
        "sort_order": 17,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "PLAYGROUND_PARK_EQUIPMENT",
        "display_name": "Playground, Park & Bleacher Equipment",
        "description": "Commercial playground structures, municipal park shelters, outdoor bleachers, and sports court equipment.",
        "typical_equipment_fit": "FLATBED / DRY_VAN",
        "seasonality_profile": "SPRING_PEAK",
        "peak_months": "Mar–Jun",
        "operating_characteristics": "BULKY, ODD_DIMENSIONS, PROJECT_DRIVEN",
        "sort_order": 18,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "REGIONAL_SPECIALTY_MFG",
        "category_code": "SOLAR_RACKING",
        "display_name": "Solar Racking & Mounting Structures",
        "description": "Ground-mount solar racking steel components, utility-scale tracker tubes, and rooftop mounting hardware.",
        "typical_equipment_fit": "FLATBED",
        "seasonality_profile": "PROJECT_DRIVEN",
        "peak_months": "Apr–Oct",
        "operating_characteristics": "PROJECT_DRIVEN, HEAVY, JOB_SITE_DELIVERY",
        "sort_order": 19,
        "is_active": 1,
        "deferred_status_note": None,
    },

    # -------------------------------------------------------------
    # FAMILY: Packaging & High-Cube Industrial (6 Categories)
    # -------------------------------------------------------------
    {
        "family_code": "PACKAGING_HIGH_CUBE",
        "category_code": "CORRUGATED_PACKAGING",
        "display_name": "Corrugated Boxes / Industrial Packaging",
        "description": "Corrugated shipping cartons, die-cut packaging, heavy bulk bins (gaylords), and honeycomb protective packaging.",
        "typical_equipment_fit": "DRY_VAN",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round / Q3–Q4 peak",
        "operating_characteristics": "HIGH_CUBE, REGIONAL",
        "sort_order": 20,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "PACKAGING_HIGH_CUBE",
        "category_code": "PLASTIC_PACKAGING",
        "display_name": "Plastic Packaging & Rigid Containers",
        "description": "Rigid plastic bottles, jugs, pails, thermoformed trays, and industrial bulk containers.",
        "typical_equipment_fit": "DRY_VAN",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "HIGH_CUBE, REGIONAL",
        "sort_order": 21,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "PACKAGING_HIGH_CUBE",
        "category_code": "CLEAN_DRUMS",
        "display_name": "Clean Industrial Drums",
        "description": "New and reconditioned clean steel, polyethylene, and fiber drums (55-gallon standard) for non-hazardous industrial goods.",
        "typical_equipment_fit": "DRY_VAN",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "HIGH_CUBE, BULKY, REGIONAL",
        "sort_order": 22,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "PACKAGING_HIGH_CUBE",
        "category_code": "CLEAN_IBC_TOTES",
        "display_name": "Clean IBC Totes / Containers",
        "description": "Clean 275-gallon and 330-gallon intermediate bulk containers with caged pallet bases for non-hazardous liquids.",
        "typical_equipment_fit": "DRY_VAN",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "HIGH_CUBE, BULKY, REGIONAL",
        "sort_order": 23,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "PACKAGING_HIGH_CUBE",
        "category_code": "MATTRESSES_FURNITURE",
        "display_name": "Mattresses / Upholstered Furniture",
        "description": "Commercial mattresses, box springs, foam cushions, and upholstered contract furniture.",
        "typical_equipment_fit": "DRY_VAN",
        "seasonality_profile": "MULTI_SEASON",
        "peak_months": "Jan–Feb, May–Sep",
        "operating_characteristics": "HIGH_CUBE, BULKY",
        "sort_order": 24,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "PACKAGING_HIGH_CUBE",
        "category_code": "FOAM_PRODUCTS",
        "display_name": "Foam Products",
        "description": "Expanded polystyrene (EPS), polyurethane foam blocks, molded foam protective inserts, and foam insulation sheets.",
        "typical_equipment_fit": "DRY_VAN",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "HIGH_CUBE, BULKY",
        "sort_order": 25,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "PACKAGING_HIGH_CUBE",
        "category_code": "INDUSTRIAL_PAPER_PACKAGING",
        "display_name": "Industrial Paper Packaging / Tubes / Cores / Drums / Reels",
        "description": "Industrial paperboard packaging, spiral tubes, cores, fiber drums, protective packaging, and reels.",
        "typical_equipment_fit": "DRY_VAN / FLATBED",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "REGIONAL, BULKY, HIGH_CUBE",
        "sort_order": 26,
        "is_active": 1,
        "deferred_status_note": None,
    },

    # -------------------------------------------------------------
    # CORE FAMILIES: Categories for baseline 615 facilities
    # -------------------------------------------------------------
    {
        "family_code": "FOREST_PRODUCTS",
        "category_code": "LUMBER_FOREST_PRODUCTS",
        "display_name": "Lumber & Forest Products",
        "description": "Softwood dimension lumber, hardwood lumber, timbers, cants, plywood, and wood chips.",
        "typical_equipment_fit": "FLATBED",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round / Spring build",
        "operating_characteristics": "HEAVY, BULKY, REGIONAL",
        "sort_order": 26,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "METALS_STEEL",
        "category_code": "STEEL_METALS",
        "display_name": "Steel & Metal Products",
        "description": "Flat-rolled carbon and stainless steel coils, plate, structural shapes, tubing, and aluminum extrusions.",
        "typical_equipment_fit": "FLATBED / STEP_DECK",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "HEAVY, DENSE, REGIONAL",
        "sort_order": 27,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "CONCRETE_PRECAST",
        "category_code": "CONCRETE_PRECAST_PRODUCTS",
        "display_name": "Precast Concrete & Heavy Building",
        "description": "Architectural and structural precast concrete elements, utility vaults, bridge girders, and pipe culverts.",
        "typical_equipment_fit": "FLATBED / STEP_DECK",
        "seasonality_profile": "PROJECT_DRIVEN",
        "peak_months": "Apr–Nov",
        "operating_characteristics": "HEAVY, ODD_DIMENSIONS, JOB_SITE_DELIVERY",
        "sort_order": 28,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "PLASTICS_TOOLING",
        "category_code": "PLASTICS_TOOLING_PRODUCTS",
        "display_name": "Plastics & Industrial Tooling",
        "description": "Precision injection molds, plastic tooling, molded plastic assemblies, and industrial automotive components.",
        "typical_equipment_fit": "DRY_VAN / FLATBED",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "REGIONAL, HIGH_CUBE",
        "sort_order": 29,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "BUILDING_MATERIALS",
        "category_code": "BUILDING_MATERIALS_GENERAL",
        "display_name": "Building Materials & Construction Products",
        "description": "Commercial wallboard, fiber cement siding, thermal insulation, and general construction products.",
        "typical_equipment_fit": "FLATBED / DRY_VAN",
        "seasonality_profile": "PROJECT_DRIVEN",
        "peak_months": "Apr–Oct",
        "operating_characteristics": "BULKY, HEAVY, PROJECT_DRIVEN",
        "sort_order": 30,
        "is_active": 1,
        "deferred_status_note": None,
    },
    {
        "family_code": "INDUSTRIAL_MFG",
        "category_code": "INDUSTRIAL_MFG_EQUIPMENT",
        "display_name": "Industrial Manufacturing & Equipment",
        "description": "Heavy industrial assemblies, machinery components, automotive stampings, and commercial equipment.",
        "typical_equipment_fit": "FLATBED / STEP_DECK / DRY_VAN",
        "seasonality_profile": "YEAR_ROUND",
        "peak_months": "Year-round",
        "operating_characteristics": "HEAVY, REGIONAL",
        "sort_order": 31,
        "is_active": 1,
        "deferred_status_note": None,
    },

    # -------------------------------------------------------------
    # DEFERRED BULK GRAIN CATEGORY
    # -------------------------------------------------------------
    {
        "family_code": "BULK_AGRICULTURE",
        "category_code": "BULK_GRAIN_DEFERRED",
        "display_name": "Bulk Grain (Soybeans, Corn, Wheat)",
        "description": "Bulk grain, soybeans, corn, and wheat requiring hopper/bulk grain trailers. DEFERRED in V1.",
        "typical_equipment_fit": "HOPPER / GRAIN TRAILER / BULK AG",
        "seasonality_profile": "HARVEST_DRIVEN",
        "peak_months": "Sep–Nov",
        "operating_characteristics": "BULK_AG, HARVEST_DRIVEN",
        "sort_order": 32,
        "is_active": 0,  # DEFERRED
        "deferred_status_note": "BULK AGRICULTURE — requires Hopper/Bulk equipment family",
    },
]


def run_migration(db_path: Path = DB_PATH):
    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # Step 1: Create tables if not exist
    print("1. Creating taxonomy tables...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS commodity_families (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_code TEXT UNIQUE NOT NULL,
        display_name TEXT NOT NULL,
        description TEXT,
        sort_order INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
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
        created_at TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS facility_commodity_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id INTEGER NOT NULL REFERENCES facilities(id),
        category_id INTEGER NOT NULL REFERENCES commodity_categories(id),
        source_evidence_notes TEXT,
        is_primary INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        UNIQUE(facility_id, category_id)
    );
    """)

    # Step 2: Add columns to facility_commodities if missing
    print("2. Checking facility_commodities columns...")
    fc_cols = [c[1] for c in cur.execute("PRAGMA table_info(facility_commodities)").fetchall()]
    if "commodity_category_id" not in fc_cols:
        print("  Adding column commodity_category_id...")
        cur.execute("ALTER TABLE facility_commodities ADD COLUMN commodity_category_id INTEGER REFERENCES commodity_categories(id);")
    if "category_code" not in fc_cols:
        print("  Adding column category_code...")
        cur.execute("ALTER TABLE facility_commodities ADD COLUMN category_code TEXT;")
    if "seasonality_profile" not in fc_cols:
        print("  Adding column seasonality_profile...")
        cur.execute("ALTER TABLE facility_commodities ADD COLUMN seasonality_profile TEXT DEFAULT NULL;")
    if "peak_months" not in fc_cols:
        print("  Adding column peak_months...")
        cur.execute("ALTER TABLE facility_commodities ADD COLUMN peak_months TEXT DEFAULT NULL;")

    now = get_timestamp()

    # Step 3: Upsert commodity_families
    print("3. Seeding commodity_families...")
    fam_id_map = {}
    for fam in COMMODITY_FAMILIES:
        existing = cur.execute("SELECT id FROM commodity_families WHERE family_code = ?", (fam["family_code"],)).fetchone()
        if existing:
            fam_id_map[fam["family_code"]] = existing[0]
            cur.execute("""
                UPDATE commodity_families
                SET display_name = ?, description = ?, sort_order = ?, is_active = ?
                WHERE id = ?
            """, (fam["display_name"], fam["description"], fam["sort_order"], fam["is_active"], existing[0]))
        else:
            cur.execute("""
                INSERT INTO commodity_families (family_code, display_name, description, sort_order, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (fam["family_code"], fam["display_name"], fam["description"], fam["sort_order"], fam["is_active"], now))
            fam_id_map[fam["family_code"]] = cur.lastrowid

    # Step 4: Upsert commodity_categories
    print("4. Seeding commodity_categories...")
    cat_id_map = {}
    for cat in COMMODITY_CATEGORIES:
        fid = fam_id_map[cat["family_code"]]
        existing = cur.execute("SELECT id FROM commodity_categories WHERE category_code = ?", (cat["category_code"],)).fetchone()
        if existing:
            cat_id_map[cat["category_code"]] = existing[0]
            cur.execute("""
                UPDATE commodity_categories
                SET family_id = ?, display_name = ?, description = ?, typical_equipment_fit = ?,
                    seasonality_profile = ?, peak_months = ?, operating_characteristics = ?,
                    sort_order = ?, is_active = ?, deferred_status_note = ?
                WHERE id = ?
            """, (
                fid, cat["display_name"], cat["description"], cat["typical_equipment_fit"],
                cat["seasonality_profile"], cat["peak_months"], cat["operating_characteristics"],
                cat["sort_order"], cat["is_active"], cat["deferred_status_note"], existing[0]
            ))
        else:
            cur.execute("""
                INSERT INTO commodity_categories (
                    family_id, category_code, display_name, description, typical_equipment_fit,
                    seasonality_profile, peak_months, operating_characteristics, sort_order,
                    is_active, deferred_status_note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fid, cat["category_code"], cat["display_name"], cat["description"], cat["typical_equipment_fit"],
                cat["seasonality_profile"], cat["peak_months"], cat["operating_characteristics"], cat["sort_order"],
                cat["is_active"], cat["deferred_status_note"], now
            ))
            cat_id_map[cat["category_code"]] = cur.lastrowid

    # Step 5: Map existing facility_commodities to Core Categories
    print("5. Mapping existing facility_commodities to taxonomy categories...")
    rows = cur.execute("SELECT id, facility_id, commodity_category, specific_products FROM facility_commodities WHERE commodity_category_id IS NULL OR category_code IS NULL").fetchall()
    for row in rows:
        fc_id = row["id"]
        fac_id = row["facility_id"]
        comm_cat = (row["commodity_category"] or "").lower()
        prod = (row["specific_products"] or "").lower()

        # Deterministic assignment to core family category based on existing verified commodity strings
        if fac_id == 613:
            code = "ROOF_TRUSSES_WALL_PANELS"
        elif fac_id in (365, 366):
            code = "INDUSTRIAL_PAPER_PACKAGING"
        elif any(w in comm_cat for w in ["lumber", "forest", "wood", "plywood", "osb", "timber", "pallet", "paper", "pulp"]):
            code = "LUMBER_FOREST_PRODUCTS"
        elif any(w in comm_cat for w in ["steel", "metal", "coil", "iron", "sheet", "plate", "tube", "tubing", "pipe", "aluminum", "strip"]):
            code = "STEEL_METALS"
        elif any(w in comm_cat for w in ["precast", "concrete", "bridge", "vault", "culvert", "prestressed", "drainage", "curb"]):
            code = "CONCRETE_PRECAST_PRODUCTS"
        elif any(w in comm_cat for w in ["plastic", "mold", "molding", "tooling"]):
            code = "PLASTICS_TOOLING_PRODUCTS"
        elif any(w in comm_cat for w in ["building", "siding", "gypsum", "insulation", "wallboard", "shingle", "masonry", "brick", "roofing"]):
            code = "BUILDING_MATERIALS_GENERAL"
        else:
            code = "INDUSTRIAL_MFG_EQUIPMENT"

        target_cat_id = cat_id_map[code]
        cur.execute("""
            UPDATE facility_commodities
            SET commodity_category_id = ?, category_code = ?
            WHERE id = ?
        """, (target_cat_id, code, fc_id))

        # Also ensure primary mapping in facility_commodity_mappings
        cur.execute("""
            INSERT INTO facility_commodity_mappings (facility_id, category_id, source_evidence_notes, is_primary, created_at)
            VALUES (?, ?, 'Primary audited facility commodity classification', 1, ?)
            ON CONFLICT(facility_id, category_id) DO UPDATE SET is_primary = 1
        """, (fac_id, target_cat_id, now))

    # Step 6: Add specific verified secondary mappings for existing facilities matching Stage 3G categories
    print("6. Adding verified secondary mappings for existing facilities with primary evidence...")
    # Purge legacy invalid secondary mappings if present
    cur.execute("DELETE FROM facility_commodity_mappings WHERE is_primary = 0 AND facility_id IN (10, 11, 38, 39, 110);")
    # Audit Finding 8: Purge bulk mulch from BAGGED_MULCH_SOIL for facilities 5 and 460
    if "BAGGED_MULCH_SOIL" in cat_id_map:
        cur.execute("DELETE FROM facility_commodity_mappings WHERE category_id = ? AND facility_id IN (5, 460);", (cat_id_map["BAGGED_MULCH_SOIL"],))

    SECONDARY_MAPPINGS = [
        # (facility_id, category_code, notes)
        # Pallets & Dunnage
        (5, "PALLETS_CRATES_DUNNAGE", "Verified primary sawmill byproduct & pallet cants production (Battle Lumber Wadley)"),
        (13, "PALLETS_CRATES_DUNNAGE", "Verified industrial hardwood pallets, pipeline skids, and dunnage production (Edwards Wood Products Marshville)"),
        (231, "PALLETS_CRATES_DUNNAGE", "Verified dedicated industrial wooden pallet and skid manufacturing (Appling County Pallet Co. Baxley)"),
        (435, "PALLETS_CRATES_DUNNAGE", "Verified custom industrial wooden pallets, crates, and skids manufacturing (B&B Wood Products Brantford)"),
        # Clean Drums & IBC Totes
        (369, "CLEAN_DRUMS", "Verified industrial steel and fiber drum manufacturing (Greif Delaware Plant)"),
        (370, "CLEAN_IBC_TOTES", "Verified intermediate bulk containers (IBC) and plastic drum manufacturing (Greif Sharonville Facility)"),
        (370, "CLEAN_DRUMS", "Verified intermediate bulk containers and clean drum manufacturing (Greif Sharonville Facility)"),
        # Rigid & Flexible Packaging
        (363, "PLASTIC_PACKAGING", "Verified rigid plastic containers and packaging manufacturing (Berry Global Evansville)"),
        (364, "PLASTIC_PACKAGING", "Verified flexible packaging and protective film converting (Berry Global Franklin)"),
        # Wood Pellets & Fuel
        (90, "WOOD_PELLETS_FIREWOOD", "Verified wood pellet fuel manufacturing from sawmill residuals (Vanderwell Mitsue)"),
        (436, "WOOD_PELLETS_FIREWOOD", "Verified commercial wood fuel pellet manufacturing facility (Atikokan Renewable Fuels)"),
        (459, "WOOD_PELLETS_FIREWOOD", "Verified specialty wood fuel pellets and shavings (Vanderhoof Specialty Wood)"),
        # Agricultural Posts & Fencing
        (459, "FENCING_GATES_POSTS", "Verified cedar agricultural and residential fence posts (Vanderhoof Specialty Wood)"),
        (460, "FENCING_GATES_POSTS", "Verified pressure-treated agricultural fence posts and rails (Spray Lake Sawmills Cochrane)"),
        (465, "FENCING_GATES_POSTS", "Verified eastern white cedar fence posts and rustic rails (Scierie Gaston Morin Sainte-Justine)"),
        # Roof Trusses & Wall Panels / Mass Timber Secondary
        (558, "ROOF_TRUSSES_WALL_PANELS", "Verified steel joists and structural truss fabrication (M&G Steel Oakville)"),
        (613, "LUMBER_FOREST_PRODUCTS", "Verified secondary raw timber feedstock & dimension lumber processing (StructureCraft Abbotsford)"),
        # Metal Roofing & Siding
        (297, "METAL_ROOFING_SIDING", "Verified pre-engineered metal building siding and structural purlins (Dean Steel Buildings Thomasville)"),
        (288, "METAL_ROOFING_SIDING", "Verified metal roofing, siding, and structural framing components (Metal Sales Manufacturing Sellersburg)"),
    ]

    new_secondary_count = 0
    for fac_id, cat_code, notes in SECONDARY_MAPPINGS:
        if cat_code in cat_id_map:
            cid = cat_id_map[cat_code]
            cur.execute("""
                INSERT INTO facility_commodity_mappings (facility_id, category_id, source_evidence_notes, is_primary, created_at)
                VALUES (?, ?, ?, 0, ?)
                ON CONFLICT(facility_id, category_id) DO UPDATE SET source_evidence_notes = ?
            """, (fac_id, cid, notes, now, notes))
            new_secondary_count += 1

    print(f"  Added/updated {new_secondary_count} secondary category mappings across existing facilities.")

    conn.commit()
    conn.close()
    print("Migration Stage 3G completed successfully.")


if __name__ == "__main__":
    run_migration()
