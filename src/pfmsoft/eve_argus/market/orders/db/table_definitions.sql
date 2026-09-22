-- Table definitions for market orders

PRAGMA foreign_keys = ON;

-- This table is used to store region_id and response metadata for market orders
CREATE TABLE IF NOT EXISTS order_response (
    region_id INT PRIMARY KEY,
    received_at TEXT NOT NULL,
    expires_at TEXT
) STRICT;

-- This table is used to store individual market orders linked to a response
CREATE TABLE IF NOT EXISTS market_orders (
    ID INTEGER PRIMARY KEY AUTOINCREMENT,
    region_id INTEGER NOT NULL REFERENCES order_response(region_id),
    duration INTEGER NOT NULL,
    is_buy_order INTEGER NOT NULL,
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

CREATE INDEX IF NOT EXISTS idx_market_orders_region_id ON market_orders(region_id);


-- This table is used to store summarized market order data for a specific region, type, solar system, and location combination
CREATE TABLE IF NOT EXISTS order_summaries (
    region_id INTEGER NOT NULL REFERENCES order_response(region_id),
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
    PRIMARY KEY (region_id, type_id, system_id, location_id)
) STRICT;