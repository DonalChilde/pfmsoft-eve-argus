"""Synthetic fixtures and explicit read-only Argus snapshot adapters."""

import sqlite3
from contextlib import ExitStack
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from industry_proof import (
    Blueprint,
    Inputs,
    Invention,
    Item,
    Market,
    Material,
    Original,
    Planner,
    Source,
    Unavailable,
)

from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.dynamic.models import ResponseMetadata
from pfmsoft.eve_argus.market_history import read as history_read
from pfmsoft.eve_argus.market_history.history_summary import (
    calculate_history_summary,
    date_range_days,
)
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS
from pfmsoft.eve_argus.static import read as static_read

D = Decimal


def demo_inputs() -> Inputs:
    """Provide explicitly fictional recipes and prices, not real EVE quotes."""
    items = {
        1: Item(type_id=1, name="Synthetic mineral"),
        2: Item(type_id=2, name="Synthetic reaction product"),
        3: Item(type_id=3, name="Synthetic datacore"),
        10: Item(type_id=10, name="Synthetic component", meta_level=0),
        100: Item(type_id=100, name="Synthetic T1 assembly", meta_level=0),
        200: Item(type_id=200, name="Synthetic T2 module", family="t2", meta_level=5),
        300: Item(
            type_id=300, name="Synthetic T2 rig", family="t2-ship-rig", meta_level=5
        ),
    }
    bps: dict[int, Blueprint] = {}
    for product, blueprint, materials in (
        (10, 1010, (Material(type_id=1, quantity=3), Material(type_id=2, quantity=1))),
        (
            100,
            1100,
            (Material(type_id=10, quantity=2), Material(type_id=1, quantity=4)),
        ),
        (
            200,
            1200,
            (Material(type_id=10, quantity=2), Material(type_id=100, quantity=1)),
        ),
        (
            300,
            1300,
            (Material(type_id=10, quantity=7), Material(type_id=1, quantity=11)),
        ),
    ):
        items[blueprint] = Item(
            type_id=blueprint, name=f"{items[product].name} Blueprint"
        )
        bps[blueprint] = Blueprint(
            blueprint_id=blueprint,
            product_id=product,
            output=1,
            max_runs=100,
            materials=materials,
            manufacturing_seconds=600,
            copying_seconds=60 if product in (10, 100) else None,
            science_skills=2 if product in (200, 300) else 0,
        )
    markets: dict[tuple[int, int], Market] = {}
    for hub in MARKET_HUBS:
        for type_id in (100, 200, 300):
            markets[hub.station_id, type_id] = Market(
                station_id=hub.station_id,
                type_id=type_id,
                buy=D(800),
                sell=D(1000),
                buy_depth=1000,
                sell_depth=2000,
                history_price=D(900),
                daily_sales=D(15),
                history_start="2026-10-25",
                history_end="2026-11-03",
                days_present=10,
            )
    return Inputs(
        items=items,
        blueprints=bps,
        inventions=tuple(
            Invention(
                source_blueprint_id=1100,
                target_blueprint_id=target,
                base_probability=D("0.34"),
                licensed_runs=runs,
                seconds=1000,
                materials=(Material(type_id=3, quantity=2),),
            )
            for target, runs in ((1200, 10), (1300, 1))
        ),
        originals=(
            Original(blueprint_id=1100, item_id=1000, me=10, te=20),
            Original(blueprint_id=1010, item_id=1001, me=10, te=20),
        ),
        reaction_products={2},
        adjusted_prices={1: D(2), 2: D(5), 3: D(10), 10: D(20), 100: D(50)},
        input_prices={1: D(3), 2: D(6), 3: D(20), 10: D(40), 100: D(100)},
        indices={
            "manufacturing": D("0.03"),
            "copying": D("0.04"),
            "invention": D("0.02"),
        },
        markets=markets,
        sources=[
            Source(
                label="Synthetic fixture",
                reference="demo-v1",
                received_at="2026-11-04T00:00:00Z",
            )
        ],
        scope="SYNTHETIC DEMO — fictional recipes, not EVE quotes",
        warnings=[
            "Station service availability is not verified; this is a cost estimate."
        ],
    )


def source(metadata: ResponseMetadata, *, label: str) -> Source:
    """Preserve response-ID linkage and Argus-expiry precedence."""
    return Source(
        label=label,
        reference=str(metadata.response_metadata_id),
        received_at=metadata.received_at,
        expires_at=metadata.expires_at,
        argus_expires_at=metadata.argus_expires_at,
    )


def history_market(
    connection: sqlite3.Connection,
    *,
    region_id: int,
    station_id: int,
    type_id: int,
    sources: list[Source],
    before: str,
    history_stale_days: int = 7,
) -> Market:
    """Anchor ten calendar days to this region/type's latest completed record."""
    if history_stale_days < 0:
        raise ValueError("History stale days must be nonnegative.")
    row = connection.execute(
        "SELECT MAX(date_) FROM market_history "
        "WHERE region_id = ? AND type_id = ? AND date_ < ?",
        (region_id, type_id, before),
    ).fetchone()
    newest = row[0] if row else None
    if newest is None:
        return Market(station_id=station_id, type_id=type_id)
    dates = date_range_days(newest, 10)
    records = history_read.market_history_date_range(
        connection,
        region_id=region_id,
        type_id=type_id,
        start=max(dates),
        end=min(dates),
    )
    summary = calculate_history_summary(records, dates)
    for received, expires, argus in sorted(
        {(r.received_at, r.expires_at, r.argus_expires_at) for r in records},
        key=lambda metadata: metadata[0],
    ):
        sources.append(
            Source(
                label=f"History region {region_id}, type {type_id}",
                reference=f"{min(dates)}..{max(dates)}; receipt {received}",
                received_at=received,
                expires_at=expires,
                argus_expires_at=argus,
                history_stale_days=history_stale_days,
            )
        )
    return Market(
        station_id=station_id,
        type_id=type_id,
        history_price=summary.average if sum(r.volume for r in records) > 0 else None,
        daily_sales=summary.volume,
        history_start=min(dates),
        history_end=max(dates),
        days_present=10 - summary.missing,
    )


def select_sample(data: Inputs) -> tuple[int, ...]:
    """Select bounded representative owned routes, flagging absent coverage."""
    planner = Planner(data)
    eligible: dict[str, list[int]] = {
        "ordinary": [],
        "t2": [],
        "t2-ship-rig": [],
        "chain": [],
    }
    for type_id in sorted(planner.routes):
        item = data.items[type_id]
        if item.family == "unsupported" or type_id in data.reaction_products:
            continue
        try:
            planner.blueprint_access(planner.route(type_id))
        except Unavailable:
            continue
        eligible[item.family].append(type_id)
        try:
            graph = planner.graph(type_id, "make-all-inputs")
        except Unavailable:
            continue
        if len(graph) > 1:
            eligible["chain"].append(type_id)
    selected: set[int] = set()
    for family, ids in eligible.items():
        if ids:
            selected.add(ids[0])
        else:
            data.warnings.append(
                f"No eligible representative for sample category: {family}."
            )
    if not selected:
        raise ValueError("No supported owned-BPO manufacturing/invention routes found.")
    return tuple(sorted(selected))


def select_bpo_products(
    data: Inputs,
    *,
    published_blueprint_ids: set[int],
    owned: bool,
    marketable_source_ids: set[int] | None = None,
    me: int = 10,
    te: int = 20,
) -> tuple[int, ...]:
    """Select published source BPO products and every supported invention result.

    Not-owned selection adds explicitly hypothetical access to missing published
    BPOs, including component sources, without changing actual owned research.
    Manufactured outputs must have meta level 0 or 5 in not-owned selection,
    including invention results and hypothetical component BPOs.
    """
    if not 0 <= me <= 10 or not 0 <= te <= 20:
        raise ValueError("Unowned BPO ME must be 0-10 and TE must be 0-20.")
    owned_ids = {o.blueprint_id for o in data.originals}
    invented_ids = {route.target_blueprint_id for route in data.inventions}
    sources = {
        bp.blueprint_id: bp
        for bp in data.blueprints.values()
        if bp.blueprint_id in published_blueprint_ids
        and (
            owned
            or marketable_source_ids is None
            or bp.blueprint_id in marketable_source_ids
        )
        and bp.blueprint_id not in invented_ids
        and bp.copying_seconds is not None
        and data.items[bp.product_id].family == "ordinary"
        and (owned or data.items[bp.product_id].meta_level in (0, 5))
        and bp.product_id not in data.reaction_products
    }
    if not owned:
        for bp_id, bp in tuple(sources.items()):
            if bp.copying_seconds is not None and bp.copying_seconds <= 0:
                item = data.items.get(bp_id)
                name = item.name if item is not None else "UNKNOWN"
                data.warnings.append(
                    f"Excluded hypothetical BPO {name} ({bp_id}): "
                    f"invalid copying duration {bp.copying_seconds}; "
                    "a copying activity with positive duration is required."
                )
                del sources[bp_id]
    selected_sources = {bp_id for bp_id in sources if (bp_id in owned_ids) == owned}
    products = {sources[bp_id].product_id for bp_id in selected_sources}
    for route in data.inventions:
        target = data.blueprints.get(route.target_blueprint_id)
        if (
            route.source_blueprint_id in selected_sources
            and target is not None
            and target.blueprint_id in published_blueprint_ids
            and data.items[target.product_id].family in ("t2", "t2-ship-rig")
            and (owned or data.items[target.product_id].meta_level in (0, 5))
            and target.product_id not in data.reaction_products
        ):
            products.add(target.product_id)
    if not products:
        raise ValueError(
            f"No supported published {'owned' if owned else 'not-owned'} BPOs found."
        )
    if not owned:
        hypothetical = tuple(
            Original(blueprint_id=bp_id, item_id=None, me=me, te=te)
            for bp_id in sorted(sources.keys() - owned_ids)
        )
        data.originals += hypothetical
        data.warnings.append(
            f"Not-owned selection: hypothetical access to {len(hypothetical)} "
            f"unowned published BPO types at ME{me}/TE{te}, including component "
            "BPOs. Actual owned ME/TE is preserved. BPO acquisition and research "
            "costs/time are excluded; invented BPCs remain ME2/TE4."
        )
    return tuple(sorted(products))


@dataclass(slots=True, kw_only=True, frozen=True)
class DatabasePaths:
    """Explicit source paths; adapters never initialize application settings."""

    static: Path
    dynamic: Path
    history: Path


def read_inputs(
    paths: DatabasePaths,
    *,
    corporation_id: int,
    product_ids: tuple[int, ...] = (),
    selection: Literal["sample", "owned", "not-owned"] = "sample",
    me: int = 10,
    te: int = 20,
    history_stale_days: int = 7,
) -> tuple[Inputs, tuple[int, ...]]:
    """Read only selected snapshots; never fetch, migrate, or initialize schemas."""
    if corporation_id < 1:
        raise ValueError("Corporation ID must be positive.")
    if history_stale_days < 0:
        raise ValueError("History stale days must be nonnegative.")
    if selection not in ("sample", "owned", "not-owned"):
        raise ValueError("Unknown blueprint selection.")
    if product_ids and selection != "sample":
        raise ValueError("Product IDs cannot be combined with a BPO selection.")
    if any(t < 1 for t in product_ids):
        raise ValueError("Product IDs must be positive.")
    if not 0 <= me <= 10 or not 0 <= te <= 20:
        raise ValueError("Unowned BPO ME must be 0-10 and TE must be 0-20.")
    with ExitStack() as stack:
        connections: list[sqlite3.Connection] = []
        for path in (paths.static, paths.dynamic, paths.history):
            if not path.is_file():
                raise ValueError(f"Database does not exist: {path}")
            connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            stack.callback(connection.close)
            connection.execute("PRAGMA query_only = ON")
            connections.append(connection)
        static, dynamic, history = connections
        types = static_read.types(static, only_published=False)
        groups = static_read.groups(static)
        categories = static_read.categories(static, only_published=False)
        market_groups = static_read.market_groups(static)
        raw_bps = static_read.blueprints(static)
        systems = static_read.map_solar_systems(static)
        static_metadata = static_read.sde_metadata(static)
        osmeden = [s for s in systems.values() if s.name == "Osmeden"]
        if len(osmeden) != 1 or osmeden[0].security_status < 0.45:
            raise ValueError(
                "Cannot resolve Osmeden as a high-sec system in static data."
            )
        price_responses = dynamic_read.markets_prices_responses(dynamic)
        index_responses = dynamic_read.system_cost_indices_responses(dynamic)
        blueprint_responses = dynamic_read.corporation_blueprints_responses(
            dynamic, corporation_id
        )
        for label, responses, hint in (
            ("adjusted prices", price_responses, "markets-prices"),
            ("industry indices", index_responses, "industry-systems"),
            (
                "corporation BPO inventory",
                blueprint_responses,
                "corporation-blueprints",
            ),
        ):
            if not responses:
                raise ValueError(f"Missing {label}; run eve-argus fetch {hint}.")
        prices = dynamic_read.markets_prices(
            dynamic, price_responses[0].response_metadata_id
        )
        indices = dynamic_read.system_cost_indices(
            dynamic, index_responses[0].response_metadata_id
        )
        owned = dynamic_read.corporation_blueprints(
            dynamic, blueprint_responses[0].response_metadata_id
        )
        system_indices = indices.records.get(osmeden[0].solar_system_id)
        if system_indices is None:
            raise ValueError(
                "Osmeden indices absent; run eve-argus fetch industry-systems."
            )
        items: dict[int, Item] = {}
        for t in types.values():
            path = market_groups.get(t.market_group_id) if t.market_group_id else None
            is_rig = path is not None and any(
                p.casefold() == "rigs" or p.casefold().endswith(" rigs")
                for p in path.str_path
            )
            family = "ordinary"
            if t.tech_level == 3 or t.meta_group_id == 14:
                family = "unsupported"
            elif t.tech_level == 2 or t.meta_group_id == 2:
                family = "t2-ship-rig" if t.category_id == 6 or is_rig else "t2"
            volume = t.packaged_volume if t.packaged_volume is not None else t.volume
            items[t.type_id] = Item(
                type_id=t.type_id,
                name=t.name,
                portion_size=t.portion_size,
                family=family,
                meta_level=t.meta_level,
                market_path=path.str_path_str() if path is not None else None,
                volume=None if volume is None else D(str(volume)),
                group_id=t.group_id,
                category_id=t.category_id,
                category_name=(
                    categories[t.category_id].name or f"UNKNOWN {t.category_id}"
                    if t.category_id in categories
                    else f"UNKNOWN {t.category_id}"
                ),
                group_name=(
                    groups[t.group_id].name or f"UNKNOWN {t.group_id}"
                    if t.group_id in groups
                    else f"UNKNOWN {t.group_id}"
                ),
            )
        bps: dict[int, Blueprint] = {}
        inventions: list[Invention] = []
        reactions: set[int] = set()
        for raw in raw_bps.values():
            manufacturing = raw.activities.manufacturing
            if manufacturing:
                products = manufacturing.products or ()
                if len(products) != 1:
                    continue
                if raw.max_production_limit is None:
                    identity = items.get(raw.blueprint_type_id)
                    name = identity.name if identity is not None else "UNKNOWN"
                    raise ValueError(
                        f"Missing copy limit for {name} ({raw.blueprint_type_id})."
                    )
                science_skills = sum(
                    groups[types[s.type_id].group_id].name == "Science"
                    and types[s.type_id].name != "Science"
                    for s in (manufacturing.skills or ())
                )
                bps[raw.blueprint_type_id] = Blueprint(
                    blueprint_id=raw.blueprint_type_id,
                    product_id=products[0].type_id,
                    output=products[0].quantity,
                    max_runs=raw.max_production_limit,
                    materials=tuple(
                        Material(type_id=m.type_id, quantity=m.quantity)
                        for m in (manufacturing.materials or ())
                    ),
                    manufacturing_seconds=manufacturing.time,
                    copying_seconds=None
                    if raw.activities.copying is None
                    else raw.activities.copying.time,
                    science_skills=science_skills,
                    copying_materials=tuple(
                        Material(type_id=m.type_id, quantity=m.quantity)
                        for m in (
                            raw.activities.copying.materials or ()
                            if raw.activities.copying
                            else ()
                        )
                    ),
                )
            if raw.activities.reaction:
                reactions.update(
                    p.type_id for p in (raw.activities.reaction.products or ())
                )
            if raw.activities.invention:
                for p in raw.activities.invention.products or ():
                    if p.probability is None:
                        continue
                    inventions.append(
                        Invention(
                            source_blueprint_id=raw.blueprint_type_id,
                            target_blueprint_id=p.type_id,
                            base_probability=D(str(p.probability)),
                            licensed_runs=p.quantity,
                            seconds=raw.activities.invention.time,
                            materials=tuple(
                                Material(type_id=m.type_id, quantity=m.quantity)
                                for m in (raw.activities.invention.materials or ())
                            ),
                        )
                    )
        data = Inputs(
            items=items,
            blueprints=bps,
            inventions=tuple(inventions),
            originals=tuple(
                Original(
                    blueprint_id=r.type_id,
                    item_id=r.item_id,
                    me=r.material_efficiency,
                    te=r.time_efficiency,
                )
                for r in owned.records.values()
                if r.quantity == -1 or r.quantity > 0
            ),
            reaction_products=reactions,
            adjusted_prices={
                t: p.adjusted_price
                for t, p in prices.records.items()
                if p.adjusted_price is not None
            },
            input_prices={},
            indices={
                activity: value
                for activity in ("manufacturing", "copying", "invention")
                if (value := getattr(system_indices, activity)) is not None
            },
            markets={},
            scope=f"Corporation {corporation_id}; stored snapshots",
            sources=[
                source(prices, label="CCP adjusted prices"),
                source(
                    indices, label=f"Osmeden indices ({osmeden[0].solar_system_id})"
                ),
                source(owned, label=f"Corporation {corporation_id} blueprints"),
                Source(
                    label="Static database",
                    reference=f"build {static_metadata.build_number}; {paths.static.resolve()}",
                    received_at=static_metadata.release_date,
                ),
            ],
            warnings=[
                f"History is stale only when its snapshot receipt is older than "
                f"{history_stale_days} days; history expiry timestamps do not "
                "override this threshold.",
                "Station service availability is unverified; this is not an executable schedule.",
                "Whole-ISK client fee rounding and material rounding retain reference caveats.",
            ],
        )
        if product_ids:
            selected = tuple(sorted(set(product_ids)))
        elif selection == "sample":
            selected = select_sample(data)
        else:
            selected = select_bpo_products(
                data,
                published_blueprint_ids={
                    bp.blueprint_id
                    for bp in bps.values()
                    if types[bp.blueprint_id].published
                    and types[bp.product_id].published
                },
                owned=selection == "owned",
                marketable_source_ids={
                    bp.blueprint_id
                    for bp in bps.values()
                    if types[bp.blueprint_id].market_group_id is not None
                    and types[bp.product_id].market_group_id is not None
                },
                me=me,
                te=te,
            )
        data.scope += (
            f"; selection: {'explicit products' if product_ids else selection}"
        )
        if any(t not in items for t in selected):
            raise ValueError("Requested product type not found in static data.")
        # Bound price lookups to the selected dependency closure, including source EIV.
        needed: set[int] = set()
        seen: set[int] = set()

        def visit(t: int) -> None:
            if t in seen:
                return
            seen.add(t)
            for bp in bps.values():
                if bp.product_id != t:
                    continue
                needed.update(m.type_id for m in bp.copying_materials)
                for m in bp.materials:
                    needed.add(m.type_id)
                    visit(m.type_id)
                for route in inventions:
                    if route.target_blueprint_id == bp.blueprint_id:
                        needed.update(m.type_id for m in route.materials)
                        source_bp = bps.get(route.source_blueprint_id)
                        if source_bp:
                            visit(source_bp.product_id)

        for t in selected:
            visit(t)
        for hub in MARKET_HUBS:
            responses = dynamic_read.market_orders_responses(dynamic, hub.region_id)
            response = responses[0] if responses else None
            if response is None:
                data.warnings.append(
                    f"Missing {hub.system_name} orders; run eve-argus fetch market-orders."
                )
            else:
                data.sources.append(
                    source(response, label=f"{hub.system_name} station orders")
                )
            for t in sorted(
                set(selected) | (needed if hub.system_name == "Jita" else set())
            ):
                buy, sell = (
                    (None, None)
                    if response is None
                    else dynamic_read.calculate_market_order_summary(
                        dynamic,
                        response.response_metadata_id,
                        type_id=t,
                        location_id=hub.station_id,
                    )
                )
                if hub.system_name == "Jita" and sell is not None:
                    data.input_prices[t] = sell.five_price
                if t not in selected:
                    continue
                market = history_market(
                    history,
                    region_id=hub.region_id,
                    station_id=hub.station_id,
                    type_id=t,
                    sources=data.sources,
                    before=datetime.now(UTC).date().isoformat(),
                    history_stale_days=history_stale_days,
                )
                data.markets[hub.station_id, t] = replace(
                    market,
                    buy=None if buy is None else buy.five_price,
                    sell=None if sell is None else sell.five_price,
                    buy_depth=None if buy is None else buy.five_items,
                    sell_depth=None if sell is None else sell.five_items,
                )
        return data, tuple(selected)
