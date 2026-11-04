"""Render the canonical proof result to comparison CSV and detailed companions."""

import csv
import io
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
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
                "Ten-run reference batches, except one run for T2 ships/rigs. Combine component "
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
    by_blueprint = {n.blueprint_id: n for n in plan.nodes}
    by_job = {job.job_id: job for job in plan.jobs}
    blueprint_inputs: list[tuple[object, ...]] = []
    for job in plan.jobs:
        if job.activity != "manufacturing":
            continue
        node = by_blueprint[job.blueprint_id]
        if node.probability is not None:
            cost = (
                None
                if node.preparation_cost is None
                else node.preparation_cost / node.bpcs
            )
        else:
            cost = known_sum(
                value
                for dep in job.dependencies
                if by_job[dep].activity == "copying"
                for value in (
                    by_job[dep].total_fee,
                    *(
                        None
                        if data.input_prices.get(m.type_id) is None
                        else data.input_prices[m.type_id] * m.quantity
                        for m in by_job[dep].inputs
                    ),
                )
            )
        blueprint_inputs.append(
            (
                job.job_id,
                item_name(report, job.blueprint_id),
                ", ".join(
                    dep
                    for dep in job.dependencies
                    if by_job[dep].activity != "manufacturing"
                ),
                f"{job.me} / {job.te}",
                1,
                job.licensed_runs,
                job.runs,
                job.remaining_runs,
                cost,
            )
        )
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
                    (
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
                    ),
                    (
                        (
                            h.system_name,
                            o.basis,
                            o.price,
                            o.sales_tax,
                            o.broker_fee,
                            o.net_per_unit,
                            o.profit_per_unit,
                            o.total_profit,
                            o.return_pct,
                            o.depth,
                            o.status,
                        )
                        for h in MARKET_HUBS
                        for o in outcomes[h.station_id]
                    ),
                    caption="Sales Data",
                ),
            ),
        )
    ]
    result.append(
        Section(
            title="Blueprints, invention and output allocation",
            anchor=f"{plan.anchor}-blueprints",
            level=4,
            tables=(
                table(
                    (
                        "Product",
                        "Blueprint",
                        "ME / TE",
                        "BPCs",
                        "Demand",
                        "Output",
                        "Surplus",
                        "Success probability",
                        "Raw expected attempts/BPC",
                        "Costed attempts/BPC",
                        "BPC preparation cost",
                        "Rolled-up cost",
                    ),
                    (
                        (
                            item_name(report, n.type_id),
                            item_name(report, n.blueprint_id),
                            f"{n.me} / {n.te}",
                            n.bpcs,
                            n.required,
                            n.produced,
                            n.produced - n.required,
                            n.probability,
                            None
                            if n.probability is None
                            else Decimal(1) / n.probability,
                            n.attempts_per_bpc or None,
                            n.preparation_cost,
                            n.cost,
                        )
                        for n in plan.nodes
                    ),
                ),
            ),
        )
    )
    result.append(
        Section(
            title="BPC material inputs to manufacturing",
            anchor=f"{plan.anchor}-bpc-inputs",
            level=4,
            paragraphs=(
                "BPC acquisition costs are internal transfers from copying/invention, "
                "including budgeted failed attempts. Do not add these again to total cost. "
                "Invented copies are assumed successful outputs for costing, not guarantees.",
            ),
            tables=(
                table(
                    (
                        "Manufacturing job",
                        "BPC type",
                        "Source steps",
                        "ME / TE",
                        "Copies",
                        "Licensed runs",
                        "Runs consumed",
                        "Runs remaining",
                        "Allocated BPC input ISK",
                    ),
                    blueprint_inputs,
                ),
            ),
        )
    )
    result.append(
        Section(
            title="Jobs and blueprint inputs",
            anchor=f"{plan.anchor}-jobs",
            level=4,
            tables=(
                table(
                    (
                        "Job",
                        "Activity",
                        "Blueprint",
                        "Runs/attempts",
                        "Licensed runs/BPC",
                        "Remaining runs",
                        "ME / TE",
                        "Duration seconds",
                        "Depends on",
                    ),
                    (
                        (
                            j.job_id,
                            j.activity,
                            item_name(report, j.blueprint_id),
                            j.runs,
                            j.licensed_runs,
                            j.remaining_runs,
                            f"{j.me} / {j.te}",
                            j.duration,
                            ", ".join(j.dependencies) or "—",
                        )
                        for j in plan.jobs
                    ),
                ),
                table(
                    (
                        "Job",
                        "EIV ISK",
                        "PTV ISK",
                        "Index charge",
                        "Facility charge",
                        "SCC charge",
                        "Alpha charge",
                        "Total installation ISK",
                    ),
                    (
                        (
                            j.job_id,
                            j.charges.eiv,
                            j.charges.ptv,
                            j.charges.index,
                            j.charges.facility,
                            j.charges.scc,
                            0,
                            j.total_fee,
                        )
                        for j in plan.jobs
                    ),
                ),
            ),
        )
    )
    nodes = {n.type_id: n for n in plan.nodes}
    input_rows: list[tuple[object, ...]] = []
    for job in plan.jobs:
        for m in job.inputs:
            child = nodes.get(m.type_id) if job.activity == "manufacturing" else None
            price = (
                (None if child.cost is None else child.cost / child.required)
                if child
                else data.input_prices.get(m.type_id)
            )
            input_rows.append(
                (
                    job.job_id,
                    item_name(report, m.type_id),
                    m.quantity,
                    "internal production transfer" if child else "Jita sell 5%",
                    price,
                    None if price is None else price * m.quantity,
                )
            )
    result.append(
        Section(
            title="Per-job material inputs",
            anchor=f"{plan.anchor}-inputs",
            level=4,
            paragraphs=(
                "Quantities are rounded per actual manufacturing job after ME. "
                "Input BPCs are listed in the preceding job/dependency table. "
                "Internal component transfer prices allocate the whole child batch "
                "over demanded units, including surplus cost without credit.",
            ),
            tables=(
                table(
                    (
                        "Job",
                        "Material",
                        "Quantity",
                        "Valuation",
                        "ISK/unit",
                        "Value ISK",
                    ),
                    input_rows,
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


def write_reports(
    report: Report, *, destination: Path, overwrite: bool = False
) -> tuple[Path, ...]:
    """Render/preflight before writing; writes are not a multi-file transaction."""
    if destination.exists() and not destination.is_dir():
        raise ValueError(f"Destination is not a directory: {destination}")
    paths = tuple(
        destination / f"industry-report{suffix}" for suffix in (".csv", ".md", ".html")
    )
    for path in paths:
        if path.exists() and (not overwrite or not path.is_file()):
            raise FileExistsError(f"Report exists: {path}; use --overwrite.")
    rendered = (render_csv(report), render_markdown(report), render_html(report))
    destination.mkdir(parents=True, exist_ok=True)
    for path, text in zip(paths, rendered, strict=True):
        with path.open(
            "w" if overwrite else "x", encoding="utf-8", newline=""
        ) as stream:
            stream.write(text)
    return paths
