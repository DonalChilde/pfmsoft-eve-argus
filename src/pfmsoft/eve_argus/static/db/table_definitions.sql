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
    published BOOLEAN --boolean represented as integer (0 or 1)
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