-- Table definitions for the Argus dynamic database.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS response_metadata(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    expires_at TEXT,
    argus_expires_at TEXT -- included to allow custom expiration handling
)STRICT;

-- Table for storing request metadata, linked to response metadata.
-- Not sure if this will be used. maybe store all data in response table row?
CREATE TABLE IF NOT EXISTS request_metadata(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metadata_json TEXT,
    response_metadata_id INTEGER,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
)STRICT;

CREATE TABLE IF NOT EXISTS universe_prices(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id INTEGER NOT NULL,
    average_price INTEGER, -- stored as an integer for precision. Values are assumed to be 0.00 format
    adjusted_price INTEGER, -- stored as an integer for precision. Values are assumed to be 0.00 format
    response_metadata_id INTEGER,
    FOREIGN KEY(response_metadata_id) REFERENCES response_metadata(id)
)STRICT;

CREATE TABLE IF NOT EXISTS cost_indices(
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

CREATE TABLE IF NOT EXISTS corporation_jobs(
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