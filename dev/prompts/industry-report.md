# Industry Report

## Purpose and status

Design and implement an auditable EVE Argus industry report that answers:

- What does it cost to manufacture a product using corporation-owned blueprints?
- Which copying, invention, subassembly, and final manufacturing steps are needed,
  and what does each step cost and how long does it take?
- What profit or loss would result from selling the output at the trade hubs,
  using buy 5%, sell 5%, and market-history average prices?

This document separates the report contract from the reusable game-mechanics
reference in [Industry calculations](./Industry-calculations.md). Keep formula
evidence and in-game comparisons there; define report selection, composition,
valuation, presentation, and acceptance criteria here.

This is a design prompt, not authorization to implement unresolved policies.
Settle the decisions below before committing to behavior or public APIs.

## Established requirements

- Use corporation-owned BPO blueprints.
- Manufacture from BPCs, not directly from BPOs. Include the time and cost of
  copying the source BPO in production estimates, including input copies for
  invention. Represent required BPCs alongside materials in the job input list.
- Select the best material efficiency (ME), then the best time efficiency (TE),
  for each required blueprint type. Preserve the ME/TE pair from one actual
  blueprint item; do not combine maxima from different items.
- Produce a manufacturing cost breakdown and estimated cost per produced unit.
- List the production steps with their costs and durations, including blueprint
  copying for invention and BPC-based manufacturing,
  invention, required subassemblies, and final manufacturing.
- Compare sale outcomes using buy 5%, sell 5%, and market-history average prices
  for each trade hub.
- Make the production dependency tree a required report feature, not an optional
  later enhancement.
- Separate game mechanics, economic assumptions, data access, and rendering.
- Keep missing inputs and provisional mechanics visible. An incomplete estimate
  must not appear to be a complete quote.
- Produce a comparison CSV with product identity, unit cost, portion size,
  average daily sales, profit, and percentage return across the major hubs.
  Compare production strategies on separate rows.
- Produce Markdown and HTML companions telling the detailed production and
  economic story for each manufactured item.
- Base unit-cost comparisons on ten manufacturing runs, except T2 ships and
  rigs: use the single licensed run on one newly invented BPC.
- Exclude decryptors and decryptor comparisons from this report. Invented T2
  BPCs use the base ME2/TE4 and licensed-run counts.
- Value all purchased inputs, including datacores and purchased components, at
  the Jita primary station's sell 5% boundary. Keep this acquisition basis fixed
  across production strategies and destination sale hubs.

### First-proof production profile

- **System:** Osmeden. Resolve its system ID from static data and select its
  stored activity-specific cost indices; do not substitute Jita's indices
  merely because inputs are valued there.
- **Facility:** High-security NPC station for copying, invention, and
  manufacturing. Apply no player-structure or fitted-rig bonuses. Identify
  suitable station service availability before claiming an executable plan.
- **Character:** All relevant skills at level 5, including manufacturing,
  copying, and invention skills. This is an explicit scenario, not fetched
  character data; it does not imply researched BPO ME/TE.
- **Implants:** None; apply no implant bonuses.
- **Clone state:** Omega, explicitly selected for this proof; no Alpha
  restrictions or Alpha job surcharge.
- **Job taxes:** Use the activity-specific rates documented in
  [Industry calculations](./Industry-calculations.md#current-activity-specific-surcharge-rates):
  NPC facility tax 0.25% and SCC surcharge 4% for manufacturing, copying, and
  invention. Use the reference comparisons' Omega profile, with no Alpha
  surcharge. The reference's 2% SCC is for ME/TE research, not these production
  activities. Retain the reference's user-confirmed rates and evidence status
  rather than claiming new verification.
- **Reactions:** No reaction-making capability. Purchase reaction-produced
  inputs at Jita sell 5%, including in `make-all-inputs`, and mark them as
  externally sourced because the facility cannot run reactions.
- **Sale fees:** Retain explicit `sales_tax_rate` and `broker_fee_rate` fields,
  both set to 0% for the proof. Display both rates in report assumptions and
  label profits as calculated with zero sale fees, not as realistic after-tax
  returns. Do not remove the fee fields or calculation slots.

### First-proof scope and accounting

- Select representative products from corporation-owned BPO routes, including
  T1/T2 products, a manufactured-component chain, and a T2 ship or rig.
  Exclude T3.
- Compare only `buy-all-inputs` and `make-all-inputs`; cost optimization is
  deferred. Missing required BPOs leave make-all-inputs incomplete, except that
  reaction inputs are explicitly purchase-only.
- Ignore existing BPCs and material inventory. Model newly copied/invented BPCs
  and value all external materials at Jita sell 5%.
- Combine intermediate demand within each product/strategy, manufacture whole
  runs, charge the full batch cost to the final output, and show surplus without
  credit. Do not share production costs across independently compared products.
- Exclude historical BPO purchase/research expenses and hauling.
- Report job durations and dependencies, not an elapsed production schedule.
- Calculate return as profit divided by production cost, assuming sale of the
  entire reference batch.
- Produce one comparison CSV and combined Markdown and HTML companions.
- Summarize the most recent available ten-day history window, rather than a
  fixed window ending yesterday. Retain the actual date range and coverage per
  region/type; windows need not share an anchor. Use the existing history
  summary helper where applicable. Exact gap/coverage handling must remain
  visible rather than presenting unavailable history as zero trading.

Use rounded-up expected invention attempts: budget `ceil(1 / p)` attempts per
required successful BPC, where `p` is the final invention success probability.
This is a report costing convention, not a confidence-based batch plan.

The zero sale-fee assumption does not waive copying, invention, or manufacturing
installation charges. Use applicable NPC job charges and Osmeden cost indices.
Apply each charge to its activity-specific valuation basis from the mechanics
reference, not indiscriminately to material purchase cost or SCI-adjusted fees.
Keep the rates explicit in the proof inputs and report assumptions. Exact
station service availability still requires verification.

Owned blueprints do not imply free materials or zero copying/invention charges.
Treatment of historical blueprint purchase and research expenses remains an
economic policy decision.

## Scope and terminology

Distinguish product type IDs, blueprint type IDs, and blueprint item IDs.
Manufacturing runs, invention attempts, copy count, licensed runs per copy, and
product units are separate quantities.

Although the game permits direct BPO manufacturing, this report assumes a
BPC-only workflow. BPOs supply copying jobs; manufacturing consumes licensed
runs from copied or invented BPCs. A copied BPC preserves the selected source
BPO's actual ME/TE. Invention consumes input BPC runs and produces successful
output BPCs with base invention attributes; input BPO ME/TE does not transfer
to an invented blueprint.

Ordinary T1/T2 manufacturing and invention are the best-supported initial scope,
but this is a proposed first slice, not a confirmed restriction. Reactions are
purchase-only under the first-proof facility profile; decide T3 coverage
explicitly. Price inputs outside supported blueprint
production externally; do not expand this report into mining, planetary industry,
reprocessing, resource extraction, or hauling-route modeling.

## Current implementation evidence

Assessment as of 2026-11-03; re-check current code before implementation.

| Surface                                                                                                                                          | Available foundation                                                                                                     | Remaining report work                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| [Static blueprint data](../../src/pfmsoft/eve_argus/static/read.py) and [models](../../src/pfmsoft/eve_argus/static/models.py)                   | Recipes, activity times, products, skills, invention probabilities, copy limits                                          | Product-to-blueprint and invention-route resolution; supported-family validation         |
| [Corporation blueprint data](../../src/pfmsoft/eve_argus/dynamic/models.py) and [report](../../src/pfmsoft/eve_argus/reports/corp_blueprints.py) | BPO/BPC classification, actual instances, ME/TE, remaining runs, best-original selection                                 | Production-specific selection, copy-use policy, availability and run allocation          |
| [Industry formulas](../../src/pfmsoft/eve_argus/calculations/industry_formulas.py)                                                               | Manufacturing, copying, invention, research, itemized fees, expected invention cost, confidence for at least one success | Composed jobs, production trees, economic allocation, multi-success planning if required |
| [Dynamic readers](../../src/pfmsoft/eve_argus/dynamic/read.py)                                                                                   | Stored adjusted prices, cost indices, orders, corporation blueprints and jobs                                            | Explicit snapshot orchestration and normalized formula inputs                            |
| [Order summaries](../../src/pfmsoft/eve_argus/dynamic/order_summary.py)                                                                          | Station-scoped buy/sell 5% prices and depth                                                                              | Material valuation policy and product sale scenarios                                     |
| [History summaries](../../src/pfmsoft/eve_argus/market_history/history_summary.py)                                                               | Regional volume-weighted historical average prices                                                                       | Agreed history window and coverage rules                                                 |
| [Report commands](../../src/pfmsoft/eve_argus/cli/reports/__init__.py)                                                                           | CLI and JSON/CSV/Markdown patterns                                                                                       | Industry command, collector, typed result, renderers, templates and integration tests    |

No industry report or production-chain resolver is currently registered.
Character skills, clone state, implants, facility taxes, structure/rig modifiers,
and installation access are not supplied by the current fetch commands. Resolve
them through explicit scenario inputs or separately approved adapters.

The assessment used source and synthetic tests, not live databases. Actual stored
snapshot completeness and coverage have not been verified.

## Input contract and provenance

The report needs explicit inputs for:

- Corporation and requested product scope.
- Requested product quantities or manufacturing runs.
- Owned blueprint inventory and any relevant job availability information.
- Static blueprint recipes, type identities, and activity metadata.
- Character skill levels, clone state, and applicable implants.
- Facility/system per activity, applicable modifiers, and facility taxes.
- Activity-specific system cost indices and CCP adjusted prices.
- Jita primary-station sell 5% prices for purchased materials and datacores.
- Hub order snapshots and regional market-history windows.
- Sale taxes, broker/relisting fees, and any separately modeled overhead.

Use stored source data without implicit fetching or refresh. Resolve the latest
snapshot independently for each scope and retain its response metadata linkage.
History is selected by region, product type, and date window; retain receipt
metadata and coverage for the records actually used.

Record source timestamps and freshness separately for blueprint inventory,
prices, cost indices, orders, history, and static data. One timestamp must not
imply that all inputs were collected together.

Stale sources warn and remain usable as estimates; unknown expiry remains unknown.
Missing required data must identify the relevant preparation step. Existing fetch
commands include:

- `eve-argus fetch corporation-blueprints`
- `eve-argus fetch corporation-jobs`, if availability is modeled
- `eve-argus fetch markets-prices`
- `eve-argus fetch industry-systems`
- `eve-argus fetch market-orders`
- `eve-argus fetch market-history`

Check current command options and static-import preparation before documenting
complete invocation examples. Specify any network-based name enrichment
separately; no snapshot refresh does not necessarily mean fully offline operation.

## Production planning and calculations

### Dependency resolution

- Resolve the selected product's manufacturing route and any invention route.
- Select actual owned blueprint instances using the agreed BPO/BPC policy.
- Expand required subassemblies recursively under the agreed build-versus-buy
  rule. Detect cycles, ambiguous routes, and missing blueprints explicitly.
- Convert demand into whole runs using output quantity per run. Show actual
  output and surplus.
- Respect BPC remaining runs and copy limits when splitting jobs.
- Preserve dependencies and blueprint-instance references for every step.
- Define whether shared intermediate demand is combined into jobs or kept
  separate. Apply material rounding to each actual planned job, never to the
  entire tree as if it were one job.

### Cost accounting

Use the Jita primary station defined in `MARKET_HUBS` for all external input
valuations. Use the existing sell 5% boundary statistic, not the lowest sell
order or a volume-weighted execution price. This includes purchased
subassemblies in `buy-all-inputs`, terminal materials in `make-all-inputs`, and
invention consumables. Built intermediates retain their allocated production
cost rather than a Jita market value. Missing Jita sell prices make the affected
estimate incomplete; do not substitute another hub, buy prices, history, or zero.
This is indicative valuation, not proof the required quantity is available at
that price. CCP adjusted prices remain the separate basis for EIV.

For each job, show materials and individual installation charges, including their
valuation basis and applied modifiers. EIV uses unmodified recipe quantities and
CCP adjusted prices; it is not the material purchase cost.

Roll costs through the dependency graph without double counting. A built
intermediate contributes its allocated production cost, not that cost plus its
market purchase value. Separately expose external shopping-list costs and
internal transfers.

Define allocation for surplus, unused BPC runs, copying batches, and invention.
Show the denominator used for every per-unit allocation.

List each required BPC as a blueprint input with blueprint type, source BPO or
invention step, ME/TE, copy count, licensed runs, runs consumed, remaining runs,
and allocated acquisition cost. Planned copies have traceable step IDs, not
fabricated owned item IDs. Keep blueprint inputs distinguishable from ordinary
recipe materials; adding them to the report does not modify the static recipe or
add BPC value to manufacturing EIV.

For ordinary copied manufacturing BPCs, include BPO copying charges and duration.
For invented T2 BPCs, include source BPO copying, invention inputs/charges, and
failure consumption under the agreed allocation policy. Do not invent a T2 BPO
copying step: the successful T2 BPC is produced by invention.

A BPC's allocated acquisition cost is an internal transfer from the copy or
invention step. Charge it once in the rolled-up unit cost, not once as a material
and again as the upstream job cost. Show copying duration as a dependency even
when scheduling is not modeled; an invented BPC's manufacturing TE does not
replace the source BPO's copying-time calculation.

The report-level reconciliation is:

`allocated production cost = allocated external inputs + allocated job fees

- allocated blueprint/copy/invention costs + included overhead`

`estimated unit cost = allocated production cost / attributed product units`

Define attributed product units and residual value explicitly. Do not divide a
batch cost by requested quantity when the allocation policy attributes it to a
different actual output.

Market amounts currently use `Decimal`, while the reference industry formulas use
floats. Set an explicit conversion, precision, and rounding contract before
integration. Preserve monetary precision in report economics and distinguish
unrounded estimates from displayed game-fee rounding.

### Invention

- User-specified baseline for invented T2 BPCs: ME 2%, TE 4%;
  ships and rigs have one licensed manufacturing run, other supported T2
  products have ten. Decryptors are excluded: do not apply decryptor modifiers
  or add decryptor input costs. These are report assumptions to validate
  against current static data and mechanics fixtures before implementation,
  not evidence of completed mechanics verification.
- Show base probability, skills, final probability, consumed inputs,
  per-attempt costs/time, and successful BPC runs/ME/TE.
- Include failure consumption and input-copy costs in invention allocation.
- Distinguish long-run expected unit cost from finite-batch spending and outcomes.
- For this report, round expected attempts up per required successful BPC:
  `attempts_per_bpc = ceil(1 / p)`. For `k` required successful BPCs, budget
  `k * attempts_per_bpc` attempts, retaining per-BPC rounding rather than rounding
  only after aggregation. Charge copying for the consumed input runs, datacores,
  invention installation charges, and attempt durations for all budgeted
  attempts. Copying job limits and rounding still apply to actual copy jobs.
- At `p = 0.4`, show raw expected attempts 2.5 and costed attempts 3. At
  100,000 ISK per attempt including input copying, allocate 300,000 ISK per
  successful BPC, or 30,000 ISK per unit for ten attributed output units.
- Label this **rounded-up expected-attempt cost**, not the exact statistical
  expected cost or a guaranteed production quote. Rounding does not guarantee
  success: three independent attempts at 40% success still have a 21.6% chance
  of zero successes. Do not treat extra possible successes as guaranteed surplus
  or reduce the cost denominator using them.
- Reject invalid probabilities; zero success probability makes the route
  unavailable rather than yielding an infinite or zero-cost estimate.
  Confidence-based batch planning and retry scheduling are outside this proof.
- State "No decryptors" once in the report assumptions; do not generate
  decryptor profiles or comparison tables.

### Unit-cost reference batches

Use these user-selected manufacturing batch rules:

| Product family | Reference manufacturing runs |
| -------------- | ---------------------------- |
| Ordinary supported products, including non-ship/non-rig T2 products | 10 |
| T2 ships and rigs | 1, the full licensed runs of the base invented BPC |

Ten runs means ten manufacturing runs, not ten units or ten BPCs. Compute actual
output as runs times recipe output units per run, and calculate unit cost using
the declared attributed output and allocation policy. For non-ship/non-rig T2
products, the ten-run reference uses all ten licensed runs of a base invented
BPC.

The ten-run reference is intended to reduce per-unit material-rounding overhead.
It is not a universal guarantee of the mathematically best material efficiency.
Apply ME/facility reductions and integer rounding per actual job, with each job
bounded by its BPC's licensed runs and applicable limits. Do not price a ten-run
T2 ship/rig job using a one-run BPC as though material rounding were shared.

Keep the reference batch distinct from a future user-requested production
quantity. Combine dependency demand within the product/strategy and round to
whole intermediate runs; charge the full batch cost with no surplus credit.
Copy-limit job splitting and unused BPC-run allocation still need explicit
mechanics consistent with that policy. Do not independently force every
intermediate to ten runs irrespective of required demand.

### Time

Show duration for every job and dependencies between jobs. Report total job-hours
separately from elapsed completion time.

Elapsed time needs an explicit scheduling policy covering parallel job slots,
shared BPO use, copy/invention sequencing, and retries. If scheduling is outside
the first slice, report durations and dependencies without claiming a completion
time. Patient market fills are not predicted from production duration.

## Trade-hub profitability

Use the hubs and primary stations defined in
[MARKET_HUBS](../../src/pfmsoft/eve_argus/models/market_hubs.py).

For each product and hub, produce three named sale-price scenarios:

1. **Buy 5%:** indicative sale into buy orders.
2. **Sell 5%:** indicative sell-order listing scenario.
3. **Regional history average:** historical comparison using the hub's region.

The existing 5% statistic is the price boundary reached by the best 5% of filtered
remaining order-book volume, not a volume-weighted average. Retain scope, outlier
filter policy, depth, and missing-side information.

Market history is regional, not station- or system-specific. Label it as the
hub's regional proxy, never as an observed historical hub price. Use an agreed
window and state whether the average is volume-weighted; the existing helper is
volume-weighted over daily average prices.

For each scenario, show:

- Price per unit and modeled quantity.
- Gross revenue, applicable sale fees, and net proceeds.
- Allocated production cost, profit/loss per unit, and total profit/loss.
- Profit margin with its denominator stated.
- Price provenance, freshness, depth, and unavailable-price flags.

`profit = gross revenue - applicable sale fees - allocated production cost`

The three prices are sale scenarios, not material purchasing policies. Keep
external acquisition costs at Jita sell 5% for every destination hub and sale
scenario; acquisition-location comparisons are outside this report.

A 5% price is not proof that the entire batch can execute at that price.
Buy-order range/minimum-volume constraints and quantity-aware execution need
separate handling if executable quotes are required. Sell and history scenarios
are not fill guarantees.

Missing prices remain unknown, not zero. Zero-volume history must not become a
valid zero-ISK sale price merely because the current summary helper returns zero
for that condition.

## Production strategy comparisons

Production strategy and sale-price basis are independent dimensions. Apply the
same requested output, character/facility profile, external-input valuation, sale
fees, and allocation rules to each strategy so differences can be explained.
Acquisition is fixed at Jita sell 5%; do not create acquisition-hub profiles.
Changing a facility creates a separately identified profile, not a silent change
between strategies.

Include these strategies:

- **`buy-all-inputs`:** Manufacture the final product, purchasing its direct
  recipe inputs, including otherwise manufacturable subassemblies. Include any
  copying/invention required to obtain the final manufacturing BPC; this
  is not a buy-the-finished-product scenario.
- **`make-all-inputs`:** Manufacture the final product and recursively manufacture
  supported manufacturable inputs under the agreed blueprint-access policy.
  Purchase terminal inputs and inputs outside supported production families.
  Missing required blueprints or unresolved routes leave the strategy explicitly
  incomplete; do not silently turn it into `buy-all-inputs`.

An optional **`cost-optimized-inputs`** strategy could select build or buy for
each eligible intermediate using comparable fully allocated costs. Adopt it only
after defining surplus, shared-demand, blueprint availability, and invention
allocation: choosing the cheapest isolated component is not necessarily the
cheapest whole batch. Other strategies need a distinct decision they help answer,
not merely another label for the same plan.

Show the external shopping list and production tree for each strategy. In the
buy strategy the tree stops at purchased inputs; in the make strategy it expands
through manufactured inputs to purchased leaves.

## Output contract

CSV, Markdown, and HTML are requested report-specific outputs. CSV is the compact
comparison; Markdown and HTML are detailed companions. Existing reports provide
CSV/Markdown foundations, but HTML needs a new renderer and packaged template.
JSON and additional step/shopping-list CSVs are optional, not required artifacts.

Build one canonical typed result and render all formats from it.

### Comparison CSV

Proposed layout: one row per product, production strategy, and explicit
production/acquisition profile. Use repeated hub column groups for Jita, Amarr,
Dodixie, Hek, and Rens, in `MARKET_HUBS` order. Within each hub group, repeat
sale-outcome columns for `buy_5pct`, `sell_5pct`, and `history_average`. This keeps
production alternatives on separate rows while allowing side-by-side hub
comparison without conflating production strategy with sale-price basis.

The proposed leading columns are:

`type_id,name,production_strategy,profile_id,portion_size,output_units_per_run,reference_manufacturing_runs,requested_units,produced_units,surplus_units,allocated_cost,unit_cost,status,detail_anchor`

- `type_id` and `name` identify the manufactured product, not its blueprint.
- Proposed `portion_size` means the static type's portion size;
  `output_units_per_run` separately records manufacturing recipe output.
  Confirm this terminology before implementation; these values must not be
  assumed interchangeable.
- `unit_cost` is ISK per attributed produced unit under the declared allocation
  policy, not cost per manufacturing run or per static portion.
- `reference_manufacturing_runs` exposes the ten-run default or the full invented
  BPC run count of one for T2 ships/rigs.
- `profile_id` identifies the explicit acquisition/production assumptions.
  `status` exposes incomplete estimates; `detail_anchor` locates the matching
  item/strategy section in both detailed companions.

For each hub prefix, include:

`{hub}_region_id,{hub}_station_id,{hub}_avg_daily_sales,{hub}_history_start,{hub}_history_end,{hub}_history_days_present,{hub}_history_days_requested`

Average daily sales means regional traded **units per day**, not order count,
hub-local sales, or a forecast of this corporation's sales. Proposed calculation:
total observed volume divided by requested calendar days, matching the existing
history summary's full-window denominator. Expose missing-day coverage rather
than treating absent records as confirmed zero-trade days. No usable history
means an empty value; an observed, complete zero-volume window can report zero
sales but cannot supply a valid historical sale price.

For each hub and sale-price basis, include:

`{hub}_{basis}_sale_price,{hub}_{basis}_net_proceeds_per_unit,{hub}_{basis}_profit_per_unit,{hub}_{basis}_total_profit,{hub}_{basis}_return_pct,{hub}_{basis}_status`

Proposed economic definitions:

- `profit_per_unit = net_proceeds_per_unit - unit_cost`.
- `total_profit` uses the explicitly modeled sale quantity and reconciles with
  allocated cost and fees in the detailed report.
- `return_pct = 100 * total_profit / allocated_cost` for the same attributed
  quantity. This is return on production cost, not revenue-based profit margin.
  With zero or unknown allocated cost, return is unknown and flagged, not
  infinity or zero. If only part of the output is sold, use its allocated cost
  and expose the unsold output separately.

Use empty CSV cells for unknown numeric values, never fabricated zeros. Preserve
rows for unavailable strategies and hub prices with explicit statuses. Define
display precision before implementation and calculate with unrounded monetary
values. Use standard CSV quoting for names and other text. Proposed ordering is
product type ID, fixed strategy order above, then profile ID.

### Detailed Markdown and HTML

Proposed packaging: one Markdown file and one self-contained HTML file per
report run, each with an index and a stable section anchor for every product and
strategy/profile. Whether to split these into per-item files remains an artifact
packaging decision.

Each manufactured item's story includes:

1. Product identity, portion size, recipe output per run, requested/actual output,
   surplus, completeness, and the strategy comparison.
2. Selected source BPOs, copied/invented BPC attributes and licensed runs,
   reference manufacturing runs, character/facility assumptions, and why each
   input is purchased or manufactured.
3. The production dependency tree, ordered jobs, inputs/outputs, copying and
   invention decisions, and per-step durations.
4. Itemized material and job costs, shopping list, internal transfers, allocation
   denominators, and reconciliation to the CSV unit cost.
5. Side-by-side hub outcomes for all three sale-price bases, regional average
   daily sales and history coverage, sale fees, profit, and return on cost.
6. Risks and caveats: invention uncertainty, surplus, depth/fill limitations,
   omitted costs, missing inputs, and source-specific provenance/freshness.

Both companions must tell the same story and agree with the CSV, not calculate
independently. Keep calculations out of templates. Format Markdown through the
shared [Markdown formatter](../../src/pfmsoft/eve_argus/helpers/markdown.py).
HTML must use autoescaping, accessible table headings, internal navigation,
readable embedded styling, and no external asset/network dependencies.

The canonical model needs these views, whether or not separately exported:

| View                       | Grain and contents                                                                                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Product summary            | Product/scenario, requested and actual output, surplus, total allocated cost, estimated unit cost, completeness                                        |
| Production steps           | Job ID, dependency IDs, activity, blueprint type/item, ME/TE, runs/copies/attempts, inputs/outputs, modifiers, fee breakdown, allocated cost, duration |
| Shopping list              | External input type, required quantity, price policy/location, unit price, total value, missing-price status                                           |
| Invention detail           | Route, probability without decryptors, BPC attributes, attempt policy, expected allocation and any finite-batch risks                                    |
| Hub profitability          | Product/strategy/profile, hub/station/region, three sale scenarios, fees, net proceeds, profit/loss, return on cost, depth, daily sales and history coverage |
| Assumptions and provenance | Input metadata, rules evidence status, valuation/allocation/scheduling policies, omitted costs, warnings                                               |

Finalize headers, precision, stable anchors, filenames, and packaging before
coding. If additional CSV views are adopted, keep their distinct grains separate
from the primary comparison CSV.

## CLI and architecture

Proposed command: `eve-argus reports industry`. Confirm the command name and
selection interface when the scope is settled.

- Reuse the current report conventions for corporation selection, `--to`,
  `--overwrite`, `--quiet`, stale warnings, actionable errors and nonzero exits.
- Keep snapshot orchestration in the CLI/integration layer.
- Keep game formulas in the reference module and production/economic composition
  separate from rendering.
- Return typed results with traceable step IDs, sources, assumptions and status.
- Render before writing and preflight output collisions. Do not promise atomic
  multi-file writes unless implemented.
- Do not use the legacy
  [industry calculation inventory](../../src/pfmsoft/eve_argus/calculations/industry_base_calculations.py)
  as an authoritative formula source.
- Avoid introducing a general report framework solely for this report.

## Decisions required before implementation

| Decision                         | What must be settled                                                                                              |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Product selection and batch size | Representative owned-BPO routes with T1/T2, a component chain and T2 ship/rig established; exact sample IDs remain to select |
| Supported families               | T1/T2 proof, exclude T3; reactions purchase-only in the high-sec NPC profile                                       |
| Character and facilities         | Osmeden high-sec NPC station, all relevant skills 5, no implants or structure/rig bonuses; use reference Omega profile, NPC tax 0.25%, production SCC 4%; station services remain to verify |
| Input purchasing                 | Jita primary-station sell 5%; ignore inventory, exclude hauling; no acquisition-location comparisons               |
| Build-versus-buy                 | Buy-all/make-all only; missing required BPOs leave make-all incomplete; ambiguous routes need explicit handling     |
| Manufacturing copies             | BPC-only workflow and copying costs/time are established; copy counts, licensed-run sizing, limits and unused-run allocation remain |
| Owned BPCs                       | Existing BPCs excluded; model fresh copying/invention                                                             |
| Invention                        | No decryptors; cost ceil(1 / p) attempts per required successful BPC; no confidence-based planning or retry schedule |
| Blueprint overhead               | Historical purchase/research excluded; full batch cost without surplus credit; unused BPC-run mechanics remain     |
| Scheduling                       | Durations and dependencies only; elapsed scheduling excluded                                                      |
| Sale economics                   | Explicit sales-tax and broker-fee fields set to 0% for the proof; nonzero fee applicability and relisting remain for later |
| Historical prices and sales      | Most recent available ten-day window; expose dates/coverage; confirm gap handling and minimum coverage             |
| Freshness and missing data       | Age/alignment policy and which missing inputs block a quote versus retain incomplete rows                         |
| Sale return                      | Profit / production cost, entire reference batch sold; numeric display precision remains                           |
| Artifacts                        | One CSV plus combined Markdown/HTML; confirm wide schema, portion-size terminology, filenames and overwrite behavior |

## Acceptance criteria

Use synthetic fixtures and mock external dependencies. Write Red/Green tests for
new functions and behavior.

1. Given a higher-ME/lower-TE original and a lower-ME/higher-TE original, select
   the higher-ME item and retain its actual TE. Resolve equal ME by TE, then a
   documented deterministic tie-breaker.
2. A multi-level manufacturing fixture produces the exact dependency jobs,
   per-job rounded materials, shopping-list quantities, surplus, fee components,
   and expected unit cost.
3. A shared component is charged once under the selected aggregation/allocation
   policy. Summary totals reconcile with the step breakdown.
4. BPC exhaustion and copy limits create valid job splits or explicit
   unavailability, never negative remaining runs.
5. Every manufacturing job uses a copied or invented BPC. Exact copy counts,
   licensed runs, source BPO ME/TE, costs and durations appear in dependencies
   and blueprint inputs. Invented T2 BPCs include source copying and invention,
   never a fictitious T2 BPO copy job; costs roll up once.
6. Invention fixtures include consumed copy runs, datacores, failure
   costs, successful BPC attributes, and the agreed expected/batch allocation.
   Multi-success confidence, if supported, is tested against exact probabilities.
7. Exact sale-price fixtures produce the expected gross revenue, fees, net
   proceeds, per-unit and total profit/loss for every hub scenario. Regional
   history is labelled correctly.
8. Missing prices, absent blueprints, unsupported routes, cycles, zero-volume
   history, stale inputs, and unknown expiry produce explicit statuses and
   diagnostics rather than fabricated zero-cost/profit results.
9. Step durations agree with verified formula examples. Any elapsed schedule
   obeys dependencies, slots and shared blueprint constraints.
10. CSV/Markdown/HTML agree on overlapping values and totals. Verify actual CSV
    headers and values, sorting, nulls and quoting; Markdown formatting; HTML
    autoescaping, accessible tables, anchors and self-contained assets.
11. CLI tests cover registration, selection, corporation overrides, preparation
    errors, quiet-mode warnings, output collisions and overwrite behavior.
12. Collection does not refresh source snapshots or make unapproved enrichment
    calls.
13. A fixture with a final recipe consuming a manufacturable component produces
    separate buy-all-inputs and make-all-inputs rows. The former buys the
    component; the latter includes its production job and purchases its terminal
    inputs. Neither double counts the component's purchase and production costs.
14. With complete history covering four days and volumes 10, 20, 0 and 30,
    average daily sales is 15 units/day, not average order count. Missing-day
    fixtures expose coverage and follow the agreed denominator; absent history
    remains unknown rather than reporting zero sales.
15. With allocated cost 200 ISK for 10 attributed units and net proceeds of
    250 ISK, unit cost is 20 ISK, profit per unit is 5 ISK, total profit is
    50 ISK and return is 25%, not the 20% revenue-based margin. Zero/unknown
    cost yields an unavailable return. Both detailed companions match the CSV.
16. A product whose static portion size differs from its recipe output per run
    preserves both values and calculates unit cost using the attributed output,
    not the static portion size.
17. Invented T2 ship/rig fixtures have ME 2%, TE 4% and one run; another
    supported T2 product has ME 2%, TE 4% and ten runs. No decryptor inputs,
    modifiers, costs or comparison profiles are included.
18. Ordinary reference estimates use ten manufacturing runs. For a recipe
    producing five units per run, output is 50 units, not ten. Base T2 ship/rig
    estimates use the single run of the base invented BPC.
    Copy/invention allocation and per-job material rounding agree
    with each actual batch and all output formats.
19. Given distinct Jita lowest-sell, Jita sell 5%, Jita buy, and other-hub prices,
    all purchased inputs use only Jita sell 5%. Built components use allocated
    production cost. Changing the destination sale hub does not change unit
    production cost. Missing Jita sell prices leave costs/profit unavailable
    with an explicit incomplete status, not a fallback price.
20. The first-proof profile uses Osmeden's activity indices and level-5 relevant
    skills, with no structure/rig bonuses. A reaction-produced input is purchased
    at Jita sell 5% even in make-all-inputs; no reaction job is emitted.
21. Both sale-fee rate fields render as 0%. Sale fees are zero while copying,
    invention and manufacturing installation charges remain included. All
    formats identify profit as using the zero-sale-fee assumption.
22. The proof applies no implant modifiers. Manufacturing, copying and invention
    use NPC facility tax 0.25%, SCC 4% and zero Alpha surcharge under the
    reference Omega profile, each on its correct activity valuation basis.
    The 2% research SCC is not applied to production jobs.
23. At success probability 0.4, raw expected attempts are 2.5 and costed attempts
    are three per required BPC. At 100,000 ISK per attempt including input
    copying, one required BPC costs 300,000 ISK; two cost 600,000 ISK, not
    500,000 ISK. At probability 1, use one attempt per BPC; probability 0 leaves
    the route unavailable. All formats disclose the rounded-up costing basis
    without guaranteeing successful output.

Run the smallest relevant pytest selection and focused Ruff checks for changed
Python files when implementation begins. Documentation-only prompt work needs no
application validation.
