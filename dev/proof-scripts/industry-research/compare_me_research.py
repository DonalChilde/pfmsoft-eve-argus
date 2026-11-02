"""Compare provisional ME PTV formulas against read-only Argus snapshots.

Mechanics reviewed as of 2026-10-27; NOT verified current game formulas.
This proof deliberately keeps competing hypotheses outside the reference module.

Sources:
    https://wiki.eveuniversity.org/Research
    https://www.eveonline.com/news/view/industry-3rd-party-developers
    https://www.eveonline.com/news/view/viridian-expansion-notes

The three candidates normalize unmodified step duration by either the blueprint
base research time or 105 seconds, or use the published level multiplier directly.
Rank-one blueprints cannot distinguish these candidates. A separate diagnostic
ceilings PTV before applying charges, mimicking the old PTV helper's rounding.
No skills, implants, or facility time reductions are assumed. Primary exports
compare single installations from ME zero to each target; incremental jobs are
retained in a separate subdirectory.
"""

import argparse
import csv
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import TypedDict

from pfmsoft.eve_argus.dynamic import read as dynamic_read
from pfmsoft.eve_argus.static import read as static_read

CUMULATIVE_SECONDS = (0, 105, 250, 595, 1414, 3360, 8000, 19000, 45255, 107700, 256000)


class ComparisonRow(TypedDict):
    """Flat comparison row; all monetary quantities are ISK."""

    candidate: str
    start_me: int
    target_me: int
    base_step_seconds: Decimal
    manufacturing_eiv_isk: Decimal
    research_multiplier: Decimal
    system_cost_index: Decimal
    facility_tax_rate: Decimal
    scc_rate: Decimal
    alpha_tax_rate: Decimal
    ptv_raw_isk: Decimal
    ptv_ceiling_isk: Decimal
    index_raw_isk: Decimal
    facility_raw_isk: Decimal
    scc_raw_isk: Decimal
    alpha_raw_isk: Decimal
    total_raw_isk: Decimal
    gross_job_cost_whole_isk: Decimal
    total_taxes_whole_isk: Decimal
    total_job_cost_whole_isk: Decimal
    total_components_cents_isk: Decimal
    total_components_whole_isk: Decimal
    total_components_ceiling_isk: Decimal
    total_aggregate_cents_isk: Decimal
    total_aggregate_whole_isk: Decimal
    total_ceiled_ptv_components_cents_isk: Decimal
    cumulative_total_components_cents_isk: Decimal


@dataclass(slots=True, kw_only=True, frozen=True)
class SnapshotInputs:
    """Resolved values and provenance from a consistent read of each database."""

    manufacturing_eiv: Decimal
    base_time_seconds: int
    system_cost_index: Decimal
    metadata: dict[str, object]


def calculate_rows(
    *,
    manufacturing_eiv: Decimal,
    base_time_seconds: int,
    system_cost_index: Decimal,
    facility_tax_rate: Decimal,
    scc_rate: Decimal,
    alpha_tax_rate: Decimal,
    from_zero: bool = False,
) -> list[ComparisonRow]:
    """Evaluate incremental or zero-to-target jobs under three provisional rules.

    With from_zero, each row is a separate alternative installation from zero;
    its charges are rounded once for that entire job, not summed across steps.
    Rates are fractions; the caller supplies the effective Alpha rate (zero for
    Omega). NPC installation-cost factor is assumed to be one. No rounding
    policy is claimed as correct: component/aggregate rounding and pre-fee PTV
    ceiling are exported separately. Decimal arithmetic uses Python's default
    28-digit context; recurring multiplier values are therefore approximations.
    """
    if base_time_seconds <= 0:
        raise ValueError("Base research time must be positive.")
    for value in (
        manufacturing_eiv,
        system_cost_index,
        facility_tax_rate,
        scc_rate,
        alpha_tax_rate,
    ):
        if not value.is_finite() or value < 0:
            raise ValueError("EIV and rates must be finite and nonnegative.")

    rates = (system_cost_index, facility_tax_rate, scc_rate, alpha_tax_rate)
    rows: list[ComparisonRow] = []
    for candidate in (
        "level_multiplier",
        "blueprint_time_normalized",
        "fixed_105_seconds",
    ):
        cumulative = Decimal(0)
        for target in range(1, 11):
            start = 0 if from_zero else target - 1
            reference_step_seconds = Decimal(
                CUMULATIVE_SECONDS[target] - CUMULATIVE_SECONDS[start]
            )
            multiplier = reference_step_seconds / Decimal(105)
            step_seconds = (
                Decimal(base_time_seconds) * reference_step_seconds / Decimal(105)
            )
            match candidate:
                case "level_multiplier":
                    ptv = (
                        manufacturing_eiv
                        * Decimal("0.02")
                        * reference_step_seconds
                        / Decimal(105)
                    )
                case "blueprint_time_normalized":
                    ptv = (
                        manufacturing_eiv
                        * Decimal("0.02")
                        * step_seconds
                        / Decimal(base_time_seconds)
                    )
                case "fixed_105_seconds":
                    ptv = (
                        manufacturing_eiv
                        * Decimal("0.02")
                        * step_seconds
                        / Decimal(105)
                    )
            ceiled_ptv = ptv.to_integral_value(rounding=ROUND_CEILING)
            charges = tuple(ptv * rate for rate in rates)
            total = sum(charges, start=Decimal(0))
            cents_total = sum(
                (
                    charge.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    for charge in charges
                ),
                start=Decimal(0),
            )
            cumulative = cents_total if from_zero else cumulative + cents_total
            whole_charges = tuple(
                charge.quantize(Decimal(1), rounding=ROUND_HALF_UP)
                for charge in charges
            )
            rows.append(
                ComparisonRow(
                    candidate=candidate,
                    start_me=start,
                    target_me=target,
                    base_step_seconds=step_seconds,
                    manufacturing_eiv_isk=manufacturing_eiv,
                    research_multiplier=multiplier,
                    system_cost_index=system_cost_index,
                    facility_tax_rate=facility_tax_rate,
                    scc_rate=scc_rate,
                    alpha_tax_rate=alpha_tax_rate,
                    ptv_raw_isk=ptv,
                    ptv_ceiling_isk=ceiled_ptv,
                    index_raw_isk=charges[0],
                    facility_raw_isk=charges[1],
                    scc_raw_isk=charges[2],
                    alpha_raw_isk=charges[3],
                    total_raw_isk=total,
                    gross_job_cost_whole_isk=whole_charges[0],
                    total_taxes_whole_isk=sum(whole_charges[1:], start=Decimal(0)),
                    total_job_cost_whole_isk=sum(whole_charges, start=Decimal(0)),
                    total_components_cents_isk=cents_total,
                    total_components_whole_isk=sum(whole_charges, start=Decimal(0)),
                    total_components_ceiling_isk=sum(
                        (
                            charge.to_integral_value(rounding=ROUND_CEILING)
                            for charge in charges
                        ),
                        start=Decimal(0),
                    ),
                    total_aggregate_cents_isk=total.quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    ),
                    total_aggregate_whole_isk=total.quantize(
                        Decimal(1), rounding=ROUND_HALF_UP
                    ),
                    total_ceiled_ptv_components_cents_isk=sum(
                        (
                            (ceiled_ptv * rate).quantize(
                                Decimal("0.01"), rounding=ROUND_HALF_UP
                            )
                            for rate in rates
                        ),
                        start=Decimal(0),
                    ),
                    cumulative_total_components_cents_isk=cumulative,
                )
            )
    return rows


def load_inputs(
    *,
    static_database: Path,
    dynamic_database: Path,
    blueprint_name: str,
    system_name: str,
) -> SnapshotInputs:
    """Read latest stored snapshots without bootstrap, network calls, or writes.

    Fails explicitly for missing recipes, prices, indices, and snapshots.
    Each read transaction pins a consistent database view; the two databases
    are independent snapshots and their paths and metadata are retained.
    """
    with sqlite3.connect(
        static_database.resolve().as_uri() + "?mode=ro", uri=True
    ) as connection:
        connection.execute("BEGIN")
        types = static_read.types(connection)
        matches = [record for record in types.values() if record.name == blueprint_name]
        if len(matches) != 1:
            raise ValueError(f"Expected one blueprint named {blueprint_name!r}.")
        blueprint_id = matches[0].type_id
        blueprint = static_read.blueprints(connection)[blueprint_id]
        systems = static_read.map_solar_systems(connection)
        matches_system = [
            record for record in systems.values() if record.name == system_name
        ]
        if len(matches_system) != 1:
            raise ValueError(f"Expected one system named {system_name!r}.")
        system_id = matches_system[0].solar_system_id
    manufacturing = blueprint.activities.manufacturing
    research = blueprint.activities.research_material
    if manufacturing is None or not manufacturing.materials or research is None:
        raise ValueError("Blueprint needs manufacturing materials and ME research.")
    if research.materials:
        raise ValueError(
            "Research consumables are not supported by this fee-only proof."
        )

    with sqlite3.connect(
        dynamic_database.resolve().as_uri() + "?mode=ro", uri=True
    ) as connection:
        connection.execute("BEGIN")
        price_responses = dynamic_read.markets_prices_responses(connection)
        index_responses = dynamic_read.system_cost_indices_responses(connection)
        if not price_responses or not index_responses:
            raise ValueError(
                "Both adjusted-price and cost-index snapshots are required."
            )
        price_response = price_responses[0]
        index_response = index_responses[0]
        prices = dynamic_read.markets_prices(
            connection, price_response.response_metadata_id
        )
        indices = dynamic_read.system_cost_indices(
            connection, index_response.response_metadata_id
        )

    materials: list[dict[str, object]] = []
    eiv = Decimal(0)
    for material in manufacturing.materials:
        price = prices.records.get(material.type_id)
        if price is None or price.adjusted_price is None:
            raise ValueError(f"Missing adjusted price for material {material.type_id}.")
        value = price.adjusted_price * material.quantity
        eiv += value
        materials.append(
            {
                "type_id": material.type_id,
                "name": types[material.type_id].name,
                "quantity": material.quantity,
                "adjusted_price_isk": str(price.adjusted_price),
                "value_isk": str(value),
            }
        )
    index_record = indices.records.get(system_id)
    if index_record is None or index_record.researching_material_efficiency is None:
        raise ValueError(f"Missing ME cost index for {system_name}.")
    return SnapshotInputs(
        manufacturing_eiv=eiv,
        base_time_seconds=research.time,
        system_cost_index=index_record.researching_material_efficiency,
        metadata={
            "blueprint_name": blueprint_name,
            "blueprint_type_id": blueprint_id,
            "system_name": system_name,
            "system_id": system_id,
            "static_database": str(static_database.resolve()),
            "dynamic_database": str(dynamic_database.resolve()),
            "prices_snapshot": asdict(price_response),
            "indices_snapshot": asdict(index_response),
            "manufacturing_materials": materials,
            "base_research_time_seconds": research.time,
        },
    )


def export_results(
    *,
    output_dir: Path,
    metadata: dict[str, object],
    rows: list[ComparisonRow],
) -> None:
    """Write identical flat step records as decimal-text CSV and JSON strings."""
    if not rows:
        raise ValueError("Cannot export an empty comparison.")
    output_dir.mkdir(parents=True, exist_ok=True)
    serialized = [
        {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in row.items()
        }
        for row in rows
    ]
    (output_dir / "me_research.json").write_text(
        json.dumps({"metadata": metadata, "steps": serialized}, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "me_research.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(serialized[0]))
        writer.writeheader()
        writer.writerows(serialized)


def main() -> None:
    """Run the explicit NPC/Alpha scenario; help never opens databases."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-database", type=Path, required=True)
    parser.add_argument(
        "--dynamic-database",
        type=Path,
        default=Path("dev/app-dir/argus-dynamic-db.sqlite"),
    )
    parser.add_argument("--blueprint", default="Antimatter Charge S Blueprint")
    parser.add_argument("--system", default="Osmeden")
    parser.add_argument("--facility-tax", type=Decimal, default=Decimal("0.0025"))
    parser.add_argument("--scc", type=Decimal, default=Decimal("0.02"))
    parser.add_argument("--alpha-tax", type=Decimal, default=Decimal("0.0025"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inputs = load_inputs(
        static_database=args.static_database,
        dynamic_database=args.dynamic_database,
        blueprint_name=args.blueprint,
        system_name=args.system,
    )
    rows = calculate_rows(
        manufacturing_eiv=inputs.manufacturing_eiv,
        base_time_seconds=inputs.base_time_seconds,
        system_cost_index=inputs.system_cost_index,
        facility_tax_rate=args.facility_tax,
        scc_rate=args.scc,
        alpha_tax_rate=args.alpha_tax,
        from_zero=True,
    )
    metadata = inputs.metadata | {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "provisional hypotheses; awaiting in-game comparison",
        "facility": "NPC station; installation-cost factor assumed 1",
        "clone": "Alpha scenario; alpha-tax argument is effective applied rate",
        "time": "unmodified; skills and implants not supplied",
        "rounding": "alternative hypotheses, not verified policies",
        "ui_labels": {
            "gross_job_cost_whole_isk": "Gross Job Cost",
            "total_taxes_whole_isk": "Total Taxes",
            "total_job_cost_whole_isk": "Total Job Cost",
        },
        "job_boundary": "alternative single ME jobs from zero to each target",
        "cumulative_policy": "round components once per zero-to-target installation",
        "numeric_precision": "Decimal, 28 significant digits",
        "warnings": [
            "Rank-one candidates coincide; this blueprint cannot distinguish them."
            if inputs.base_time_seconds == 105
            else "Fixed-105 and blueprint-normalized hypotheses differ.",
            "Stored SCI is quantized to four decimal places; live quotes may differ.",
            "Facility tax 0.25% and cost factor 1 are assumptions, not a live quote.",
            "Stored snapshots are used even if expired; see expiration metadata.",
            "Blueprint ownership, character skills, and installation eligibility unverified.",
        ],
        "sources": [
            "https://wiki.eveuniversity.org/Research",
            "https://www.eveonline.com/news/view/industry-3rd-party-developers",
            "https://www.eveonline.com/news/view/viridian-expansion-notes",
            "SCC 2% and Alpha 0.25%: user-confirmed 2026-10-27",
        ],
    }
    export_results(output_dir=args.output_dir, metadata=metadata, rows=rows)
    incremental_rows = calculate_rows(
        manufacturing_eiv=inputs.manufacturing_eiv,
        base_time_seconds=inputs.base_time_seconds,
        system_cost_index=inputs.system_cost_index,
        facility_tax_rate=args.facility_tax,
        scc_rate=args.scc,
        alpha_tax_rate=args.alpha_tax,
    )
    export_results(
        output_dir=args.output_dir / "incremental",
        metadata=metadata
        | {
            "job_boundary": "ten independently installed one-step ME jobs per candidate",
            "cumulative_policy": "sum of per-component half-up cents-rounded step fees",
        },
        rows=incremental_rows,
    )
    print(f"EIV: {inputs.manufacturing_eiv} ISK; ME SCI: {inputs.system_cost_index}")
    print("ME job | PTV (ISK) | Gross Job Cost | Total Taxes | Total Job Cost")
    for row in rows[:10]:
        print(
            f"{row['start_me']:>2} -> {row['target_me']:<2} | "
            f"{row['ptv_raw_isk']:>14.6f} | "
            f"{row['gross_job_cost_whole_isk']:>14.0f} | "
            f"{row['total_taxes_whole_isk']:>11.0f} | "
            f"{row['total_job_cost_whole_isk']:>14.0f}"
        )
    print(f"Full candidate/rounding comparisons: {args.output_dir}")


if __name__ == "__main__":
    main()
