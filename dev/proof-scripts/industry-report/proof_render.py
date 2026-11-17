"""Render the canonical proof result to comparison CSV and detailed companions."""

import csv
import io
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path

from industry_proof import Outcome, Plan, Report, known_sum
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from pfmsoft.eve_argus.helpers.markdown import format_markdown, markdown_cell
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS


def number(value: object) -> str:
    """Display unknowns explicitly; retain full precision in the CSV instead."""
    if value is None:
        return "Unavailable"
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    return str(value)


def item_name(report: Report, type_id: int) -> str:
    """Resolve static identity, explicitly identifying missing names."""
    item = report.data.items.get(type_id)
    return f"UNKNOWN {type_id}" if item is None else item.name


def render_csv(report: Report) -> str:
    """Export one row per product/strategy with fixed major-hub column groups."""
    rows: list[dict[str, object]] = []
    for plan in report.plans:
        item = report.data.items[plan.type_id]
        bp = report.data.blueprints[plan.nodes[0].blueprint_id] if plan.nodes else None
        row: dict[str, object] = {
            "type_id": plan.type_id,
            "name": item.name,
            "production_strategy": plan.strategy,
            "profile_id": "osmeden-npc-omega-skills5",
            "portion_size": item.portion_size,
            "output_units_per_run": None if bp is None else bp.output,
            "reference_manufacturing_runs": plan.reference_runs,
            "requested_units": None if bp is None else bp.output * plan.reference_runs,
            "produced_units": plan.produced or None,
            "surplus_units": None
            if bp is None or not plan.produced
            else plan.produced - bp.output * plan.reference_runs,
            "allocated_cost": plan.total,
            "unit_cost": plan.unit_cost,
            "status": plan.status,
            "detail_anchor": plan.anchor,
            "sales_tax_rate": report.sales_tax_rate,
            "broker_fee_rate": report.broker_fee_rate,
            "invention_cost_basis": "ceil(1/p) attempts per required BPC",
        }
        for hub in MARKET_HUBS:
            prefix = hub.system_name.casefold()
            market = report.data.markets.get((hub.station_id, plan.type_id))
            row.update(
                {
                    f"{prefix}_region_id": hub.region_id,
                    f"{prefix}_station_id": hub.station_id,
                    f"{prefix}_avg_daily_sales": None
                    if market is None
                    else market.daily_sales,
                    f"{prefix}_history_start": None
                    if market is None
                    else market.history_start,
                    f"{prefix}_history_end": None
                    if market is None
                    else market.history_end,
                    f"{prefix}_history_days_present": None
                    if market is None
                    else market.days_present,
                    f"{prefix}_history_days_requested": 10,
                }
            )
            for outcome in plan.outcomes:
                if outcome.station_id != hub.station_id:
                    continue
                p = f"{prefix}_{outcome.basis}"
                row.update(
                    {
                        f"{p}_sale_price": outcome.price,
                        f"{p}_net_proceeds_per_unit": outcome.net_per_unit,
                        f"{p}_profit_per_unit": outcome.profit_per_unit,
                        f"{p}_total_profit": outcome.total_profit,
                        f"{p}_return_pct": outcome.return_pct,
                        f"{p}_status": outcome.status,
                        f"{p}_five_percent_depth": outcome.depth,
                    }
                )
        rows.append(row)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


@dataclass(slots=True, kw_only=True, frozen=True)
class Table:
    """A presentation table shared by Markdown and autoescaped HTML."""

    headings: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    caption: str = ""
    cell_links: dict[tuple[int, int], str] = field(default_factory=dict)
    cell_anchors: dict[tuple[int, int], str] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True, frozen=True)
class Section:
    """Precomputed presentation content; templates contain no economic logic."""

    title: str
    anchor: str
    level: int = 2
    paragraphs: tuple[str, ...] = ()
    tables: tuple[Table, ...] = ()
    tree: str = ""
    raw_text: str = ""
    index_anchor: str = ""
    summary_anchor: str = ""
    category_id: int | None = None
    category_name: str = "Unknown category"


def table(
    headings: tuple[str, ...],
    rows: Iterable[Iterable[object]],
    *,
    caption: str = "",
    cell_links: dict[tuple[int, int], str] | None = None,
    cell_anchors: dict[tuple[int, int], str] | None = None,
) -> Table:
    """Normalize cells once without applying format-specific escaping."""
    return Table(
        headings=headings,
        rows=tuple(tuple(number(cell) for cell in row) for row in rows),
        caption=caption,
        cell_links=cell_links or {},
        cell_anchors=cell_anchors or {},
    )


def dependency_tree(report: Report, plan: Plan) -> str:
    """Show shared manufacturing nodes as references, not duplicate jobs."""
    nodes = {node.type_id: node for node in plan.nodes}
    shown: set[int] = set()
    lines: list[str] = []

    def walk(type_id: int, indent: str) -> None:
        name = item_name(report, type_id)
        name = name.replace("\n", " ").replace("\r", " ").replace("`", "'")
        if type_id not in nodes:
            reason = (
                " (reaction; buy only)"
                if type_id in report.data.reaction_products
                else ""
            )
            lines.append(f"{indent}BUY {name} [{type_id}]{reason}")
            return
        node = nodes[type_id]
        if type_id in shown:
            lines.append(f"{indent}REFERENCE {name} -> {', '.join(node.job_ids)}")
            return
        shown.add(type_id)
        lines.append(
            f"{indent}MAKE {name} [{type_id}]: need {node.required}, "
            f"produce {node.produced}; jobs {', '.join(node.job_ids)}"
        )
        lines.append(
            f"{indent}  BPC {item_name(report, node.blueprint_id)}: "
            f"{node.bpcs} copies, ME{node.me}/TE{node.te}; "
            + (
                "source BPO copying + invention"
                if node.probability
                else "source BPO copying"
            )
        )
        for material in node.materials:
            lines.append(f"{indent}  Required: {material.quantity} units")
            walk(material.type_id, indent + "    ")

    if plan.nodes:
        walk(plan.type_id, "")
    return "\n".join(lines)


SALES_HEADINGS = (
    "Hub",
    "Sale basis",
    "Price/unit",
    "Sales tax/batch",
    "Broker fee/batch",
    "Net/unit",
    "Profit/unit",
    "Profit/batch",
    "Return %",
    "5% depth",
    "Status",
)


def sales_row(outcome: Outcome) -> tuple[object, ...]:
    """Share sale scenario values between detail and opportunity tables."""
    hub = next(h for h in MARKET_HUBS if h.station_id == outcome.station_id)
    return (
        hub.system_name,
        outcome.basis,
        outcome.price,
        outcome.sales_tax,
        outcome.broker_fee,
        outcome.net_per_unit,
        outcome.profit_per_unit,
        outcome.total_profit,
        outcome.return_pct,
        outcome.depth,
        outcome.status,
    )


def profit_opportunities(report: Report) -> Section:
    """List history-average scenarios meeting the unrounded 20-percent threshold."""
    candidates = [
        (outcome.return_pct, plan, outcome)
        for plan in report.plans
        for outcome in plan.outcomes
        if outcome.basis == "history_average"
        and outcome.return_pct is not None
        and outcome.return_pct >= Decimal(20)
    ]
    candidates.sort(
        key=lambda row: (
            -row[0],
            report.data.items[row[1].type_id].name,
            row[1].type_id,
            row[1].strategy,
            row[2].station_id,
            row[2].basis,
        )
    )
    rows: list[tuple[object, ...]] = []
    for _, plan, outcome in candidates:
        market = report.data.markets.get((outcome.station_id, plan.type_id))
        sale = sales_row(outcome)
        rows.append(
            (
                item_name(report, plan.type_id),
                plan.strategy,
                sale[0],
                None if market is None else market.daily_sales,
                plan.unit_cost,
                sale[2],
                None if market is None else market.sell,
                None if market is None else market.sell_depth,
                *sale[3:9],
                "Sell 5% price below history average"
                if market is not None
                and market.sell is not None
                and outcome.price is not None
                and market.sell < outcome.price
                else "",
            )
        )
    return Section(
        title="Profit Opportunities",
        anchor="profit-opportunities",
        paragraphs=(
            "Scenarios with at least 20% return against history_average prices "
            "after sale fees, highest return first. "
            "Average traded units/day is regional, not hub-local. "
            "Sell 5% price and depth describe current stored sell orders; profit "
            "and return still use history_average. History proxies remain "
            "indicative, not guaranteed fills.",
            *(("No scenarios offer at least 20% return.",) if not rows else ()),
        ),
        tables=(
            table(
                (
                    "Product",
                    "Strategy",
                    "Hub",
                    "Avg traded Units/day",
                    "Unit cost ISK",
                    "History avg Price/unit",
                    "Sell 5% Price/unit",
                    "5% depth",
                    *SALES_HEADINGS[3:9],
                    "Status",
                ),
                rows,
                cell_links={
                    (row, column): f"item-{plan.type_id}"
                    if column == 0
                    else plan.anchor
                    for row, (_, plan, _) in enumerate(candidates)
                    for column in (0, 1)
                },
            ),
        ),
    )


def sections(report: Report) -> list[Section]:
    """Build decision-first detail sections and audit tables from the same model."""
    data = report.data
    result = [
        Section(
            title="Assumptions and limitations",
            anchor="assumptions",
            paragraphs=(
                f"Scope: {data.scope}. Generated: {report.generated_at.isoformat()}.",
                "Osmeden high-sec NPC station; Omega; relevant skills 5; no implants, "
                "structure bonuses, rigs, or decryptors. BPO ownership does not imply free BPCs.",
                "All purchased inputs use Jita primary-station sell 5% (outlier filter factor 100). "
                "Reaction outputs are purchased: this facility cannot make reactions.",
                f"Sales tax: {number(report.sales_tax_rate * 100)}%; broker fee: "
                f"{number(report.broker_fee_rate * 100)}%. These are proof assumptions. "
                "NPC job tax 0.25%, SCC 4%, Alpha surcharge 0%; Osmeden activity-specific indices.",
                "Sales tax applies to all sale bases. Broker fees apply to sell_5pct "
                "and history_average, but not sales to buy orders (buy_5pct).",
                "Rounded-up expected-attempt costing: ceil(1/p) per required successful BPC. "
                "All budgeted attempts consume inputs and incur fees/time. Success is not guaranteed.",
                "Invented BPC licensed runs come from the static invention product quantity. "
                "Ten-run reference batches, except T2 ships/rigs use those licensed runs. Combine component "
                "demand per product/strategy; charge whole batches without surplus credit.",
                "Ignore existing BPCs/inventory. Exclude historical BPO purchase/research, hauling, "
                "relisting and scheduling. Job-hours are not elapsed completion time.",
                "History: ten calendar days ending at each region/type's latest available completed "
                "day. Missing days stay visible; observed volume is divided by ten. "
                "Zero-volume history has no usable sale price.",
                "Prices are indicative, not execution quotes. Regional history is not hub-local. "
                "Return is profit / allocated production cost; assume the entire reference output sells.",
                "Monetary calculations use unrounded Decimal amounts. Display uses two decimals; "
                "CSV retains calculation precision. Client whole-ISK rounding can differ. "
                "Durations use reference float formulas converted via str, never float currency.",
                *data.warnings,
            ),
            tables=(
                table(
                    ("Activity", "Osmeden cost index %", "NPC facility", "SCC"),
                    (
                        (
                            a,
                            None
                            if data.indices.get(a) is None
                            else data.indices[a] * 100,
                            "0.25%",
                            "4%",
                        )
                        for a in ("copying", "invention", "manufacturing")
                    ),
                ),
            ),
        )
    ]
    result.append(profit_opportunities(report))
    index_plans = sorted(
        report.plans,
        key=lambda plan: (
            data.items[plan.type_id].market_path is None,
            data.items[plan.type_id].market_path or "",
            data.items[plan.type_id].name,
            plan.type_id,
        ),
    )
    index_links: dict[tuple[int, int], str] = {}
    index_anchors: dict[tuple[int, int], str] = {}
    indexed_products: set[int] = set()
    for row, plan in enumerate(index_plans):
        index_links[row, 0] = f"item-{plan.type_id}"
        if plan.type_id not in indexed_products:
            index_anchors[row, 0] = f"index-item-{plan.type_id}"
            indexed_products.add(plan.type_id)
    result.append(
        Section(
            title="Item index",
            anchor="item-index",
            tables=(
                table(
                    (
                        "Product",
                        "Strategy",
                        "Units",
                        "m3",
                        "Batch cost ISK",
                        "Unit cost ISK",
                        "Job-hours",
                        "Status",
                    ),
                    (
                        (
                            data.items[p.type_id].name,
                            p.strategy,
                            p.produced or None,
                            None
                            if data.items[p.type_id].volume is None or not p.produced
                            else data.items[p.type_id].volume * p.produced,
                            p.total,
                            p.unit_cost,
                            sum((j.duration for j in p.jobs), Decimal(0)) / 3600,
                            p.status,
                        )
                        for p in index_plans
                    ),
                    cell_links=index_links,
                    cell_anchors=index_anchors,
                ),
            ),
        )
    )
    for type_id in sorted({p.type_id for p in report.plans}):
        item = data.items[type_id]
        plans = [p for p in report.plans if p.type_id == type_id]
        result.append(
            Section(
                title=item.name,
                anchor=f"item-{type_id}",
                index_anchor=f"index-item-{type_id}",
                tables=(
                    table(
                        (
                            "Strategy",
                            "Reference runs",
                            "Portion Size",
                            "Units",
                            "m3",
                            "Batch cost ISK",
                            "Unit cost ISK",
                            "Job-hours",
                            "Status",
                        ),
                        (
                            (
                                p.strategy,
                                p.reference_runs,
                                item.portion_size,
                                p.produced or None,
                                None
                                if item.volume is None or not p.produced
                                else item.volume * p.produced,
                                p.total,
                                p.unit_cost,
                                sum((j.duration for j in p.jobs), Decimal(0)) / 3600,
                                p.status,
                            )
                            for p in plans
                        ),
                        caption="Strategy Summaries",
                        cell_links={(row, 0): p.anchor for row, p in enumerate(plans)},
                        cell_anchors={
                            (row, 0): f"summary-{p.anchor}"
                            for row, p in enumerate(plans)
                        },
                    ),
                ),
            )
        )
        result.append(
            Section(
                title="Regional demand and history coverage",
                anchor=f"history-{type_id}",
                level=3,
                tables=(
                    table(
                        (
                            "Hub",
                            "Regional proxy",
                            "Oldest day",
                            "Newest day",
                            "Days present / 10",
                            "Avg traded units/day",
                            "Status",
                        ),
                        (
                            (
                                h.system_name,
                                h.region_name,
                                None if m is None else m.history_start,
                                None if m is None else m.history_end,
                                0 if m is None else m.days_present,
                                None if m is None else m.daily_sales,
                                "missing"
                                if m is None or m.daily_sales is None
                                else "complete"
                                if m.days_present == 10
                                else "incomplete coverage",
                            )
                            for h in MARKET_HUBS
                            for m in (data.markets.get((h.station_id, type_id)),)
                        ),
                    ),
                ),
            )
        )
        for plan in plans:
            result.extend(plan_sections(report, plan))
    result.append(
        Section(
            title="Source provenance and freshness",
            anchor="sources",
            paragraphs=(
                "Sources are selected independently. Stale data warns and renders; "
                "no fetching or refresh occurs. History provenance lists each receipt "
                "used in its window; the history table does not retain response IDs.",
            ),
            tables=(
                table(
                    (
                        "Source",
                        "Reference",
                        "Received / version",
                        "Source expiry",
                        "Argus expiry",
                        "Freshness",
                    ),
                    (
                        (
                            s.label,
                            s.reference,
                            s.received_at,
                            s.expires_at,
                            s.argus_expires_at,
                            s.freshness(now=report.generated_at),
                        )
                        for s in data.sources
                    ),
                ),
            ),
        )
    )
    return result


def plan_sections(report: Report, plan: Plan) -> list[Section]:
    """Expose the full production story without charging internal transfers twice."""
    data = report.data
    by_job = {job.job_id: job for job in plan.jobs}
    nodes = {n.type_id: n for n in plan.nodes}

    def input_unit_price(*, type_id: int, activity: str) -> Decimal | None:
        child = nodes.get(type_id) if activity == "manufacturing" else None
        if child is not None:
            return None if child.cost is None else child.cost / child.required
        return data.input_prices.get(type_id)

    outcomes: dict[int, list[Outcome]] = {o.station_id: [] for o in plan.outcomes}
    for outcome in plan.outcomes:
        outcomes[outcome.station_id].append(outcome)
    result = [
        Section(
            title=plan.strategy,
            anchor=plan.anchor,
            summary_anchor=f"summary-{plan.anchor}",
            level=3,
            paragraphs=(
                f"Estimate status: {plan.status}. "
                "Blueprints and manufactured inputs below are internal transfers, "
                "not extra shopping-list purchases.",
                *plan.warnings,
            ),
            tree=dependency_tree(report, plan),
            tables=(
                table(
                    (*SALES_HEADINGS[:-1], "Avg traded units/day", "Status"),
                    (
                        (
                            *sales_row(o)[:-1],
                            None if market is None else market.daily_sales,
                            o.status,
                        )
                        for h in MARKET_HUBS
                        for market in (data.markets.get((h.station_id, plan.type_id)),)
                        for o in outcomes[h.station_id]
                    ),
                    caption="Sales Data",
                ),
            ),
        )
    ]
    activity_groups = [
        (activity, [j for j in plan.jobs if j.activity == activity])
        for activity in ("copying", "invention", "manufacturing")
    ]
    activity_sections: dict[str, Section] = {}
    invention_results = {
        dependency: node
        for node in plan.nodes
        for job_id in node.job_ids
        for dependency in by_job[job_id].dependencies
        if by_job[dependency].activity == "invention"
    }
    for activity, jobs in activity_groups:
        headings = (
            "Job",
            "Blueprint",
            "Attempts" if activity == "invention" else "Runs/attempts",
            *(("Licensed runs/BPC",) if activity != "invention" else ()),
            *(("Remaining runs",) if activity == "manufacturing" else ()),
            *(("Success Probability", "Result") if activity == "invention" else ()),
            *(("Licensed runs/BPC",) if activity == "invention" else ()),
            "ME / TE",
            "Job-hours",
            f"{activity.capitalize()} Cost ISK",
            "Depends on",
        )
        job_rows: list[tuple[object, ...]] = []
        for job in jobs:
            invention_cells: tuple[object, ...] = ()
            if activity == "invention":
                node = invention_results[job.job_id]
                invention_cells = (
                    "Unavailable"
                    if node.probability is None
                    else f"{number(node.probability * 100)}%",
                    item_name(report, node.blueprint_id),
                )
            input_costs: list[Decimal | None] = [job.total_fee]
            for material in job.inputs:
                price = input_unit_price(type_id=material.type_id, activity=activity)
                input_costs.append(None if price is None else price * material.quantity)
            job_rows.append(
                (
                    job.job_id,
                    item_name(report, job.blueprint_id),
                    job.runs,
                    *((job.licensed_runs,) if activity != "invention" else ()),
                    *((job.remaining_runs,) if activity == "manufacturing" else ()),
                    *invention_cells,
                    *((job.licensed_runs,) if activity == "invention" else ()),
                    f"{job.me} / {job.te}",
                    job.duration / 3600,
                    known_sum(input_costs),
                    ", ".join(job.dependencies) or "—",
                )
            )
        activity_sections[activity] = Section(
            title=activity.capitalize(),
            anchor=f"{plan.anchor}-{activity}",
            level=4,
            paragraphs=() if jobs else ("No jobs required for this activity.",),
            tables=(
                table(
                    headings,
                    job_rows,
                    caption=f"{activity.capitalize()} jobs",
                ),
            ),
        )
    result.extend(activity_sections[activity] for activity, _ in activity_groups)
    result.append(
        Section(
            title="Installation Costs",
            anchor=f"{plan.anchor}-installation-costs",
            level=4,
            paragraphs=(
                "Costs below are installation charges only; material and BPC transfer "
                "values are not added here. Job-hours are summed work, not elapsed time.",
                *(
                    ("The plan is incomplete; only known jobs are listed.",)
                    if plan.status == "incomplete"
                    else ()
                ),
            ),
            tables=(
                table(
                    (
                        "Activity",
                        "Job",
                        "EIV ISK",
                        "PTV ISK",
                        "Index charge",
                        "Facility charge",
                        "SCC charge",
                        "Alpha charge",
                        "Total installation ISK",
                        "Job-hours",
                    ),
                    (
                        (
                            activity.capitalize(),
                            j.job_id,
                            j.charges.eiv,
                            j.charges.ptv,
                            j.charges.index,
                            j.charges.facility,
                            j.charges.scc,
                            0,
                            j.total_fee,
                            j.duration / 3600,
                        )
                        for activity, jobs in activity_groups
                        for j in jobs
                    ),
                    caption="Installation charge breakdown",
                ),
            ),
        )
    )
    input_rows: list[tuple[object, ...]] = []
    input_volumes: list[Decimal | None] = []
    input_values: list[Decimal | None] = []
    for job in plan.jobs:
        for m in job.inputs:
            child = nodes.get(m.type_id) if job.activity == "manufacturing" else None
            price = input_unit_price(type_id=m.type_id, activity=job.activity)
            item = data.items.get(m.type_id)
            volume = (
                None
                if item is None or item.volume is None
                else item.volume * m.quantity
            )
            value = None if price is None else price * m.quantity
            input_volumes.append(volume)
            input_values.append(value)
            input_rows.append(
                (
                    job.job_id,
                    item_name(report, m.type_id),
                    m.quantity,
                    volume,
                    "internal production transfer" if child else "Jita sell 5%",
                    price,
                    value,
                )
            )
    result.append(
        Section(
            title="Per-job material inputs",
            anchor=f"{plan.anchor}-inputs",
            level=4,
            paragraphs=(
                f"Total m3: {number(known_sum(input_volumes))}. "
                f"Total Cost: {number(known_sum(input_values))} ISK.",
            ),
            tables=(
                table(
                    (
                        "Job",
                        "Material",
                        "Quantity",
                        "m3",
                        "Valuation",
                        "ISK/unit",
                        "Value ISK",
                    ),
                    [
                        *input_rows,
                        (
                            "Total",
                            "",
                            "",
                            known_sum(input_volumes),
                            "",
                            "",
                            known_sum(input_values),
                        ),
                    ],
                ),
            ),
        )
    )
    shopping_quantities: dict[int, int] = defaultdict(int)
    for purchase in plan.shopping:
        shopping_quantities[purchase.type_id] += purchase.quantity
    shopping_rows = [
        (
            " ".join(data.items[type_id].name.split())
            if type_id in data.items
            else f"UNKNOWN {type_id}",
            str(quantity),
        )
        for type_id, quantity in sorted(shopping_quantities.items())
    ]
    name_width = max(len(name) for name, _ in [("Name", "Quantity"), *shopping_rows])
    quantity_width = max(
        len(quantity) for _, quantity in [("Name", "Quantity"), *shopping_rows]
    )
    shopping_text = "\n".join(
        f"{name:<{name_width}}  {quantity:>{quantity_width}}"
        for name, quantity in [("Name", "Quantity"), *shopping_rows]
    )
    result.append(
        Section(
            title="External Shopping List",
            anchor=f"{plan.anchor}-shopping",
            level=4,
            raw_text=shopping_text,
        )
    )
    external = known_sum(p.cost for p in plan.shopping)
    job_fees = known_sum(j.total_fee for j in plan.jobs)
    result.append(
        Section(
            title="Cost reconciliation",
            anchor=f"{plan.anchor}-costs",
            level=4,
            paragraphs=(
                "No BPC/component transfer value is added again. Unknown required "
                "inputs invalidate the total rather than producing a partial quote.",
            ),
            tables=(
                table(
                    ("Category", "Value"),
                    (
                        (
                            "External materials and blueprint preparation consumables ISK",
                            external,
                        ),
                        ("Installation charges across all jobs ISK", job_fees),
                        ("Allocated production cost ISK", plan.total),
                        ("Attributed produced units", plan.produced or None),
                        ("Unit cost ISK", plan.unit_cost),
                    ),
                ),
            ),
        )
    )
    return result


def environment() -> Environment:
    """Load only proof-local templates with strict context and HTML autoescaping."""
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent),
        undefined=StrictUndefined,
        autoescape=lambda name: bool(name and ".html." in name),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["md"] = markdown_cell  # type: ignore[reportUnknownMemberType]
    env.filters["href"] = lambda anchor: f"#{anchor}"  # type: ignore[reportUnknownMemberType]
    return env


def render_markdown(report: Report) -> str:
    """Format generated Markdown through the shared project helper."""
    text = (
        environment().get_template("report.md.jinja2").render(sections=sections(report))
    )
    return format_markdown(text)


def render_html(report: Report) -> str:
    """Render a self-contained accessible HTML document from the same sections."""
    return (
        environment()
        .get_template("report.html.jinja2")
        .render(sections=sections(report))
    )


def report_pages(report: Report) -> dict[str, list[Section]]:
    """Partition presentation sections by static group, preserving each story."""
    pages: dict[str, list[Section]] = {
        "index": [],
        "profit-opportunities": [],
        "assumptions": [],
        "sources": [],
    }
    fixed = {
        "item-index": "index",
        "profit-opportunities": "profit-opportunities",
        "assumptions": "assumptions",
        "sources": "sources",
    }
    current = ""
    for section in sections(report):
        if section.anchor == "profit-opportunities":
            pages["profit-opportunities"].append(replace(section, tables=()))
            entry = section.tables[0]
            for hub in MARKET_HUBS:
                rows = [
                    row
                    for row, values in enumerate(entry.rows)
                    if values[2] == hub.system_name
                ]
                pages["profit-opportunities"].append(
                    Section(
                        title=hub.system_name,
                        anchor=f"opportunities-hub-{hub.station_id}",
                        level=3,
                        paragraphs=()
                        if rows
                        else ("No scenarios offer at least 20% return for this hub.",),
                        tables=(
                            replace(
                                entry,
                                headings=entry.headings[:2] + entry.headings[3:],
                                rows=tuple(
                                    entry.rows[row][:2] + entry.rows[row][3:]
                                    for row in rows
                                ),
                                cell_links={
                                    (new, col): entry.cell_links[old, col]
                                    for new, old in enumerate(rows)
                                    for col in (0, 1)
                                },
                            ),
                        ),
                    )
                )
            continue
        if section.anchor == "item-index":
            pages["index"].append(replace(section, tables=()))
            entry = section.tables[0]
            grouped_rows: dict[int | None, list[int]] = defaultdict(list)
            group_names: dict[int | None, str] = {}
            group_categories: dict[int | None, tuple[int | None, str]] = {}
            for row in range(len(entry.rows)):
                type_id = int(entry.cell_links[row, 0].removeprefix("item-"))
                item = report.data.items[type_id]
                grouped_rows[item.group_id].append(row)
                group_names[item.group_id] = item.group_name
                group_categories[item.group_id] = (item.category_id, item.category_name)
            for group_id, rows in sorted(
                grouped_rows.items(),
                key=lambda pair: (
                    pair[0] is None,
                    group_names[pair[0]].casefold(),
                    pair[0] or 0,
                ),
            ):
                pages["index"].append(
                    Section(
                        title=f"{group_names[group_id]} products",
                        anchor=f"index-group-{group_id if group_id is not None else 'unknown'}",
                        level=3,
                        category_id=group_categories[group_id][0],
                        category_name=group_categories[group_id][1],
                        tables=(
                            replace(
                                entry,
                                rows=tuple(entry.rows[row] for row in rows),
                                cell_links={
                                    (new, col): entry.cell_links[old, col]
                                    for new, old in enumerate(rows)
                                    for col in range(len(entry.headings))
                                    if (old, col) in entry.cell_links
                                },
                                cell_anchors={
                                    (new, col): entry.cell_anchors[old, col]
                                    for new, old in enumerate(rows)
                                    for col in range(len(entry.headings))
                                    if (old, col) in entry.cell_anchors
                                },
                            ),
                        ),
                    )
                )
            continue
        if section.anchor in fixed:
            pages[fixed[section.anchor]].append(section)
            continue
        if section.index_anchor:
            type_id = int(section.anchor.removeprefix("item-"))
            item = report.data.items[type_id]
            current = (
                f"group-{item.group_id}"
                if item.group_id is not None
                else "group-unknown"
            )
            if current not in pages:
                pages[current] = [
                    Section(
                        title=f"{item.group_name} products",
                        anchor=current,
                    )
                ]
        if not current:
            raise ValueError(f"Product section has no group: {section.anchor}")
        pages[current].append(section)
    return pages


def render_pages(pages: dict[str, list[Section]], *, extension: str) -> dict[str, str]:
    """Render linked documents with validated relative anchor destinations."""
    owners: dict[str, str] = {}
    for stem, content in pages.items():
        for section in content:
            anchors = [section.anchor]
            for entry in section.tables:
                anchors.extend(entry.cell_anchors.values())
            for anchor in anchors:
                if anchor in owners:
                    raise ValueError(f"Duplicate report anchor: {anchor}")
                owners[anchor] = stem
    navigation = tuple(
        (content[0].title, f"{stem}.{extension}") for stem, content in pages.items()
    )
    rendered: dict[str, str] = {}
    for stem, content in pages.items():

        def href(anchor: str, *, current: str = stem) -> str:
            target = owners.get(anchor)
            if target is None:
                raise ValueError(f"Unknown report link: {anchor}")
            return (
                f"#{anchor}" if target == current else f"{target}.{extension}#{anchor}"
            )

        env = environment()
        env.filters["href"] = href
        grouped_navigation: dict[tuple[int | None, str], list[tuple[str, str]]] = (
            defaultdict(list)
        )
        for section in content:
            if section.anchor.startswith("index-group-"):
                grouped_navigation[section.category_id, section.category_name].append(
                    (section.title, f"#{section.anchor}")
                )
        text = env.get_template(f"report.{extension}.jinja2").render(
            sections=content,
            page_title=content[0].title,
            navigation=tuple(
                (title, link)
                for title, link in navigation
                if link != f"{stem}.{extension}"
                and (stem == "index" or not link.startswith("group-"))
            ),
            split_page=True,
            index_sidebar=stem == "index" and extension == "html",
            product_sidebar=stem.startswith("group-") and extension == "html",
            hub_sidebar=stem == "profit-opportunities" and extension == "html",
            hub_navigation=tuple(
                (section.title, f"#{section.anchor}")
                for section in content
                if section.anchor.startswith("opportunities-hub-")
            ),
            product_navigation=tuple(
                (section.title, f"#{section.anchor}")
                for section in content
                if section.index_anchor
            ),
            group_navigation=tuple(
                (category[1], links)
                for category, links in sorted(
                    grouped_navigation.items(),
                    key=lambda pair: (
                        pair[0][0] is None,
                        pair[0][1].casefold(),
                        pair[0][0] or 0,
                    ),
                )
            ),
        )
        rendered[f"{stem}.{extension}"] = (
            format_markdown(text) if extension == "md" else text
        )
    return rendered


def write_reports(
    report: Report, *, destination: Path, overwrite: bool = False
) -> tuple[Path, ...]:
    """Render/preflight before writing; writes are not a multi-file transaction."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Destination is not a directory: {destination}")
    pages = report_pages(report)
    paths = (
        destination / "industry-report.csv",
        *(
            destination / folder / f"{stem}.{extension}"
            for folder, extension in (("markdown", "md"), ("html", "html"))
            for stem in pages
        ),
    )
    for folder in (destination / "markdown", destination / "html"):
        if folder.exists() and not folder.is_dir():
            raise ValueError(f"Destination is not a directory: {folder}")
    for path in paths:
        if path.exists() and (not overwrite or not path.is_file()):
            raise FileExistsError(f"Report exists: {path}; use --overwrite.")
    rendered = {destination / "industry-report.csv": render_csv(report)}
    for folder, extension in (("markdown", "md"), ("html", "html")):
        rendered.update(
            (destination / folder / name, text)
            for name, text in render_pages(pages, extension=extension).items()
        )
    for path, text in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(text)
    return paths
