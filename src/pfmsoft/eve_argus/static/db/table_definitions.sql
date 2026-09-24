-- Table definitions for the Argus static database.

PRAGMA foreign_keys = ON;

-- ref esd_datasets.py TypesRecord
CREATE TABLE IF NOT EXISTS types (
    type_id INTEGER PRIMARY KEY,
    base_price REAL,
    capacity REAL,
    description TEXT,
    faction_id INTEGER,
    graphic_id INTEGER,
    group_id INTEGER NOT NULL,
    icon_id INTEGER,
    market_group_id INTEGER,
    mass REAL,
    meta_group_id INTEGER,
    meta_level INTEGER,
    name TEXT NOT NULL,
    packaged_volume REAL,
    portion_size INTEGER NOT NULL,
    published INTEGER NOT NULL, --boolean represented as integer (0 or 1)
    race_id INTEGER,
    radius REAL,
    ship_tree_group_id INTEGER,
    sound_id INTEGER,
    tech_level INTEGER,
    variation_parent_type_id INTEGER,
    volume REAL
) STRICT;

-- meta_groups
CREATE TABLE IF NOT EXISTS meta_groups (
    meta_group_id INTEGER PRIMARY KEY,
    color TEXT, -- a json string representing the color as a dict.
    description TEXT,
    icon_id INTEGER,
    icon_suffix TEXT,
    name TEXT NOT NULL
) STRICT;

-- Table definitions for type materials and their components.
CREATE TABLE IF NOT EXISTS type_materials (
    type_id INTEGER PRIMARY KEY,
    FOREIGN KEY (type_id) REFERENCES types(type_id)
) STRICT;

CREATE TABLE IF NOT EXISTS type_material_components (
    type_id INTEGER NOT NULL,
    material_type_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (type_id, material_type_id),
    FOREIGN KEY (type_id) REFERENCES type_materials(type_id) ON DELETE CASCADE,
    FOREIGN KEY (material_type_id) REFERENCES types(type_id)
) STRICT;

CREATE TABLE IF NOT EXISTS type_material_randomized_components (
    type_id INTEGER NOT NULL,
    material_type_id INTEGER NOT NULL,
    quantity_min INTEGER NOT NULL CHECK (quantity_min >= 0),
    quantity_max INTEGER NOT NULL CHECK (quantity_max >= quantity_min),
    PRIMARY KEY (type_id, material_type_id),
    FOREIGN KEY (type_id) REFERENCES type_materials(type_id) ON DELETE CASCADE,
    FOREIGN KEY (material_type_id) REFERENCES types(type_id)
) STRICT;

-- Table definitions for blueprints and their activities.
CREATE TABLE IF NOT EXISTS blueprints (
    blueprint_type_id INTEGER PRIMARY KEY,
    max_production_limit INTEGER CHECK (max_production_limit >= 0),
    FOREIGN KEY (blueprint_type_id) REFERENCES types(type_id)
) STRICT;

CREATE TABLE IF NOT EXISTS blueprint_activities (
    blueprint_type_id INTEGER NOT NULL,
    activity TEXT NOT NULL CHECK (
        activity IN (
            'copying',
            'invention',
            'manufacturing',
            'reaction',
            'research_material',
            'research_time'
        )
    ),
    time INTEGER NOT NULL CHECK (time >= 0),
    PRIMARY KEY (blueprint_type_id, activity),
    FOREIGN KEY (blueprint_type_id)
        REFERENCES blueprints(blueprint_type_id) ON DELETE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS blueprint_activity_materials (
    blueprint_type_id INTEGER NOT NULL,
    activity TEXT NOT NULL,
    material_type_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (blueprint_type_id, activity, material_type_id),
    FOREIGN KEY (blueprint_type_id, activity)
        REFERENCES blueprint_activities(blueprint_type_id, activity)
        ON DELETE CASCADE,
    FOREIGN KEY (material_type_id) REFERENCES types(type_id)
) STRICT;

CREATE TABLE IF NOT EXISTS blueprint_activity_skills (
    blueprint_type_id INTEGER NOT NULL,
    activity TEXT NOT NULL,
    skill_type_id INTEGER NOT NULL,
    level INTEGER NOT NULL CHECK (level >= 0),
    PRIMARY KEY (blueprint_type_id, activity, skill_type_id),
    FOREIGN KEY (blueprint_type_id, activity)
        REFERENCES blueprint_activities(blueprint_type_id, activity)
        ON DELETE CASCADE,
    FOREIGN KEY (skill_type_id) REFERENCES types(type_id)
) STRICT;

CREATE TABLE IF NOT EXISTS blueprint_activity_products (
    blueprint_type_id INTEGER NOT NULL,
    activity TEXT NOT NULL,
    product_type_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    probability REAL CHECK (probability >= 0.0 AND probability <= 1.0),
    PRIMARY KEY (blueprint_type_id, activity, product_type_id),
    FOREIGN KEY (blueprint_type_id, activity)
        REFERENCES blueprint_activities(blueprint_type_id, activity)
        ON DELETE CASCADE,
    FOREIGN KEY (product_type_id) REFERENCES types(type_id)
) STRICT;

-- Categories
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY,
    icon_id INTEGER,
    name TEXT,
    published INTEGER NOT NULL --boolean represented as integer (0 or 1)
) STRICT;

-- Groups
CREATE TABLE IF NOT EXISTS groups (
    group_id INTEGER PRIMARY KEY,
    anchorable INTEGER NOT NULL, --boolean represented as integer (0 or 1)
    anchored INTEGER NOT NULL, --boolean represented as integer (0 or 1)
    category_id INTEGER NOT NULL,
    fittable_non_singleton INTEGER NOT NULL, --boolean represented as integer (0 or 1)
    icon_id INTEGER,
    name TEXT,
    published INTEGER, --boolean represented as integer (0 or 1)
    use_base_price INTEGER NOT NULL, --boolean represented as integer (0 or 1)
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
) STRICT;

-- Market Groups
CREATE TABLE IF NOT EXISTS market_groups (
    market_group_id INTEGER PRIMARY KEY,
    description TEXT,
    has_types INTEGER NOT NULL, --boolean represented as integer (0 or 1)
    icon_id INTEGER,
    name TEXT NOT NULL,
    parent_group_id INTEGER,
    int_path TEXT NOT NULL, -- a string representing the path of ancestor market group IDs as a JSON array
    str_path TEXT NOT NULL, -- a string representing the path of ancestor market group names as a JSON array
    types TEXT, -- a string representing the IDs of types in this market group as a JSON array, NULL if none
    FOREIGN KEY (parent_group_id) REFERENCES market_groups(market_group_id)
) STRICT;

-- Industry Activities
CREATE TABLE IF NOT EXISTS industry_activities (
    activity_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL
) STRICT;

-- Map Regions
CREATE TABLE IF NOT EXISTS map_regions (
    region_id INTEGER PRIMARY KEY,
    description TEXT,
    faction_id INTEGER,
    name TEXT NOT NULL,
    nebula_id INTEGER NOT NULL,
    position_x REAL NOT NULL,
    position_y REAL NOT NULL,
    position_z REAL NOT NULL,
    wormhole_class_id INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS map_regions_constellations (
    region_id INTEGER NOT NULL,
    constellation_id INTEGER NOT NULL,
    PRIMARY KEY (region_id, constellation_id),
    FOREIGN KEY (region_id) REFERENCES map_regions(region_id) ON DELETE CASCADE
) STRICT;

-- Map Constellations
CREATE TABLE IF NOT EXISTS map_constellations (
    constellation_id INTEGER PRIMARY KEY,
    faction_id INTEGER,
    name TEXT NOT NULL,
    position_x REAL NOT NULL,
    position_y REAL NOT NULL,
    position_z REAL NOT NULL,
    region_id INTEGER NOT NULL,
    wormhole_class_id INTEGER,
    FOREIGN KEY (region_id) REFERENCES map_regions(region_id)
) STRICT;

CREATE TABLE IF NOT EXISTS map_constellations_solar_systems (
    constellation_id INTEGER NOT NULL,
    solar_system_id INTEGER NOT NULL,
    PRIMARY KEY (constellation_id, solar_system_id),
    FOREIGN KEY (constellation_id)
        REFERENCES map_constellations(constellation_id) ON DELETE CASCADE
) STRICT;

-- Map Solar Systems
CREATE TABLE IF NOT EXISTS map_solar_systems (
    solar_system_id INTEGER PRIMARY KEY,
    border INTEGER, --boolean represented as integer (0 or 1)
    constellation_id INTEGER NOT NULL,
    corridor INTEGER, --boolean represented as integer (0 or 1)
    faction_id INTEGER,
    fringe INTEGER, --boolean represented as integer (0 or 1)
    hub INTEGER, --boolean represented as integer (0 or 1)
    international INTEGER, --boolean represented as integer (0 or 1)
    luminosity REAL,
    name TEXT NOT NULL,
    position_x REAL NOT NULL,
    position_y REAL NOT NULL,
    position_z REAL NOT NULL,
    position2d_x REAL,
    position2d_y REAL,
    radius REAL NOT NULL,
    region_id INTEGER NOT NULL,
    regional INTEGER, --boolean represented as integer (0 or 1)
    security_class TEXT,
    security_status REAL NOT NULL,
    star_id INTEGER,
    visual_effect TEXT,
    wormhole_class_id INTEGER,
    FOREIGN KEY (constellation_id) REFERENCES map_constellations(constellation_id),
    FOREIGN KEY (region_id) REFERENCES map_regions(region_id)
) STRICT;

CREATE TABLE IF NOT EXISTS map_solar_systems_disallowed_anchor_categories (
    solar_system_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY (solar_system_id, category_id),
    FOREIGN KEY (solar_system_id)
        REFERENCES map_solar_systems(solar_system_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
) STRICT;

CREATE TABLE IF NOT EXISTS map_solar_systems_disallowed_anchor_groups (
    solar_system_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    PRIMARY KEY (solar_system_id, group_id),
    FOREIGN KEY (solar_system_id)
        REFERENCES map_solar_systems(solar_system_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES groups(group_id)
) STRICT;

CREATE TABLE IF NOT EXISTS map_solar_systems_planets (
    solar_system_id INTEGER NOT NULL,
    planet_id INTEGER NOT NULL,
    PRIMARY KEY (solar_system_id, planet_id),
    FOREIGN KEY (solar_system_id)
        REFERENCES map_solar_systems(solar_system_id) ON DELETE CASCADE
) STRICT;

CREATE TABLE IF NOT EXISTS map_solar_systems_stargates (
    solar_system_id INTEGER NOT NULL,
    stargate_id INTEGER NOT NULL,
    PRIMARY KEY (solar_system_id, stargate_id),
    FOREIGN KEY (solar_system_id)
        REFERENCES map_solar_systems(solar_system_id) ON DELETE CASCADE
) STRICT;