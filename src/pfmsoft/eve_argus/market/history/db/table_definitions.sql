-- Table definitions for market history
PRAGMA foreign_keys = ON;

-- GetMarketsRegionIdHistory API response metadata.
-- Because this database only stores market history, we include response info here.
-- This table records the requests for market history. It is not keyed
-- off/to other tables.
CREATE TABLE IF NOT EXISTS market_history_response (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    expires_at TEXT,
    argus_expires_at TEXT, -- included to allow custom expiration handling
    region_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS market_history (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at TEXT NOT NULL,
    region_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    average INTEGER NOT NULL, -- stored as an integer for precision. Values are assumed to be 0.00 format
    date_ TEXT NOT NULL,
    highest INTEGER NOT NULL, -- stored as an integer for precision. Values are assumed to be 0.00 format
    lowest INTEGER NOT NULL, -- stored as an integer for precision. Values are assumed to be 0.00 format
    order_count INTEGER NOT NULL,
    volume INTEGER NOT NULL,
    UNIQUE(region_id, type_id, date_)
    ON CONFLICT REPLACE
) STRICT;