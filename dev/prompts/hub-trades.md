# Hub-to-hub trades report

## Purpose and controlling scope

Design and implement a report that answers:

> Which items can I buy right now from sell orders at one hub's primary station,
> haul to another hub's primary station, and sell immediately into its buy
> orders for a profit after sales tax and transport, and how many m³ is that?

This is **immediate arbitrage** between stored order snapshots: buy from
existing sell orders, sell into existing buy orders. No orders are placed or
relisted, so no broker fees apply. Relisting at a station is covered by
[station-trades.md](station-trades.md).

The command is `eve-argus reports hub-trades`. "Live" means the latest stored
order snapshots; the command never fetches. Run
`eve-argus fetch market-orders --hubs` immediately before it.

### Confirmed decisions

- **Order scope:** only active orders whose `location_id` is a hub's primary
  station, matching station-trades. Orders elsewhere in the system, and
  wider-range buy orders placed from other stations, are ignored.
- **Quantity model:** walk both order books (see the calculations section).
- **Transport cost:** one global ISK-per-m³ rate, `--transport-per-m3`,
  default 0. There is no collateral component and no per-route rate.
- **Ranking:** total net profit for the matched quantity.
- **Filters:** repeatable `--include` / `--exclude` market groups with the same
  rules as `fetch market-history` and `reports station-trades`.
- **Output layout:** one report (Markdown, CSV, JSON) per source hub, covering
  its four destinations.
- **m³:** shown per unit and per row. It drives transport cost and is a key
  decision input.
- **Multiple destinations:** note items that are profitable to more than one
  destination from the same source, and mark the best match.
- **Snapshot age gap:** warn when the five order snapshots' `received_at`
  times span more than 30 minutes.

### Assumed defaults (not yet confirmed)

- `--min-profit` applies to the row's total net profit, default 0.
- Rows with no profitable overlap (`no_overlap`) are dropped and only counted;
  they would be thousands per source.
- Each destination's walk is independent. Alternate destinations compete for
  the same source supply; supply is not split across destinations.
- No combined cross-source file.

### Non-goals

- Relisting, fill forecasting, or order placement.
- Hauling risk, travel time, jumps, ship cargo limits, collateral, or
  multi-stop routes.
- Capital limits and portfolio allocation.
- Market history (price sanity and liquidity). It can be added later.

## Implemented patterns to reuse

- `reports station-trades`:
  - Active station book selection (`_active_station_book`).
  - Order freshness, with Argus expiry taking precedence over source expiry.
  - Market path resolution and filters (`is_selected_market_path`,
    `validate_market_group_ids`).
  - Report-wide flags, the Markdown template structure, and CLI orchestration.
- `reports scrapmetal`:
  - Order-book walking.
  - `_unit_volume` (`packaged_volume` when set, otherwise `volume`).
- Move shared helpers into a small common module only when both reports need
  the identical code.

## Inputs, scope, and freshness

| Input | Source | Notes |
| ----- | ------ | ----- |
| Orders for 5 hubs | Latest `get_markets_region_id_orders_response` per hub region | All hubs required; read each snapshot once and share it across routes |
| Types, market groups | Static database, read-only | Name, publication, market path, `volume`, `packaged_volume` |

- 5 sources × 4 destinations = 20 routes. Hubs whose stations share a region
  share that region's snapshot.
- If any hub has no snapshot, fail before writing and name the missing hubs
  with the hint `eve-argus fetch market-orders --hubs`.
- Each snapshot keeps its own response ID, `received_at`, expiry used, and
  freshness (`current`, `expired`, or `unknown`). Expired snapshots warn and
  still render. A missing expiry is `unknown`, not fresh.
- Warn when the newest and oldest `received_at` are more than 30 minutes apart.

## Row grain and eligibility

The row key is (source station, destination station, type_id).

- A candidate needs at least one active source sell order and one active
  destination buy order.
- Unpublished and nonmarket types are excluded and counted in a warning.
- Types removed by `--include` / `--exclude` are dropped and counted in
  `filtered_out_count`. Unknown group IDs are a usage error (exit 2).

## Calculations

All money is `Decimal`. m³ values come from static floats; convert them with
`Decimal(str(value))`.

### Unit volume

`m3_per_unit = packaged_volume if packaged_volume else volume`. It is null when
both are missing or 0.

### Book walk

1. Sort source sell orders by price ascending, then order ID.
2. Sort destination buy orders by price descending, then order ID.
3. At each step take `q = min(remaining sell quantity, remaining buy quantity)`
   for the current pair of orders.
4. Profit per unit at a step:
   `buy_price × (1 − sales_tax% / 100) − sell_price − transport_per_m3 × m3_per_unit`
5. Stop before the first step whose profit per unit is ≤ 0
   (`profit_exhausted`), or when either book runs out (`source_supply` or
   `destination_demand`).
6. A buy order whose `min_volume` cannot be met by the quantity still
   available at a profit is skipped, and the row is flagged
   `min_volume_skipped`.

The walk records each fill: source order ID, destination order ID, quantity,
sell price, and buy price.

### Row totals

| Field | Definition |
| ----- | ---------- |
| `units` | Sum of fill quantities |
| `total_m3` | `units × m3_per_unit`; null when m³ is unknown |
| `purchase_cost` | Σ q × sell price |
| `gross_revenue` | Σ q × buy price |
| `sales_tax` | `gross_revenue × sales_tax% / 100` |
| `transport_cost` | `total_m3 × transport_per_m3`; 0 when the rate is 0 |
| `net_profit` | `gross_revenue − sales_tax − purchase_cost − transport_cost` |
| `net_margin_percent` | `net_profit / purchase_cost × 100` |
| `profit_per_m3` | `net_profit / total_m3`; null when m³ is unknown or 0 |
| Prices | Best and last (marginal) sell and buy prices; volume-weighted average sell and buy prices |
| Depth | Source and destination order counts used; `limit_reason` |

### Worked example

- Source sells: 10 units at 100, then 10 units at 105.
- Destination buys: 5 units at 120, then 20 units at 110.
- `m3_per_unit` = 1, transport 1 ISK/m³, sales tax 0%.

| Step | Qty | Sell | Buy | Profit/unit | Profit |
| ---: | --: | ---: | --: | ----------: | -----: |
| 1 | 5 | 100 | 120 | 19 | 95 |
| 2 | 5 | 100 | 110 | 9 | 45 |
| 3 | 10 | 105 | 110 | 4 | 40 |

The source supply runs out (`source_supply`):

- Units 20, total m³ 20.
- Purchase cost 2,050, gross revenue 2,250, transport 20.
- Net profit 180, margin 8.780…%, profit per m³ 9.

With sales tax at 4%, the books are the same but step 3 earns
110 × 0.96 − 105 − 1 = −0.4, so the walk stops (`profit_exhausted`):

- Units 10, purchase cost 1,000, gross revenue 1,150.
- Sales tax 46, transport 10, net profit 94.

### Statuses (precedence order)

1. `unknown_volume`: m³ is unknown and `--transport-per-m3` > 0. No walk.
   With a rate of 0 the row walks and ranks, and m³ fields stay null.
2. `no_overlap`: the first step is not profitable. Dropped and counted.
3. `below_min_profit`: `net_profit ≤ --min-profit` (when it is above 0).
4. `ranked`.

### Ranking

Within a source report, sort by:

1. net profit, highest first;
2. profit per m³, highest first (null last);
3. type name (casefolded), then type_id;
4. destination in `MARKET_HUBS` order.

Unranked rows follow, sorted by status, name, type_id, then destination.

### Multiple destinations and best match

Within one source, an item **matches multiple hubs** when it has ranked rows
for two or more destinations. Its **best match** is the destination with the
highest net profit, using the same tie-breakers as ranking. Exactly one row per
(source, type) is the best match.

The collector computes these fields for every row:

| Field | Type | Meaning |
| ----- | ---- | ------- |
| `destination_match_count` | int | Number of ranked destinations for this source and type |
| `is_best_match` | bool | This row is the item's best destination |
| `best_match_destination` | str | System name of the best destination, on every row of the item |
| `alternate_destinations` | list | Other ranked destinations, best first |

Unranked rows get a count of 0, `false`, and empty values.

Each destination's walk uses the same source sell orders, so **profits across
destinations overlap and must not be added together**. Summary totals count
only best-match rows. The report's definitions section states this.

## Output contract

The run writes three files per source station (15 files in total):

```text
hub-trades-from-<system>-<station_id>-<file_safe_generated_at>.md
hub-trades-from-<system>-<station_id>-<file_safe_generated_at>.csv
hub-trades-from-<system>-<station_id>-<file_safe_generated_at>.json
```

The generation time stamps the name because each report combines five
snapshots.

### Markdown

- **Header:**
  - The source station, generation time, and options.
  - Each snapshot's response ID, received time, expiry, and freshness.
- **Notices:**
  - Expired or unknown-freshness snapshots.
  - Sales tax or transport rate at 0.
  - The snapshot age gap.
  - The station-only competition limitation.
  - Active filters and the filtered-out count.
- **Per-destination summary:** ranked count, best-match profit total, and
  best-match m³ total.
- **Ranked table** (top 100), with these columns:
  - Rank, Best (★), Item, Destination (`Amarr (+2)` when alternates exist).
  - Units, m³ per unit, Total m³.
  - Buy from (best/last), Sell to (best/last).
  - Purchase cost, Sales tax, Transport.
  - Net profit, Margin, Profit per m³, Limit, Flags.
- **Items with multiple destinations:** one line per item, sorted by
  best-match profit. Each line gives the best destination with its profit and
  m³, then the alternates with their profit.
- **Unranked candidates:** counts by status, including the dropped
  `no_overlap` count.
- **Warnings**, then **definitions and limitations**.

Display money with `as_currency` and thousands separators, and escape cells with
`markdown_cell`. The output passes through `format_markdown()`.

### CSV

- One row per kept (destination, type).
- Columns:
  - Provenance for the source and the destination snapshots.
  - Options and the `;`-joined filter IDs.
  - Identity and market path, status, rank, flags.
  - Multi-destination fields, with alternates `;`-joined.
  - m³ and every total.
- Values are plain unrounded decimal strings, and nulls are empty cells.
- Column order is a stable constant tested by the suite.

### JSON

The top-level sections are:

- `schema_version` (1) and `report: "hub-trades"`.
- `source` scope and snapshot provenance; `destinations` with provenance for
  each.
- `generated_at` and `assumptions` (sales tax, transport rate, min profit,
  competition scope).
- `filters` (include, exclude, `filtered_out_count`) and `warnings`.
- `summary`:
  - Counts by status and the dropped `no_overlap` count.
  - `multi_destination_item_count`.
  - `best_match_total_net_profit` and `best_match_total_m3`.
- `records`, each with its `fills`. Fills appear in JSON only.

All formats show the same best destination for every item.

## CLI

| Option | Default | Validation |
| ------ | ------- | ---------- |
| `--to` | required | Directory |
| `--overwrite`, `--quiet` | off | As other reports |
| `--sales-tax` | 0 | 0–100 |
| `--transport-per-m3` | 0 | ≥ 0 ISK/m³ |
| `--min-profit` | 0 | ≥ 0 ISK per row |
| `--include` / `--exclude` | none | Repeatable market-group IDs; unknown exits 2 |

- Steps: validate options, load static data, validate filters, select
  snapshots, preflight output paths, collect and render everything, then
  write. Writing uses exclusive creation unless `--overwrite` is passed.
- Progress goes to stderr and is suppressed by `--quiet`. Warnings and errors
  always print. Distinct warnings print once, naming the affected hubs.
- `OSError`, `sqlite3.Error`, and `ValueError` print `Error: ...` and exit 1.

## Implementation outline

1. `reports/hub_trades.py`:
   - `HubTradesOptions`, `Fill`, `WalkResult`, `HubTradeRow`, and
     `HubTradesReport`.
   - `unit_volume_m3`, a pure `walk_books()`, best-match annotation, and
     `collect_hub_trades(...)`.
2. `reports/hub_trades_render.py` and `templates/hub_trades/report.md.jinja2`.
3. `cli/reports/hub_trades.py`, registered in `cli/reports/__init__.py`.
4. `tests/pfmsoft/eve_argus/reports/test_hub_trades_report.py`.
5. README section and the skill's `report-patterns.md` registry row.

## Measurable acceptance criteria

- **Walk:**
  - Both worked examples give the exact totals and limit reasons above.
  - `destination_demand` is reported when buy orders run out first.
  - Sales tax and transport can turn a positive spread into `no_overlap`.
  - `min_volume` skipping is flagged.
- **m³:**
  - Packaged volume is preferred over volume.
  - Unknown m³ with a rate above 0 gives `unknown_volume`; with a rate of 0
    the row ranks with null m³ fields.
- **Scope:**
  - Orders at another station in the hub system are ignored, and so are
    exhausted orders.
  - Each route uses its own region's snapshot.
  - The age-gap warning fires at more than 30 minutes and not at 30 or less.
- **Ranking and tie-breakers:**
  - Ranking order and tie-breakers are exact.
  - `--min-profit` moves rows to `below_min_profit`.
- **Multiple destinations:**
  - One item profitable to three destinations has a count of 3 on all three
    rows, exactly one best row, and alternates in profit order.
  - A profit tie is broken by profit per m³, then hub order.
  - A single-destination item is the best match, has no alternates, and is
    absent from the multi-destination section.
  - Best-match totals count each item once.
- **Filters:** drop rows and record their count; exclusions win.
- **Formats:**
  - The CSV header order is exact and nulls are empty cells.
  - JSON fills and summaries are present.
  - Markdown is unchanged by a second `format_markdown()` pass and escapes
    pipes.
  - All formats agree on the best destination.
- **CLI:**
  - Help lists every option.
  - The command writes 15 files.
  - A missing hub snapshot writes nothing.
  - Existing files need `--overwrite`.
  - Bad options exit 2.
  - `--quiet` keeps warnings.
  - No ESI resources are initialized.

## Deferred scope

- Splitting source supply greedily across destinations.
- A combined best-route file across all sources.
- Per-route transport rates and collateral.
- Cargo caps (`--max-m3`).
- History context.
- Wider-range buy orders that reach the destination station.
