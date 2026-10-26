# Station trades opportunity report

## Purpose and controlling scope

Design and prototype a report that answers:

> At this hub's primary station, which items are worth placing buy orders for,
> then relisting as sell orders, after fees and with realistic liquidity context?

The intended workflow is one trading character at each hub. Give that character
a separate, actionable report for their station, not an all-hub comparison that
requires sorting through unrelated locations.

This is **station trading**, not immediate arbitrage: both acquisition and resale
depend on future player fills. A spread visible in an order snapshot is not a
guaranteed profit or evidence that either proposed order will fill.

Use [scrap-metal-reprocessing.md](scrap-metal-reprocessing.md) as the structural
starting point, but do not copy its reprocessing calculations, material
exclusions, portion sizes, fill-aware order-book walks, or system-wide scope.
The same item is bought and sold here, with no transformation or transport.

### Confirmed report-specific decisions

- Place buy orders, then relist filled items as sell orders.
- Analyze each configured hub's **primary station**, separately.
- Set the proposed buy price one valid EVE market tick above the station's
  highest buy price, and the proposed sell price one valid tick below its
  lowest sell price.
- Rank by **estimated daily net profit**, constrained by a configurable assumed
  share of regional average daily traded volume.
- Start with **1% participation**. This is a scenario assumption, not a measured
  station market share or a forecast of fills.
- Model acquisition broker fee, sale broker fee, and sales tax separately.
  Rates are configurable and initially 0%; prominently warn when fees are 0.
- Show the capital needed for the modeled quantity. Defer capital limits,
  inventory limits, and portfolio allocation.
- Begin with proof scripts, inspect their output, and migrate into eve-argus
  only after approving the prototype.

### Proposed prototype settings

The following choices make the first output concrete but remain reviewable:

- A 10-calendar-day history window.
- A history-age warning beyond 7 days.
- Show the top 100 ranked rows in each station's Markdown report; retain all
  candidate rows in CSV and JSON.
- Rank only positive estimated daily net profit, with no additional minimum
  profit or margin threshold initially.
- Use station-anchored order competition for the initial prototype; explicitly
  disclose the wider-range buy-order limitation described below.

These are report-specific settings, not universal eve-argus report conventions.

### Non-goals

- Buying existing sell orders and selling immediately into buy orders.
- Hauling between stations, systems, or regions.
- Reprocessing, manufacturing, or valuation of recovered materials.
- Placing, changing, canceling, or otherwise executing market orders.
- Character wallet, existing inventory, escrow discounts, or own-order tracking.
- Predicting queue position, competitors' repricing, fill probabilities, or an
  exact time to sell.
- Treating summed opportunity estimates as an achievable portfolio profit.

## Development workflow

Keep the initial prototype in `dev/proof-scripts/station-trades/`, with generated
output in `dev/proof-scripts/proof-output/station-trades/`.

Do not modify application source or application tests during this design and
prototype phase without explicit approval. Pure calculation checks and synthetic
fixtures may accompany the proof scripts; production Red/Green tests follow at
migration. This prompt requests a report design and prototype, not production
integration yet.

Proposed eventual command: `eve-argus reports station-trades --to ./reports`.
This command does not exist yet.

## Implemented patterns to reuse

Check current implementations before coding; historical prompts are not
authoritative API documentation.

- [Hub-price command](../../src/pfmsoft/eve_argus/cli/reports/hub_prices.py):
  newest regional snapshots, read-only inputs, on-demand summaries, provenance,
  destination preflight, and render-before-write behavior.
- [Order summary calculations](../../src/pfmsoft/eve_argus/dynamic/order_summary.py):
  `calculate_dataset_summaries(..., location_id=hub.station_id)` already supports
  station scope. Do not also pass `system_id`; the scopes are mutually exclusive.
- [Hub definitions](../../src/pfmsoft/eve_argus/models/market_hubs.py):
  station, system, and region IDs and names.
- [Scrapmetal collector](../../src/pfmsoft/eve_argus/reports/scrapmetal.py),
  [renderer](../../src/pfmsoft/eve_argus/reports/scrapmetal_render.py), and
  [template](../../src/pfmsoft/eve_argus/templates/scrapmetal/report.md.jinja2):
  per-hub opportunity output, fee visibility, flags, and explanatory footers.
- [Shared Markdown formatter](../../src/pfmsoft/eve_argus/helpers/markdown.py):
  format rendered Markdown with `format_markdown()`, including table alignment.

Station-scoped collection is a deliberate departure from the existing
system-scoped hub-price and scrapmetal reports. Do not pass station summaries
to their system-only collectors or relabel system prices as station prices.

## Available datasets

| Dataset | Access | Scope and contents | Role in this report |
| ------- | ------ | ------------------ | ------------------- |
| Market orders | `market_orders_responses()` and `market_orders()` in [dynamic/read.py](../../src/pfmsoft/eve_argus/dynamic/read.py) | Regional snapshots; individual orders include station/structure `location_id`, system, side, price, remaining volume, range, and minimum volume | Exact station best prices, competing order counts, visible quantities, and proposed order prices |
| Order summaries | `calculate_dataset_summaries()` in [dynamic/order_summary.py](../../src/pfmsoft/eve_argus/dynamic/order_summary.py) | Calculated on demand from the same source snapshot; station, system, or regional scope | Station 5% buy/sell reference prices, depth quantities, counts, and outlier context |
| Regional market history | `market_history_by_region()` in [market_history/read.py](../../src/pfmsoft/eve_argus/market_history/read.py) | Daily regional average/high/low prices, traded volume, and order count per type | Actual historical regional activity and traceable history dates |
| History summaries | `calculate_history_summary()` in [market_history/history_summary.py](../../src/pfmsoft/eve_argus/market_history/history_summary.py) | Volume-weighted prices and average daily volume/order count over an explicit calendar window | The volume basis for the participation scenario and historical price sanity context |
| Static types and market groups | [static/read.py](../../src/pfmsoft/eve_argus/static/read.py) | Published status, market membership, type identity, market path, packaged volume | Candidate eligibility and readable identification |
| Configured hubs | `MARKET_HUBS` in [models/market_hubs.py](../../src/pfmsoft/eve_argus/models/market_hubs.py) | Primary station plus enclosing system and region | Exact report scope |

### Important dataset semantics

- A **5% price is a depth threshold**, not a +/-5% price band and not necessarily
  an average execution price. The implementation walks 5% of valid volume and
  includes orders tied at the cutoff. Its separate outlier filter is not 1.05;
  use and record the existing `FILTER_FACTOR_DEFAULT`.
- Proposed order prices come from the raw station best prices, **not** 5%
  prices or historical average prices. Summaries are reference context only.
- Regional history is not station history. Its volume cannot reveal the
  station's share, how much traded through buy versus sell orders, or how much
  the user's orders could capture.
- History daily `order_count` is not the number of currently competing orders.
- History summaries average volume across the entire requested calendar
  window; absent dates contribute zero volume, not a shorter denominator.
  An absent stored date alone cannot distinguish no trading from incomplete
  collection. An absent dataset is unknown, not proven zero demand.
- Summary `start` means the newest requested date; `end` means the oldest.
  Export clearer `window_start_date` / `window_end_date` names in chronological
  order rather than copying this naming ambiguity.

### Preparation

Use existing static-import configuration and stored regional orders. Examples
of supported fetch commands:

```bash
uv run eve-argus fetch market-orders --hubs
uv run eve-argus fetch market-history --hubs --market-types
uv run eve-argus fetch market-history --from ./selection.json
```

The last form can narrow expensive history collection:

```json
{"region_ids": [10000002], "type_ids": [34, 35, 36]}
```

Report generation must not fetch or refresh data, access credentials, or require
network enrichment. Do not run these fetch commands as part of designing or
generating the prototype.

## Scope and candidate selection

- Include all five configured hubs: Jita, Amarr, Dodixie, Hek, and Rens.
- Match raw orders using `location_id == hub.station_id`, not just system ID.
- Candidate types are published, have a market group, and have at least one
  remaining buy or sell order at the station. Retain one-sided candidates as
  incomplete rows rather than pretending their missing price is zero.
- Use valid positive prices and positive remaining quantities. Invalid
  nonpositive prices are data errors, not opportunities. Ignore exhausted
  orders when identifying best prices and counting competing orders.
- Preserve `type_id`, type name, market-group path, station, system, and region
  IDs and names. Diagnose missing static references instead of silently
  inventing eligibility or dropping inconsistent data.
- Do not apply scrapmetal's Raw/Gas/Reaction exclusions or require type materials.
- Each row is one `(station_id, type_id)` opportunity.

### Buy orders with wider ranges

Station-anchored buy orders may accept deliveries elsewhere, and orders based
elsewhere may accept deliveries at this station. Filtering on `location_id`
does not determine every order competing for goods sold here.

The first prototype models a **station-range acquisition order** and compares
it against buy orders anchored at that station. Label its competition scope
`station_anchored_only`, show the limitation prominently in every report, and
do not claim its bid is the best effective bid available at the station.

Do not include all regional bids as station competitors or assume a numeric
jump range covers the station without a route/range calculation. A later
effective-coverage model needs explicit range rules and verified system-distance
data. Preserve relevant raw range/minimum-volume context for investigating
outliers; do not interpret visible bid quantity as fillable supply.

## Snapshot selection, freshness, and missing data

- Select the newest stored regional order response per hub region, using the
  source `response_metadata_id` to read its orders.
- Never fall back to an older populated snapshot when the newest one is empty.
- Reuse each regional dataset once; calculate station summaries in memory.
- Validate response, order, and summary scope and provenance before collecting.
- Show generation time separately from order receipt time and expiry.
- Follow Argus-expiry precedence over source expiry. Warn and render expired
  orders; unknown expiry stays unknown, not fresh.
- History is allowed to lag orders because fetching it can take many minutes.
  Show its receipt timestamps, actual newest/oldest dates used, and window.
- For the first prototype, use one common window per region: end on its newest
  stored history date strictly before generation's UTC date, then include that
  date and the previous 9 calendar days. Export the window and actual per-type
  dates separately. Do not use a different old window for each illiquid item.
- Mark history stale when its newest used date is more than 7 days before
  generation's UTC date; stale history remains usable with a visible flag.
- Missing history does **not** suppress a spread opportunity from CSV/JSON,
  but its daily quantity/profit are unknown and it cannot receive a daily-profit
  rank. Explain this difference from scrapmetal, where history is not required
  for the main ranking.

| Condition | Required behavior |
| --------- | ----------------- |
| No stored order snapshot for a hub | Fail before report writes, naming affected hubs and the fetch command |
| Newest snapshot empty, or no station orders | Produce an explicit empty station report and valid export headers |
| One station book side missing | Retain candidate with missing-side status; no proposed round trip or rank |
| History database or type history missing | Warn, retain spread/fee information, leave daily estimates null and unranked |
| History exists but window volume is zero | Daily scenario quantity/profit are zero; no positive-profit rank |
| Stale orders/history | Warn and render; preserve age/expiry and flags in machine-readable output |
| No known expiry | Report unknown freshness |
| Inconsistent provenance/static references | Explicit failure; do not fabricate prices, names, or eligibility |

## Proposed prices and market ticks

For each complete station book:

```text
best_buy = highest remaining station-anchored buy price
best_sell = lowest remaining station sell price
proposed_buy = next valid market price strictly greater than best_buy
proposed_sell = next valid market price strictly less than best_sell
```

Verify current EVE price precision, minimum price, and tick rules before
implementing these operations. Do not assume that a tick is always 0.01 ISK,
or multiply by a percentage and round arbitrarily. No market-tick helper has
been identified in the existing currency helpers.

Record the verified rule and source alongside the prototype, and test precision
boundaries and transitions between tick bands. Generic currency quantization
is not a market-tick algorithm.

If no valid lower sell price exists, or proposed prices meet/cross
(`proposed_buy >= proposed_sell`), retain the row but do not rank it. A negative
spread must never become an apparent profit through rounding.

Assume one placement of each order and no repricing. Repeated modification fees,
minimum order charges, competition, and time spent maintaining orders are not
modeled initially; disclose these exclusions.

## Calculations and units

Use `Decimal` throughout. Rates below are fractions internally; user inputs and
exports label percentages explicitly.

```text
B = proposed_buy                           ISK/unit
S = proposed_sell                          ISK/unit
ba = acquisition broker fee percent / 100
bs = sale broker fee percent / 100
t = sales tax percent / 100

acquisition_broker_fee_per_unit = B * ba
sale_broker_fee_per_unit = S * bs
sales_tax_per_unit = S * t
acquisition_cost_per_unit = B + acquisition_broker_fee_per_unit
net_sale_proceeds_per_unit = S - sale_broker_fee_per_unit - sales_tax_per_unit
gross_spread_per_unit = S - B
net_profit_per_unit = net_sale_proceeds_per_unit - acquisition_cost_per_unit
net_margin_percent = 100 * net_profit_per_unit / acquisition_cost_per_unit

V = regional average daily volume across the full history window
p = assumed participation percent / 100     initially 0.01
estimated_daily_units = V * p
estimated_daily_net_profit = estimated_daily_units * net_profit_per_unit
modeled_acquisition_capital = estimated_daily_units * acquisition_cost_per_unit
modeled_sale_listing_cost = estimated_daily_units * sale_broker_fee_per_unit
```

- Apply participation **once**, to complete buy-then-sell cycles. Do not add
  buy-side and sell-side volume or independently claim 1% fills on both sides.
- `estimated_daily_units` may be fractional: it is an average scenario, not a
  valid order quantity. Also show `one_day_order_units = floor(estimated_daily_units)`
  as an illustrative integer quantity and its acquisition capital. A zero
  one-day integer quantity does not prove that longer-horizon trading is invalid.
- Show per-unit and daily-scenario fee amounts independently, including zeros.
- Fee inputs default to 0% with a prominent warning that net profit excludes
  any real fees not entered. Validate each percentage within 0..100 and
  participation within greater than 0 and at most 100.
- Broker fees apply to buy acquisition and sell listing separately; sales tax
  applies to gross sale value. There is no reprocessing tax.
- This is a proportional fee model, not an exact wallet-transaction simulation.
  Verify relevant game fee rules before asserting exact in-game costs.
- Acquisition capital includes item cost and acquisition broker fee. Sale
  listing cost is shown separately because it is paid at a different stage.
  This is not peak wallet/escrow or working-capital modeling.
- Do not cap daily throughput by visible open order quantities: competing buy
  orders are demand, not acquisition supply, and sell orders are competing
  inventory, not a guaranteed cap on future daily trades.
- Preserve calculation precision for sorting and thresholds. Quantize displayed
  money to cents using the existing currency rounding convention; round counts
  only where explicitly defined. Export precision and rounding rules.
- A history average of zero with zero traded volume is not a market price.
  Export its price-sanity comparisons as null.

### Worked example

The following planned prices are synthetic tick-helper outputs, not a test of
unverified tick rules:

```text
B = 100.00 ISK
S = 120.00 ISK
acquisition broker fee = 1%
sale broker fee = 1%
sales tax = 2%
regional daily volume = 200 units
participation = 1%
```

Expected results:

| Metric | Value |
| ------ | ----- |
| Acquisition broker fee per unit | 1.00 ISK |
| Sale broker fee per unit | 1.20 ISK |
| Sales tax per unit | 2.40 ISK |
| Acquisition cost per unit | 101.00 ISK |
| Net sale proceeds per unit | 116.40 ISK |
| Net profit per unit | 15.40 ISK |
| Net margin | 15.247524...%, displayed 15.25% |
| Estimated daily completed units | 2 |
| Estimated daily net profit | 30.80 ISK |
| Modeled acquisition capital | 202.00 ISK |
| Modeled sale listing cost | 2.40 ISK |
| Daily acquisition / sale broker fee / sales tax | 2.00 / 2.40 / 4.80 ISK |

Changing regional volume to 150 gives 1.5 estimated daily units, 23.10 ISK
estimated daily net profit, and 1 illustrative one-day order unit. Do not round
the ranked daily estimate to one unit.

## Eligibility, ranking, and flags

Keep status and quality flags separate.

Suggested statuses: `ranked`, `unprofitable`, `missing_buy`, `missing_sell`,
`missing_history`, `zero_history_volume`, and `invalid_price_target`.
Where multiple conditions apply, export a `missing_data` list and use a
documented deterministic status precedence.

Rank only rows with two usable proposed prices, positive net profit per unit,
and positive known history-based daily units. Stale data does not automatically
remove a rank; warn rather than silently hiding it.

Sort ranked rows by:

1. Estimated daily net profit descending, using unrounded values.
2. Net margin descending.
3. Type name ascending.
4. Type ID ascending.

CSV/JSON retain all candidates, with ranked rows first and remaining rows ordered
by status, name, and ID. Ranks are station-local, not global.

Show regional history average, actual history coverage, competing station book
depth, and deviations of proposed prices from the history average. These help
the user inspect spikes, manipulation, or illiquid spreads; historical average
is not a bid/ask substitute or evidence either order will fill.

Required flags include missing/stale history, expired/unknown order freshness,
zero fee assumptions, and incomplete competition coverage. Show history missing
days and station order counts directly. Do not invent an unverified fill
probability or silently suppress candidates using arbitrary price-deviation
thresholds.

## Output contract

Create one set of Markdown, CSV, and JSON files per hub's primary station:

```text
station-trades-Jita-60003760-<orders_received_at>.md
station-trades-Jita-60003760-<orders_received_at>.csv
station-trades-Jita-60003760-<orders_received_at>.json
```

Sanitize filename components using the existing helper. Source receipt time is
not generation time. Different hubs may have different snapshots. During proof
iteration, explicitly overwrite or select a new destination; do not silently
reuse an earlier report with different history or fee settings.

### Markdown

- Station name/ID and enclosing system and region.
- Order receipt/expiry and generation times, history window, actual data dates.
- Prominent stale-data, zero-fee, regional-volume, and competition-scope notices.
- Assumptions: tick price policy, all fee rates, participation, history window,
  and the absence of capital constraints or repricing costs.
- One daily-net-profit-ranked table: rank, item/type ID, market path, proposed
  buy/sell, per-unit net profit, net margin, regional daily volume, modeled daily
  units, modeled daily net profit, acquisition capital, and flags.
- Fee detail table for the same displayed opportunities, including acquisition
  broker fee, sale broker fee, and sales tax; do not hide costs in one total.
- Unranked counts by status and directions to the full CSV/JSON.
- Explicit "No opportunities meet the ranking criteria" when appropriate.
- A glossary at the end defining statuses, flags, prices, margin denominator,
  regional volume, assumed participation, capital, and the limits of the daily
  profit estimate.

### CSV

One row per station/type candidate; use these column groups in this order:

1. Generation time, order response ID, receipt/expiry metadata and freshness.
2. Region/system/station IDs and names.
3. Type ID, type name, market path.
4. Status, rank, flags, missing data, competition scope.
5. Participation, history window length, all three fee rates, price policy.
6. Best station buy/sell; proposed buy/sell; 5% buy/sell references.
7. Remaining station buy/sell quantities and order counts, plus 5% depth counts
   and quantities.
8. History receipt/freshness, window start/end, actual oldest/newest dates used,
   missing days, regional average price, daily volume, daily order count.
9. Proposed buy/sell deviations from the historical average, as percentages.
10. Gross spread, acquisition broker fee, sale broker fee, sales tax,
    acquisition cost, net sale proceeds, net profit, net margin, all per unit
    except margin.
11. Modeled daily units, daily net profit, daily fee amounts, acquisition capital,
    sale listing cost, illustrative one-day integer units and acquisition capital.

Finalize exact field names and typed model before implementation. Document the
resulting literal header and test its order. Monetary values are plain decimal
strings; nullable values are empty cells, never fabricated zeros. Use UTF-8,
standard CSV quoting, LF records, `/`-joined paths and `;`-joined flags.

### JSON

Start this report at `schema_version=1`. Include report-level scope, source and
history metadata, assumptions, fee/participation settings, warnings, summary
counts, and a `records` array matching CSV facts and ordering.

Use exact decimal strings for money and calculated decimal metrics, integer IDs
and counts, and JSON `null` for unknown values. Distinguish rounded presentation
values from any exported higher-precision ranking values so the ordering remains
auditable. Do not copy hub-price schema version 2 as a universal convention.

All formats must be rendered from one typed collected model per station, not
recalculate business logic in templates or repeat database queries per format.

## Eventual CLI and operational behavior

On migration, register under the existing `reports` group and follow `--to`,
`--overwrite`, and `--quiet` conventions. Proposed report-specific controls:

- `--buy-broker-fee`, `--sell-broker-fee`, `--sales-tax`.
- `--participation-percent`, initially 1.

Keep history window, freshness warning age, and Markdown row limit visible in
metadata even if fixed initially. Do not add a general report framework,
portfolio optimizer, or extra configuration surfaces without a demonstrated need.

Use read-only inputs and no implicit source refresh. Preflight every hub and
output path; collect and render all content before writing. Preserve exclusive
creation unless overwrite is requested. Filesystem failures may leave a partial
file set; preflight is not an atomic multi-file transaction.

Progress belongs on stderr; quiet suppresses progress, not warnings/errors.
Use specific operational error handling with actionable messages and nonzero
status. Do not broadly catch invalid data and turn it into a successful empty
report.

## Implementation phases

1. Verify tick rules and inspect public source models using synthetic examples.
2. Implement pure station selection, tick pricing, fee, throughput, and ranking
   calculations in the proof directory.
3. Generate per-station Markdown/CSV/JSON from stored data without refreshing it.
4. Review known items in game: actual station bid/ask, valid proposed prices,
   spread after fees, realistic fill expectations, and daily-volume assumptions.
5. Refine the output and any adopted quality thresholds with user approval.
6. After prototype acceptance, migrate into eve-argus collectors, renderers,
   packaged templates, CLI registration, and production tests.

## Measurable acceptance criteria

- Orders at another station in the same hub system never set this station's
  best prices or depth summaries.
- Wider-range competition is disclosed, not represented as fully modeled.
- All candidates are published market types, without reprocessing exclusions.
- Newest empty snapshots do not trigger fallback; missing snapshots fail before
  writes with the affected scopes listed.
- Exhausted orders do not set best prices; zero/negative prices fail explicitly.
- Tick helpers pass verified boundary cases, including minimum price and tick
  band transitions; proposed prices are strictly better than their references.
- Crossing price targets remain unranked, with an explicit explanation.
- The worked fee/capital/quantity examples above match exactly, including the
  fractional-throughput case.
- A 10-day window with 1,000 traded units across 8 stored dates has daily volume
  100, not 125, and reports 2 missing days.
- History never becomes a station-specific volume or guaranteed fill estimate.
- Missing history leaves daily estimates null; known zero volume yields zero;
  stale history retains estimates with warnings.
- A row with smaller margin but larger daily net profit ranks first; deterministic
  ties resolve by margin, name, and ID, using unrounded calculations.
- A zero-fee scenario has visible warnings in Markdown, JSON, and CLI diagnostics.
- CSV headers/rows and JSON fields agree on IDs, prices, fees, nulls, ranks, and
  quantities; Markdown presents the same ranked rows and rounded values.
- Names containing pipes, commas, quotes, or newlines render/export correctly.
- Markdown passes through the shared formatter and formatting is idempotent.
- Required invalid input fails before writes; empty output retains headers and
  metadata; quiet mode retains warnings; overwrite/collision behavior is tested.
- Connections close on both success and failure, and no report run implicitly
  fetches orders/history or performs network enrichment.

## Open verification and deferred scope

- Verify market tick and minimum-price rules before implementing price targets.
- Validate fee assumptions against current EVE rules; keep proportional costs
  and omitted modification/minimum fees explicitly labeled.
- Review whether station-anchored competition is adequate before production
  promotion; full effective buy-order coverage is not implemented by this plan.
- A 1% regional participation scenario must be reviewed against actual user
  experience. Regional history alone cannot establish station throughput.
- Missing stored dates do not by themselves establish zero-trade days.
- Capital/inventory limits, own-order exclusion, fill modeling, repricing,
  wider-range coverage, and alternative time horizons are deferred.

This document is a design prompt. No station-trades prototype, application
implementation, live-data verification, or new application tests are claimed
complete.
