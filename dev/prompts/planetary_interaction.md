# Planetary Interaction

## Purpose and status

Design and implement reusable calculations and CLI reports for the unit costs of
Planetary Interaction (PI) materials across the full P0-P4 range.

The report should answer:

- What does each material cost under different purchase and production scenarios?
- Which inputs should be purchased, manufactured, or supplied by mining?
- How do import and export taxes affect those choices?
- What profit or loss results when the output is valued at Jita buy or sell prices?

This document records confirmed requirements, proposed implementation decisions,
and unresolved policies. It is not authorization to silently choose unresolved
behavior or public interfaces.

## References and current foundation

- [PI reference documentation](../../src/pfmsoft/eve_argus/pi/markdown_docs/pi-stats.md)
  contains recipes, type IDs, taxable base values, and customs formulas.
- [Factory plans](../../src/pfmsoft/eve_argus/pi/markdown_docs/factory-plans.md)
  provide context for later layout work, not requirements for this unit-cost stage.
- The [PI planning workbook](../tmp/pi_spreadsheet/PI%20Planning.xlsx), especially
  the **What PI To Build** sheet, demonstrates mixed-input choices using unit
  prices from other scenarios. Reconcile representative calculations with its
  formulas before implementation. The workbook formulas have not yet been
  inspected as part of this plan. Its display idioms are not requirements.
- [Order summaries](../../src/pfmsoft/eve_argus/dynamic/order_summary.py) and
  [history summaries](../../src/pfmsoft/eve_argus/market_history/history_summary.py)
  provide existing price calculations.
- [Price-summary CLI orchestration](../../src/pfmsoft/eve_argus/cli/reports/price_summaries.py)
  demonstrates stored-source selection and safe report exports.
- [Registered reports](../../src/pfmsoft/eve_argus/cli/reports/__init__.py)
  provide the integration point; no PI report is currently registered.

Keep PI data models and calculation logic under the
[`pi` package](../../src/pfmsoft/eve_argus/pi). Keep CLI orchestration, report
collection, and rendering separate from reusable calculations.

## Confirmed scope

- Cover the complete P0-P4 material range.
- Use one configurable effective customs-tax rate across all scenarios for now.
  This is a convenience, not a model of every possible in-game tax arrangement.
- Compare Jita buy, Jita sell, and regional ten-day history-summary price bases.
  The history price is The Forge regional data, not a station-specific average.
- Support mixed input tiers and sources within the same recipe.
- Preserve all modeled outcomes, including suboptimal, unprofitable, and
  incomplete alternatives. External constraints may justify a non-cheapest choice.
- Highlight the cheapest complete alternative without replacing the other results.
- Allow a scenario's calculated unit price to supply an input to another scenario.
- Support small operations combining mining-derived and purchased materials.
- Produce a CLI report with Markdown as the initial human-readable format.

### Outside this stage

- Mining cost, extraction yield, mining time, and mining-volume constraints.
- Factory capacity, feasible layouts, power/CPU use, scheduling, and loadouts.
- Batch profitability and capital/rate-of-return planning beyond unit economics.
- A local interactive server or HTML production-tree visualization.
- Per-planet tax rates, customs ownership, and skill-derived effective rates.

Do not treat the absence of capacity modeling as evidence that a production
scenario is executable at unlimited scale. Market-purchased P1 and higher inputs
are the common factory supply case because mining volume is limited.

## Source-price model

A material can have multiple named source prices. A source price is the cost per
unit available off-planet, before import into a downstream production planet.
For manufactured sources, it includes the export required to reach that boundary.
Market purchase prices exclude subsequent planetary import charges.

| Source label | Applies to | Unit-price basis |
| ------------ | ---------- | ---------------- |
| Jita buy | P0-P4 where available | Selected Jita buy-price statistic |
| Jita sell | P0-P4 where available | Selected Jita sell-price statistic |
| Regional ten-day average | P0-P4 where available | Existing regional volume-weighted history-summary average |
| Freely mined with a P1 result | P1 | P1 taxable base value multiplied by the effective tax rate |
| Purchased P0 refined to P1 | P1 | P0 purchase and import costs, divided by recipe output, plus P1 export tax |
| Freely mined with a P2 result | Eligible P2 | P2 taxable base value multiplied by the effective tax rate |
| Manufactured from selected sources | P2-P4 | Explicit recipe inputs, selected source scenarios, and applicable customs movements |

### Simple mining-derived sources

These are labels and values, not mining simulations. Their only price variable
is the effective tax rate:

- Locally mined P0 is free by assumption.
- P0 refined to P1 on its mining planet incurs only the resulting P1 export tax.
- Where both required raw resources are available on one planet, refinement
  through P2 incurs only the resulting P2 export tax.
- No intermediate import/export charges apply to materials retained on that
  mining planet.

With the reference's taxable base values, and `r` expressed as a fraction:

```text
Freely mined with a P1 result = 400 * r
Freely mined with a P2 result = 7200 * r
```

At 10%, these prices are 40 ISK/P1 and 720 ISK/P2. Explicitly label the zero
extraction-cost assumption; these are not opportunity-cost valuations.

Use reviewed reference metadata to identify eligible P2 materials and planet
types. The single-planet P2 table is a starting point, not verified evidence by
itself. Do not offer mining-derived P2 sources for unsupported materials or
substitute zero for an unavailable source. No planet-search engine is required.

### Purchased P0 refining

Include purchasing P0, importing it, refining it to P1, and exporting the P1.
Although uncommon because of taxes, this is required for completeness.

Using the documented 3000 P0 to 20 P1 recipe:

```text
P1 unit cost =
    (3000 * P0 market unit price + 3000 * P0 taxable base * r * 0.5) / 20
    + P1 taxable base * r
```

Calculate this for each selected, available P0 market-price basis.

## Customs boundaries and scenario composition

Apply the documented launchpad customs formulas:

```text
Import tax = imported quantity * taxable base value * r * 0.5
Export tax = exported quantity * taxable base value * r
```

The taxable base is not the material's market price or calculated production cost.
Use quantities and output sizes from the validated recipe data.

For a stage consuming off-planet input sources and exporting its output:

```text
Input acquisition cost = sum(input quantity * selected source unit cost)
Exported output unit cost =
    (input acquisition cost + input import taxes + output export tax)
    / output quantity
```

Keep recipe dependencies distinct from customs movements:

- A P2 made from purchased P1 includes the P1 import charges and P2 export charge.
- If another planet consumes that P2, retain its source cost and add P2 import
  tax exactly once. Do not charge its previous export again.
- If an intermediate is made and consumed on the same planet, charge neither
  intermediate export nor intermediate import. Represent this integrated route
  explicitly rather than assuming every recipe edge is a planetary transfer.
- A recursive recipe alone does not determine where production occurs.

For a P3 requiring P2-A and P2-B, show alternatives such as:

- Purchase both P2 inputs.
- Purchase A and manufacture B from purchased P1.
- Manufacture A from purchased P1 and purchase B.
- Manufacture both, retaining their selected production routes.
- Substitute eligible mining-derived sources or purchased-P0 refining routes
  within those branches.

Preserve the specific upstream scenario identity, not just its cheapest price.
Repeated use of an upstream source can reuse its calculation without losing its
provenance or charging fixed/batch costs that are outside this model.

## Market inputs, precision, and missing data

- Read stored source data without implicit fetching or refresh.
- Reuse existing price and history calculations instead of duplicating them.
- Retain order scope, source response metadata, and history dates/coverage.
  Order and history timestamps must not imply synchronized collection.
- Reuse the ten-day volume-weighted history-summary average. Zero-volume or
  missing history is unavailable pricing, not a free input.
- Warn and render stale inputs; retain unknown freshness as unknown.
- Keep unavailable alternatives visible with an explanation. Missing prices
  invalidate only dependent costs; never rank an incomplete partial sum as a
  complete unit cost.
- Use `Decimal` for monetary calculations. Do not convert through binary floats.
- State sale-price basis and fee assumptions beside profit comparisons. Define
  margin and return-on-cost denominators before implementing those fields.

## Proposed report presentation

Proposed command: `eve-argus reports planetary-interaction`. The name and
report-specific options remain subject to the decisions below.

Markdown should contain:

1. Assumptions, tax rate, source definitions, and freshness/coverage notices.
2. Simple source-price tables, including the mining-derived P1 and P2 values.
3. Best-complete-alternative comparisons per product and price basis.
4. All modeled alternatives, grouped into understandable categories such as
   `From P1`, `From P2`, and `Mixed P1/P2 inputs`.
5. Input source choices, quantities, material and tax breakdowns, and traceable
   production dependencies.
6. Missing-data explanations and visibility of unprofitable alternatives.

JSON and CSV companions are proposed for exhaustive machine-readable results,
not yet confirmed requirements. All formats must use the same collected model.
Markdown must use packaged templates and the existing shared
[`format_markdown()` helper](../../src/pfmsoft/eve_argus/helpers/markdown.py).

Follow established `--to`, `--overwrite`, and `--quiet` conventions. Keep warnings
and errors visible under quiet mode. Preflight destinations and collisions;
collect and render before writing. Do not promise atomic multi-file writes.
Choose deterministic ordering, stable scenario identifiers, and filenames that
distinguish generation time from source timestamps.

## Implementation plan

1. **Validate reference data and worked examples.**
   Reconcile the workbook's mixed-production examples with recipes and customs
   rules. Resolve name inconsistencies using type IDs and explicit mappings.
   Record evidence for mining-derived P2 eligibility.
2. **Build canonical PI data models.**
   Define typed, slotted, keyword-only dataclasses for materials, recipes, source
   prices, scenario references, and customs movements. Prefer reviewed structured
   data over parsing display Markdown on every report run. Validate duplicate
   IDs, missing references, nonpositive quantities, and dependency cycles.
3. **Implement simple source prices and stage costing.**
   Start with mining-derived P1/P2 values and purchased-P0 refining. Implement
   exact recipe costs, output normalization, explicit customs charges, and
   missing-value propagation independently of databases and rendering.
4. **Compose production scenarios.**
   Support independent per-input choices and reusable upstream scenarios.
   Preserve all alternatives rather than pruning to cheapest-only routes.
   Measure exact alternative counts for the full P0-P4 range before committing
   to an exhaustive display strategy; do not silently cap or truncate results.
5. **Connect stored market prices.**
   Select the required Jita order and The Forge history inputs, retaining their
   provenance. Do not require unrelated market hubs. Provide actionable missing
   source diagnostics using verified existing fetch/import commands.
6. **Implement collection, rendering, and CLI integration.**
   Build one typed report model, add Markdown and any approved companion
   formats, register the report, and update directly related help/documentation.
7. **Verify using Red/Green tests.**
   Add focused synthetic fixtures for the acceptance cases below. Mock external
   dependencies and run the smallest relevant pytest selection, then focused
   Ruff lint and format checks. Do not inspect live databases or refresh data as
   an incidental part of development.

## Acceptance criteria

- All supported P0-P4 references resolve to type IDs with valid recipe quantities.
- At 10% customs tax, freely mined P1 costs 40 ISK/unit and eligible freely mined
  P2 costs 720 ISK/unit, with no intermediate customs charges.
- Unsupported mining-derived P2 sources are marked unavailable, not zero-priced.
- With P0 priced at 1 ISK/unit and 10% tax, the documented P0-to-P1 refining route
  costs `(3000 + 600) / 20 + 40 = 220` ISK per exported P1.
- With both P1 inputs priced at 100 ISK/unit and 10% tax, a P2 recipe consuming
  40 of each and producing 5 costs
  `(8000 + 1600 + 3600) / 5 = 2640` ISK per exported P2.
- A downstream consumer of that P2 pays its 2640 ISK source cost plus 360 ISK
  import tax per unit at 10%; its previous export tax is not charged again.
- Explicit same-planet consumption omits both intermediate customs movements.
- A P3 comparison includes buying one P2 and making the other; a P4 example
  combines mining-derived and market-purchased inputs.
- Small synthetic graphs have exact expected alternative counts, stable source
  references, and visible non-cheapest outcomes.
- Missing prices and zero-volume history cannot appear as free inputs or valid
  best-cost results. Stale data remains identifiable without source refresh.
- Summary values agree with detailed inputs/taxes and all approved output formats.
- CLI tests cover registration, invalid settings, overwrite protection, quiet-mode
  warnings, rendering failures, and documented write-failure behavior.

## Decisions to settle before implementation

- Exact Jita order scope and statistic: primary-station buy/sell 5% prices are
  proposed, but not confirmed.
- History-window anchoring, coverage display, and any minimum-coverage policy.
- Whether each market scenario uses one uniform buy/sell/history basis or allows
  market-price bases to mix per input. Mixed production sources and tiers are
  required regardless; this separate policy must not be conflated with them.
- Which integrated same-planet and staged interplanetary production routes to
  enumerate without introducing a factory-layout optimizer.
- Whether all alternatives require separate Markdown rows or can use a compact,
  lossless branching representation, particularly for large P4 chains.
- Whether JSON/CSV companions are required and their exact schemas.
- Continuous normalized unit costing versus whole-run rounding and surplus
  accounting; continuous costing is proposed for this stage.
- Sale fees, profit-margin definitions, precision/display rounding, tie handling,
  product selection defaults, and report-specific CLI options.

This planning update changes documentation only; calculation tests and workbook
reconciliation have not yet been run.
