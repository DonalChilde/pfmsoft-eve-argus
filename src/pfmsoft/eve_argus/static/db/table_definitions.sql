-- Table definitions for the Argus static database.

PRAGMA foreign_keys = ON;

-- ref esd_datasets.py TypesRecord
CREATE TABLE IF NOT EXISTS types (
    type_id INTEGER PRIMARY KEY,
    base_price FLOAT,
    capacity FLOAT,
    description TEXT,
    faction_id INTEGER,
    graphic_id INTEGER,
    group_id INTEGER NOT NULL,
    icon_id INTEGER,
    market_group_id INTEGER,
    mass FLOAT,
    meta_group_id INTEGER,
    meta_level INTEGER,
    name TEXT NOT NULL,
    packaged_volume FLOAT,
    portion_size INTEGER NOT NULL,
    published INTEGER NOT NULL,
    race_id INTEGER,
    radius FLOAT,
    ship_tree_group_id INTEGER,
    sound_id INTEGER,
    tech_level INTEGER,
    variation_parent_type_id INTEGER,
    volume FLOAT
) STRICT;

CREATE TABLE IF NOT EXISTS meta_groups (
    meta_group_id INTEGER PRIMARY KEY,
    color TEXT, -- a json string representing the color as a dict.
    description TEXT,
    icon_id INTEGER,
    icon_suffix TEXT,
    name TEXT NOT NULL
) STRICT;