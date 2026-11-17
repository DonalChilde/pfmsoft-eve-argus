# Planetary Interaction

## Purpose and status

Design and implement reusable calculations and CLI reports for the unit costs of
Planetary Interaction (PI) materials across the full P0-P4 range.

The report should answer:

- What does each material cost under different purchase and production scenarios?
- Which inputs should be purchased, manufactured, or supplied by mining?
- How do import and export taxes affect those choices?
- What profit or loss results when the output is valued using a separately
  selected market-price basis?

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
  formulas before implementing scenario generation. Representative formulas
  have now been inspected; see the implementation status and discrepancies below.
  Its display idioms are not requirements.
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
Prefer documented, typed, slotted, keyword-only dataclasses for data models over
positional tuples, TypedDicts, or loosely typed dictionaries. Use Google-style
`Attributes` sections to explain field semantics, units, customs boundaries, and
missing-value meanings where applicable.

### Implementation status

The first implementation slice supplies:

- A typed, validated catalog of all 83 P0-P4 materials, transcribed from the
  ingredient table with explicit type-ID resolution of reference name aliases.
- Raw-resource planet metadata and derived P1/P2 mining eligibility. All 24 P2
  results agree with the local single-planet table; this is internal reference
  reconciliation, not independent verification against current game data.
- Pure mined-source pricing and explicit-boundary production-stage costing,
  including purchased-P0 refining, mixed sources, unknown-cost propagation,
  uniform market-basis validation, and shared customs-rate validation.
- Reusable source quotes and per-stage material/import/export breakdowns using
  `Decimal`. Callers explicitly choose exported versus locally retained output.
- Focused synthetic tests under
  [`tests/pfmsoft/eve_argus/pi`](../../tests/pfmsoft/eve_argus/pi).

Implementation modules are
[`models.py`](../../src/pfmsoft/eve_argus/pi/models.py),
[`catalog.py`](../../src/pfmsoft/eve_argus/pi/catalog.py), and
[`costing.py`](../../src/pfmsoft/eve_argus/pi/costing.py).

Automatic scenario enumeration, graph storage/traversal, database price adapters,
source-price tables, renderers, and the CLI report remain to be implemented.
This slice makes no choice about enumerating integrated versus staged layouts,
or unresolved report options. The calculation primitive supplies normalized
per-cycle unit costs; whole-run scheduling and surplus accounting remain deferred.

Verification for this slice:

- Red: the new tests initially failed because the PI implementation modules did
  not exist.
- Green: `uv run --no-sync pytest tests/pfmsoft/eve_argus/pi -q` passed 36 tests.
- Focused Ruff lint/format checks passed, and Pylance reported no diagnostics in
  the three implementation modules and two new test modules.
- A read-only comparison matched all 83 recipe rows and all 24 derived P2
  eligibility rows against the local Markdown reference.

Validation used the existing environment without installing dependencies.

### Workbook reconciliation

Read-only inspection of representative workbook formulas confirms that
**What PI To Build** selects per-material sources through **Price Lookup**, which
can refer to calculated **PI Unit Cost** prices. Representative lower-tier
formulas agree with the documented import/export multipliers and output
normalization.

Do not copy the workbook's higher-tier tax formulas without checking their
taxable bases. In **PI Unit Cost**:

- `N73` imports P2 inputs using a base of 400 rather than 7200.
- `O73` exports a P3 output using a base of 7200 rather than 60000.
- `N102` imports P3 inputs using a base of 7200 rather than 60000.

These conflict with the local reference's tier-specific customs bases. The
implementation uses the input material's base for import and the output
material's base for export; it does not reproduce those spreadsheet defects.
The workbook also contains broken defined names and cached/hard-coded values,
so neither cached totals nor all workbook routes have been certified. No workbook
changes or live market requests were made.

## Confirmed scope

- Cover the complete P0-P4 material range.
- Use one configurable effective customs-tax rate across all scenarios for now.
  This is a convenience, not a model of every possible in-game tax arrangement.
- Market-price inputs include Jita buy 5%, Jita sell 5%, and a regional ten-day
  history-summary price.
  The history price is The Forge regional data, not a station-specific average.
- Anchor history summaries to the most recent available ten-day period, reusing
  existing window-selection functions where applicable.
- Each scenario uses one market-price basis for all purchased inputs, including
  purchases in upstream manufacturing scenarios. Do not mix buy, sell, and
  history market-price bases within one production scenario.
- Select one output valuation basis separately from the input market-price
  basis. For example, acquire inputs at Jita sell 5% and compare the resulting
  unit cost with Jita buy 5%.
- Support mixed input tiers and sources within the same recipe.
- Preserve all modeled outcomes, including suboptimal, unprofitable, and
  incomplete alternatives. External constraints may justify a non-cheapest choice.
- Highlight the cheapest complete alternative without replacing the other results.
- Allow a scenario's calculated unit price to supply an input to another scenario.
- Support small operations combining mining-derived and purchased materials.
- Produce a CLI report with Markdown as the initial human-readable format.
- Use compact branching representations to make all alternatives inspectable
  without requiring a separate flat Markdown row for every complete combination.
- Exclude sales tax and transport fees from this stage's calculations, and state
  those exclusions beside profit/loss comparisons.

### Outside this stage

- Mining cost, extraction yield, mining time, and mining-volume constraints.
- Factory capacity, feasible layouts, power/CPU use, scheduling, and loadouts.
- Batch profitability and capital/rate-of-return planning beyond unit economics.
- A local interactive server or HTML production-tree visualization.
- Per-planet tax rates, customs ownership, and skill-derived effective rates.

Do not treat the absence of capacity modeling as evidence that a production
scenario is executable at unlimited scale. Market-purchased P1 and higher inputs
are the common factory supply case because mining volume is limited.

### Notional production facilities

Planets and factories can be notional for unit-cost calculations, but customs
movements must remain explicit. Notional facilities do not imply free transfers
between planets.

The user identifies a capacity caveat for P4 made from all P1: a single planet
cannot fit enough factories for one P4 unit per hour, but can support one every
two hours. Retain this constraint for later throughput/profit-per-hour work;
do not apply it as a multiplier to per-unit material or customs costs. Verify its
product/route applicability before implementing hourly estimates.

If investigation reveals other cases where actual planet or factory constraints
change the unit-cost result, surface them to the user before choosing a workaround
or expanding into layout optimization. Factory layouts remain deferred unless
such a dependency requires revisiting the scope.

## Source-price model

A material can have multiple named source prices. A source price is the cost per
unit available off-planet, before import into a downstream production planet.
For manufactured sources, it includes the export required to reach that boundary.
Market purchase prices exclude subsequent planetary import charges.

| Source label                       | Applies to            | Unit-price basis                                                                    |
| ---------------------------------- | --------------------- | ----------------------------------------------------------------------------------- |
| Jita buy 5%                        | P0-P4 where available | Existing Jita buy 5% price statistic                                                |
| Jita sell 5%                       | P0-P4 where available | Existing Jita sell 5% price statistic                                               |
| Regional ten-day average           | P0-P4 where available | Existing regional volume-weighted history-summary average                           |
| Freely mined with a P1 result      | P1                    | P1 taxable base value multiplied by the effective tax rate                          |
| Purchased P0 refined to P1         | P1                    | P0 purchase and import costs, divided by recipe output, plus P1 export tax          |
| Freely mined with a P2 result      | Eligible P2           | P2 taxable base value multiplied by the effective tax rate                          |
| Manufactured from selected sources | P2-P4                 | Explicit recipe inputs, selected source scenarios, and applicable customs movements |

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
Within a downstream scenario, the P0 purchase basis must match that scenario's
other market purchases.

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

Mixed sourcing means choosing market purchase, mining-derived supply, or an
explicit manufacturing route independently for each input. It does not mean
mixing different market-price bases: all market-purchased leaves in a scenario
share the selected input basis. Reused upstream scenarios must be compatible with
that basis and the shared customs-tax rate.

## Market inputs, precision, and missing data

- Read stored source data without implicit fetching or refresh.
- Reuse existing price and history calculations instead of duplicating them.
- Retain order scope, source response metadata, and history dates/coverage.
  Order and history timestamps must not imply synchronized collection.
- Reuse the ten-day volume-weighted history-summary average. Zero-volume or
  missing history is unavailable pricing, not a free input.
- Include average daily traded volume in the history input table for all
  materials and output products covered by the report, even when input and
  output prices use order data. Reuse the helper's full-window denominator:
  total observed traded units
  divided by ten calendar days, with missing days contributing zero to that
  average and missing-day coverage displayed separately. Distinguish unavailable
  history from a known zero-volume summary. Label the metric as The Forge
  regional units/day, not Jita station volume, factory throughput, or expected
  sales for this operation.
- Select the most recent available ten-day calendar period using existing
  history-window helpers where applicable. Record the actual anchor, dates, and
  missing-day coverage; do not silently substitute ten nonconsecutive trading
  days or force a window ending yesterday. Verify whether the appropriate
  existing selection policy anchors per region or per type before integration,
  and document the resulting behavior.
- Warn and render stale inputs; retain unknown freshness as unknown.
- Keep unavailable alternatives visible with an explanation. Missing prices
  invalidate only dependent costs; never rank an incomplete partial sum as a
  complete unit cost.
- Use `Decimal` for monetary calculations. Do not convert through binary floats.
- Keep input acquisition basis and output valuation basis distinct in scenario
  identity, report metadata, and comparisons. A scenario has one of each; they
  may differ.
- Calculate per-unit profit/loss as selected output valuation minus exported
  output unit cost, excluding sales tax and transport fees. Label this as a
  comparison on the stated price bases, not an after-all-fees return or a fill
  forecast. Define margin and return-on-cost denominators before implementing
  those percentage fields.

## Proposed report presentation

Proposed command: `eve-argus reports planetary-interaction`. The name and
report-specific options remain subject to the decisions below.

Markdown should contain:

1. Assumptions, tax rate, source definitions, and freshness/coverage notices.
   Include the input market-price basis, separate output valuation basis, and
   explicit exclusions for sales tax and transport fees.
2. Source-price tables covering all materials and output products used by the
   report, not only those selected by the cheapest scenario:
   - A Jita buy 5% table and a separate Jita sell 5% table, each showing type ID,
     material name, PI tier, unit price in ISK, and source scope/freshness.
   - A The Forge ten-day history-summary table showing type ID, material name,
     PI tier, average unit price in ISK, average daily traded volume in regional
     units/day, actual window dates, coverage, and freshness.
   - Simple calculated source-price tables, including mining-derived P1/P2 and
     purchased-P0 refining values, with the applicable tax rate and price basis.
   Use one row per material per source table and deterministic ordering. Shared
   metadata can appear above a table; retain per-material differences where
   applicable. Show unavailable inputs explicitly rather than omitting rows.
   Displayed prices must match the values used by the calculations, subject only
   to stated presentation rounding.
3. Best-complete-alternative comparisons per product and price basis. The
   history-summary input table satisfies the average daily volume requirement;
   repeating volume in this comparison is optional. Volume is shared market
   context, not an additive scenario total or a daily-profit forecast.
4. All modeled alternatives in compact branching representations, grouped into
   understandable categories such as `From P1`, `From P2`, and
   `Mixed P1/P2 inputs`. Label branch choices and reusable sub-scenarios clearly;
   preserve enough detail to reconstruct each complete outcome.
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
   Enforce one market-price basis across all purchased leaves and retain a
   separately selected output valuation basis.
   Preserve all alternatives rather than pruning to cheapest-only routes.
   Measure exact alternative counts for the full P0-P4 range and prototype
   compact branching displays on representative P3/P4 chains. Do not silently
   cap or truncate results. Keep facilities notional while preserving customs
   boundaries; surface discovered capacity dependencies that change unit costs.
5. **Connect stored market prices.**
   Select Jita buy/sell 5% prices and The Forge's most recent available ten-day
   history-summary inputs, retaining provenance and coverage. Reuse existing
   history-selection functions where applicable; verify their anchor semantics.
   Collect the buy/sell price references and history metrics for all materials
   and output products covered by the source tables, including average daily
   volume when acquisition and output valuation both use order prices. Keep
   optional reference-data gaps from invalidating unrelated scenario costs.
   Do not require unrelated market hubs. Provide actionable missing source
   diagnostics using verified existing fetch/import commands.
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
- Compact branches preserve every modeled combination and its source choices;
  best-cost highlighting must not hide more expensive alternatives.
- A scenario using Jita sell 5% values every market-purchased leaf, including
  upstream P0 purchases, on that basis. A reused buy-5%-based upstream scenario
  cannot silently enter the same input-cost calculation.
- Given a synthetic exported output cost of 100 ISK from sell-5%-valued inputs
  and an output buy-5% valuation of 120 ISK, per-unit profit is 20 ISK. No sales
  tax or transport fee is deducted, and both bases and exclusions are displayed.
- History fixtures select the most recent available ten-day calendar window
  under the documented anchoring policy, preserving gaps rather than stretching
  the window to collect ten trading days.
- A ten-day history fixture with 1000 total observed traded units and two missing
  days displays 100 units/day in the history-summary input table, with coverage
  of 8/10 days. This also applies when both price bases use Jita order data. Missing
  history displays unavailable volume, while a known zero-volume summary
  displays zero; neither implies an executable daily sales target.
- Separate buy-5%, sell-5%, and history-summary tables cover every material and
  output product used by the report, including sources not selected by the best
  scenario. Prices agree with calculation inputs, identities and ordering are
  stable, and missing references remain visible without invalidating scenarios
  that do not depend on them.
- No hourly profit or factory-throughput claims are inferred from unit costs.
  The all-P1-to-P4 capacity caveat does not double the per-unit material cost.
- Missing prices and zero-volume history cannot appear as free inputs or valid
  best-cost results. Stale data remains identifiable without source refresh.
- Summary values agree with detailed inputs/taxes and all approved output formats.
- CLI tests cover registration, invalid settings, overwrite protection, quiet-mode
  warnings, rendering failures, and documented write-failure behavior.

## Decisions to settle before implementation

- Exact Jita order scope: primary-station scope is proposed, but not confirmed.
  Buy/sell 5% statistics are confirmed.
- History coverage display and any minimum-coverage policy. The most recent
  available ten-day period is confirmed; verify the existing region/type anchor
  semantics as part of implementation.
- Which integrated same-planet and staged interplanetary production routes to
  enumerate without introducing a factory-layout optimizer.
- Exact compact branching layout, navigation, and how complete outcomes and
  their costs are reconstructed without expanding every combination into a row.
- Whether JSON/CSV companions are required and their exact schemas.
- Continuous normalized unit costing versus whole-run rounding and surplus
  accounting; continuous costing is proposed for this stage.
- Profit-margin definitions, precision/display rounding, tie handling, product
  selection defaults, and report-specific CLI options. Sales tax and transport
  fees are explicitly excluded for now; identify any other proposed fee before
  including it rather than silently adding costs.

Focused calculation tests now cover the first implementation slice. Full report
acceptance, exhaustive scenario counts, and complete workbook reconciliation
remain pending; they must not be inferred from the foundation tests passing.
