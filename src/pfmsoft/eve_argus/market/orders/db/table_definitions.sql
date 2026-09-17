-- Table definitions for market orders

PRAGMA foreign_keys = ON;

-- This table is used to store region_id and response metadata for market orders
CREATE TABLE IF NOT EXISTS order_response (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    region_id INT,
    received_at TEXT NOT NULL,
    expires_at TEXT
) STRICT;

-- This table is used to store individual market orders linked to a response
CREATE TABLE IF NOT EXISTS market_orders (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    order_response_id INTEGER NOT NULL REFERENCES order_response(ID),
    duration INTEGER NOT NULL,
    is_buy_order BOOLEAN NOT NULL,
    issued TEXT NOT NULL,
    location_id INTEGER NOT NULL,
    min_volume INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    price INTEGER NOT NULL, -- Stored as an integer to avoid floating point precision issues
    range_ TEXT NOT NULL,
    system_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    volume_remain INTEGER NOT NULL,
    volume_total INTEGER NOT NULL
) STRICT;

