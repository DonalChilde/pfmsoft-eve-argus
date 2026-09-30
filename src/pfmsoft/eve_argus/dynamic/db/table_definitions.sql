-- Table definitions for the Argus dynamic database.
-- This database stores data retrieved from the EVE Online API.

PRAGMA foreign_keys = ON;

-- This table stores metadata about API responses, including when they were received and when they expire.
CREATE TABLE IF NOT EXISTS response_metadata(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    expires_at TEXT,
    argus_expires_at TEXT -- included to allow custom expiration handling
)STRICT;

-- GetMarketsRegionIdOrders API response metadata link.
CREATE TABLE IF NOT EXISTS get_markets_region_id_orders_response(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_metadata_id INTEGER,
    region_id INTEGER NOT NULL,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
) STRICT;

-- This table stores records from the GetMarketsRegionIdOrders API response.
CREATE TABLE IF NOT EXISTS market_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_metadata_id INTEGER,
    region_id INTEGER NOT NULL,
    duration INTEGER NOT NULL,
    is_buy_order INTEGER NOT NULL,
    issued TEXT NOT NULL,
    location_id INTEGER NOT NULL,
    min_volume INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    price INTEGER NOT NULL, -- stored as an integer for precision. Values are assumed to be 0.00 format
    range_ TEXT NOT NULL,
    system_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    volume_remain INTEGER NOT NULL,
    volume_total INTEGER NOT NULL,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
) STRICT;

-- This table is used to store summarized market order data for a specific region, type, solar system, and location combination
CREATE TABLE IF NOT EXISTS order_summaries (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    response_metadata_id INTEGER,
    region_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    system_id INTEGER,
    location_id INTEGER,
    is_buy_summary INTEGER NOT NULL,
    five_price INTEGER NOT NULL,
    five_orders INTEGER NOT NULL,
    five_items INTEGER NOT NULL,
    lowest INTEGER NOT NULL,
    highest INTEGER NOT NULL,
    average INTEGER NOT NULL,
    total_items INTEGER NOT NULL,
    total_orders INTEGER NOT NULL,
    filtered_items INTEGER NOT NULL,
    filtered_orders INTEGER NOT NULL,
    UNIQUE (region_id, type_id, system_id, location_id),
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
) STRICT;

-- GetMarketsPrices
CREATE TABLE IF NOT EXISTS get_markets_prices_response(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_metadata_id INTEGER,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
) STRICT;

-- This table stores the records from the GetMarketsPrices API response
CREATE TABLE IF NOT EXISTS markets_prices(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id INTEGER NOT NULL,
    average_price INTEGER, -- stored as an integer for precision. Values are assumed to be 0.00 format
    adjusted_price INTEGER, -- stored as an integer for precision. Values are assumed to be 0.00 format
    response_metadata_id INTEGER,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
)STRICT;

-- GetIndustrySystems
CREATE TABLE IF NOT EXISTS get_industry_systems_response(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_metadata_id INTEGER,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
) STRICT;

-- This table stores the records from the GetIndustrySystems API response
-- The table name is different to more clearly reflect the data stored.
CREATE TABLE IF NOT EXISTS system_cost_indices(
    system_id INTEGER PRIMARY KEY,
    copying INTEGER, -- stored as an integer for precision. Values are assumed to be 0.0000 format
    manufacturing INTEGER, -- stored as an integer for precision. Values are assumed to be 0.0000 format
    invention INTEGER, -- stored as an integer for precision. Values are assumed to be 0.0000 format
    reaction INTEGER, -- stored as an integer for precision. Values are assumed to be 0.0000 format
    researching_material_efficiency INTEGER, -- stored as an integer for precision. Values are assumed to be 0.0000 format
    researching_time_efficiency INTEGER, -- stored as an integer for precision. Values are assumed to be 0.0000 format
    response_metadata_id INTEGER,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
)STRICT;

-- GetCorporationsCorporationIdIndustryJobs
CREATE TABLE IF NOT EXISTS get_corporations_corporation_id_industry_jobs_response(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_metadata_id INTEGER,
    corporation_id INTEGER NOT NULL,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
) STRICT;

-- This table stores the records from the GetCorporationsCorporationIdIndustryJobs API response
CREATE TABLE IF NOT EXISTS corporation_industry_jobs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    corporation_id INTEGER NOT NULL,
    activity_id INTEGER NOT NULL,
    blueprint_id INTEGER NOT NULL,
    blueprint_location_id INTEGER NOT NULL,
    blueprint_type_id INTEGER NOT NULL,
    completed_character_id INTEGER,
    completed_date TEXT,
    cost INTEGER, -- stored as an integer for precision. Values are assumed to be 0.00 format
    duration INTEGER NOT NULL,
    end_date TEXT NOT NULL,
    facility_id INTEGER NOT NULL,
    installer_id INTEGER NOT NULL,
    job_id INTEGER NOT NULL,
    licensed_runs INTEGER,
    location_id INTEGER NOT NULL,
    output_location_id INTEGER NOT NULL,
    pause_date TEXT,
    probability REAL,
    product_type_id INTEGER,
    runs INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    status TEXT NOT NULL,
    successful_runs INTEGER,
    response_metadata_id INTEGER,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
)STRICT;

-- GetCorporationsCorporationIdBlueprints
CREATE TABLE IF NOT EXISTS get_corporations_corporation_id_blueprints_response(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    response_metadata_id INTEGER,
    corporation_id INTEGER NOT NULL,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id) 
) STRICT;

-- This table stores the records from the GetCorporationsCorporationIdBlueprints API response
CREATE TABLE IF NOT EXISTS corporation_blueprints(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    corporation_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL, -- the unique identifier for the blueprint item.
    type_id INTEGER NOT NULL, -- the type ID of the blueprint.
    location_id INTEGER NOT NULL, -- the location ID where the blueprint is stored.
    location_flag TEXT NOT NULL, -- the flag indicating the type of location of the blueprint within the location_id.
    quantity INTEGER NOT NULL, -- -1 for BPO, -2 for BPC, >0 for unprocessed stack of BPO.
    time_efficiency INTEGER,
    material_efficiency INTEGER,
    runs INTEGER NOT NULL, -- -1 for BPO, or number of runs for BPC.
    response_metadata_id INTEGER,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
)STRICT;