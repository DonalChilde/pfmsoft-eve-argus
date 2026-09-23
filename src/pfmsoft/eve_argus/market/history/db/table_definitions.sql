-- Table definitions for market history
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS market_history (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    region_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    average INTEGER NOT NULL, -- Stored as an integer to avoid floating point precision issues
    date_ TEXT NOT NULL,
    highest INTEGER NOT NULL, -- Stored as an integer to avoid floating point precision issues
    lowest INTEGER NOT NULL, -- Stored as an integer to avoid floating point precision issues
    order_count INTEGER NOT NULL,
    volume INTEGER NOT NULL,
    UNIQUE(region_id, type_id, date_)
    ON CONFLICT REPLACE
) STRICT;