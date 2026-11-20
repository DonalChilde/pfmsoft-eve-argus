# Pfmsoft Eve Argus

## Static database access

The static database access layer follows the same separation as market history:

- [static.read](src/pfmsoft/eve_argus/static/read.py) executes read queries and
  returns typed datasets, for example `read.types(connection)`. Types, groups,
  and categories default to published records; use `only_published=False` to
  include unpublished records. Type records include `category_id` from their
  linked group, regardless of the group's publication status. Reading a type
  whose group is missing raises `sqlite3.IntegrityError`.
- [static.write](src/pfmsoft/eve_argus/static/write.py) writes validated ESD
  datasets, for example `write.types(connection, dataset=types)`. Writers with
  localized fields accept `language=LanguageEnum.EN` by default. Industry
  activities use the existing `write.industrial_activities` entry point.
- [static.util](src/pfmsoft/eve_argus/static/util.py) provides
  `load_table_definitions()` for schema initialization.

The former `static.query_helpers` module has been removed. Use the read/write
entry points without `get_`/`write_` prefixes and pass writer datasets by keyword.
Generic metadata operations remain unsupported; use `read.sde_metadata` and
`write.sde_metadata` for SDE build metadata.

## Planetary Interaction browser and unit costs

For the separate route-oriented operations report, run:

```bash
uv run eve-argus reports planetary-operations --to ./reports/planetary-operations.html
```

Open the single HTML file directly in a browser. It includes Extraction,
P1/P2/P3 Inputs, P4 Buy/Build, Factory Planner, Market Prices, Market History, PI Stats, and
Factory Plans, with no companion files
or network requests. It uses the latest locally stored The Forge order
snapshot (Jita **system** and The Forge region) and per-material ten-day
Forge history windows where available. `--overwrite` replaces an existing
report; `--quiet` keeps warnings and errors visible.

Factory Planner compares two colony layouts using the workbook's building and
link budgets. Change the Command Center, planet radius, optional extra link
distance, and building counts to see CPU, powergrid, and setup cost update.

**Calculated Costs** compares route costs against a selected market basis.
The **Source operation** filter defaults to **ALL** and keeps any checked
rows when you change the filter.
Use **Export Selected** to save one calculated cost per material and
**Clear Selected** to uncheck all rows without changing saved costs. The
**Exported Costs** view retains those values for the browser tab session
and downloads the full list as `pi-unit-costs.json`:
later exports update selected materials without removing the others. Clear
resets the saved list but does not delete downloaded files.

The original browser command below is unchanged.

The [PI package](src/pfmsoft/eve_argus/pi) provides a validated local P0-P4 recipe
catalog, pure unit-cost calculations, compact automatic production scenarios,
and grouped comparisons for an offline HTML browser.

```bash
uv run eve-argus reports planetary-interaction --to ./reports/pi-browser
```

Open the generated `index.html` directly in a browser; no server or network is
required. Keep all six generated files together when copying the directory.
The command reads stored Jita station orders and optional The Forge history;
it never fetches or refreshes data. Missing references and stale snapshots are
shown explicitly. Generation follows `--overwrite` and `--quiet` conventions;
quiet mode retains warnings/errors. Existing unrelated files are preserved.
Collection and rendering finish before writing, but multiple writes are not
an atomic transaction.

- Starts at **6% customs tax**, with intermediate production retained on-planet.
  Override with `--tax-percent` and
  `--intermediate-boundary on-planet|off-planet`, or edit the browser controls.
- Shows all seven workbook starting-tier/output-tier groups (105 comparisons),
  separately selected input/sales price bases, recipe/customs details, and
  complete Jita buy, Jita sell, and history reference tables. The history table
  includes average daily regional volume and coverage.
- Shared material choices support purchasing, mining-derived quotes, and
  manufacturing. `Make profitable P2` mixes profitable P1-manufactured P2 quotes
  with purchased P2 inputs. Manual choices persist across control changes;
  switching presets asks before replacing them.
- `Factory cycles` means **completed cycles/hour**, initially 1 as an editable
  assumption, not a factory-capacity claim. Changing it affects time estimates,
  never unit cost. Mining costs, sales tax, and transport fees are excluded.
- Select any subset of source or route prices to download as JSON. There is one
  selected quote per type; filters do not remove selections. The `prices` object
  maps type-ID strings to exact decimal unit-cost strings, including applicable
  export tax. A JSON preview supports copying if an embedded browser blocks
  downloads. Industry-report override importing remains separate future work.

Browser arithmetic uses locally bundled MIT-licensed decimal.js (with its
license). Node.js enables the Python/browser parity tests; those tests skip if
Node.js is unavailable.

- [Catalog](src/pfmsoft/eve_argus/pi/catalog.py): `load_catalog()` returns the
  83 material definitions. `mining_planet_types()` derives P1/P2 single-planet
  resource eligibility from raw-resource co-occurrence, not extraction capacity.
  The source is the local PI reference, not independently verified live game data.
- [Costing](src/pfmsoft/eve_argus/pi/costing.py): `mined_source()` quotes zero-cost
  extraction/local refining with optional final export; `calculate_stage()`
  consumes explicit input quotes and returns a per-cycle breakdown and reusable
  unit price. Neither function reads databases or accesses the network.
- [Scenarios](src/pfmsoft/eve_argus/pi/scenarios.py): `build_scenario_graph()`
  represents market, mining, and manufacturing alternatives using documented
  dataclasses. It shares material dependencies and includes both local and
  exported intermediate production. Supply explicit off-planet market quotes on
  one price basis; absent quotes become explicitly unavailable alternatives.
  `scenario_counts()` returns exact total/complete combination counts,
  `iter_scenarios()` expands outcomes lazily, and `best_scenario()` finds a
  cheapest complete outcome without exhaustive enumeration. Set `manufacture=True`
  to require manufacturing the root product; `False` also includes its market
  and mining sources. Root outputs are always off-planet.
- [Browser market inputs](src/pfmsoft/eve_argus/reports/pi_browser.py):
  `collect_pi_market_inputs()` resolves Jita's primary station from the market-hub
  model and collects separate buy-5%, sell-5%, and ten-day regional-history
  references for every catalog material. Supply the selected order response and
  matching dataset, generation time, and an optional `RegionalHistory` lookup.
  The collector performs no database reads or refreshes itself; callers supply
  the lookup. `prices_for()` returns quotes on one market basis. Missing prices,
  history coverage, regional average daily volume, source timestamps, and
  freshness warnings remain explicit. No other market-hub data is required.
- [Grouped comparisons](src/pfmsoft/eve_argus/pi/comparisons.py):
  `calculate_grouped_comparison()` expands manufacturing above a chosen starting
  tier and consumes shared off-planet quotes at that tier or below. For example,
  a P2-starting P3 can consume one bought P2 and one exported P1-manufactured P2
  without expanding either quote again. Choose the intermediate customs boundary
  explicitly. `build_grouped_comparisons()` produces the workbook's seven tier
  groups: P0-to-P1, P1-to-P2/P3/P4, P2-to-P3/P4, and P3-to-P4 (105 comparisons
  for the full catalog). Direct lower-tier recipe ingredients are retained.

Use `Decimal` prices and a fractional effective customs rate (`Decimal("0.1")`
for 10%). `CostBoundary.OFF_PLANET` input quotes incur import tax;
`CostBoundary.ON_PLANET` explicitly means local to the consuming stage.
Choose `export_output=True` to include output export tax, or `False` when the
output stays on the same planet for another stage. Reuse the returned
`StageCost.output` as an input quote without charging its previous export again.
All purchased inputs and reused upstream quotes must share the declared market
price basis, and tax-dependent sources must share the customs rate.

For example, purchasing 3000 P0 at 1 ISK/unit, importing at 10%, and exporting
the 20 refined P1 costs `(3000 + 600 + 800) / 20 = 220` ISK/P1.
Freely mined/refined P1 exported at the same rate costs 40 ISK/P1; eligible
freely mined/refined P2 costs 720 ISK/P2. No mining cost, inferred factory capacity,
sales tax, or transport fee is included. Missing prices retain explicit reasons
and propagate unknown totals rather than partial quotes.

Grouped comparisons keep sales valuation separate from acquisition pricing.
`estimate_production()` takes a comparison and `Decimal` completed
`cycles_per_hour`; output quantity times that rate gives units/hour. Hourly,
daily, and 30-day profit estimates assume continuous operation and do not certify
a factory layout or market fills. Changing the rate never changes unit cost.
Each stage breakdown is per that stage's recipe cycle; embedded upstream costs
must not be added again when displaying a route.

Mining-derived graph sources are exported prices, never implicitly free inputs
on an arbitrary factory planet. Best-scenario comparisons include input import
taxes: a lower off-planet quote can be more expensive than a local intermediate.
Unavailable and expensive alternatives remain in the graph even when a best
complete result exists. A `None` best result explicitly means no complete
eligible route; inspect the retained source reasons.

Concrete combinations grow rapidly: the full catalog uses 83 material nodes and
273 source/production branches, while some P4 roots represent more than
532 quadrillion structural combinations. Use counts, best selections, or bounded
iteration instead of converting a full P4 iterator to a list. Counts distinguish
routes/source choices, not distinct monetary totals. Sale-price comparison stays
separate so an acquisition graph can be reused with different output valuations.

See the [PI design and implementation plan](dev/prompts/planetary_interaction.md)
for calculation assumptions, verification evidence, and deferred work.

## Export market groups

```bash
uv run eve-argus export market-groups --to ./exports
```

Exports all market groups from the configured **Argus static database** (market
groups are not stored in the dynamic database). Uses the configured static build,
or the latest build in the store manifest when unspecified. The source is opened
read-only; no network requests, credentials, or data refresh are required.

The destination directory is created if needed and receives:

- `market-groups-build-{N}.json`: the complete dataset keyed by market-group ID,
  with native JSON arrays for `int_path`, `str_path`, and `types`.
- `market-groups-build-{N}.csv`: one row per market group, with all record fields.
  `str_path` uses the default `/`-joined string path. The other container fields
  (`int_path`, `types`) contain JSON strings, including `[]` for empty containers,
  rather than Python representations.

`{N}` is the build number from the selected database's SDE metadata.
Both outputs are UTF-8. JSON is ordered by market-group ID; CSV rows are sorted
by the rendered `str_path` string. CSV uses standard quoting
and LF record terminators, preserves embedded newlines, writes booleans as
`True` / `False`, and represents absent scalar values as empty cells. JSON uses
`null` for absent values. An empty dataset produces `{}` and a header-only CSV.
Use `--overwrite` to replace existing files and `--quiet` to suppress success
messages without hiding errors. Missing sources and existing outputs fail before
writing either file; filesystem failures during writing may leave partial output
and return a nonzero exit status.

## Export types

```bash
uv run eve-argus export types --to ./exports
```

Exports published types from the configured **Argus static database** to
`types-build-{N}.csv`, where `{N}` is the build number from the selected
database's SDE metadata. Use `--include-unpublished` to include unpublished
types. The CSV is UTF-8, has one row per type sorted by type ID, and includes
group and category IDs/names, market-group and meta-group names, and the
slash-separated market-group path. `description` is the final column.

The source is opened read-only; no network requests, credentials, or data
refresh are required. The destination directory is created if needed. Use
`--overwrite` to replace an existing export and `--quiet` to suppress success
messages without hiding errors.

## Fetch market history

```bash
uv run eve-argus fetch market-history --region-id 10000002 --type-id 34
```

Fetches history into the configured market-history database. Supply at least one
region with `--region-id`, `--from`, `--hubs`, or a combination, and exactly one
type-selection mode:

| Mode                 | Candidate types                                                                                    | Market-group filters |
| -------------------- | -------------------------------------------------------------------------------------------------- | -------------------- |
| Repeated `--type-id` | Explicit IDs, including unpublished, nonmarket, and unknown types                                  | Not allowed          |
| `--from <file.json>` | The file's `type_ids`; each must be a published, market-listed static type                         | Not allowed          |
| `--active`           | Published, market-listed active types discovered independently for each region                     | Allowed              |
| `--market-types`     | Published types listed in static market groups                                                     | Allowed              |
| `--industry-types`   | Published, market-listed blueprint IDs plus materials and products across all blueprint activities | Allowed              |
| `--scrapmetal`       | Published types listed in static market groups and appearing as fixed type-material parents or components | Allowed          |

Explicit regions run in command-line order, followed by `--from` file regions,
then hub regions for Jita, Amarr, Dodixie, Hek, and Rens, with duplicates removed. Types are deduplicated
and scheduled in ascending numeric order within each region; completion order
can differ. Explicit types apply to every selected region.

```bash
# Explicit types across multiple regions
uv run eve-argus fetch market-history \
  --region-id 10000002 --region-id 10000043 --type-id 34 --type-id 35

# Active regional types, restricted by market-group subtrees
uv run eve-argus fetch market-history \
  --hubs --active --include 4 --exclude 187

# Published market-listed types, with configurable execution limits
uv run eve-argus fetch market-history \
  --hubs --market-types --include 4 --include 9 --exclude 187 \
  --workers 25 --failure-limit 10 --progress plain

# Industry-related types from the static blueprints dataset
uv run eve-argus fetch market-history \
  --hubs --industry-types --include 4 --exclude 187

# Reprocessing inputs and recovered materials from static type materials
uv run eve-argus fetch market-history \
  --hubs --scrapmetal --exclude 1031 --exclude 1032 --exclude 1034

# Regions and types from a selection file
uv run eve-argus fetch market-history --from ./selection.json
```

### Selection files

`--from` (for both `fetch market-history` and `fetch market-orders`) reads a JSON
file whose top level is an object:

```json
{"region_ids": [10000002, 10000043], "type_ids": [34, 35, 36]}
```

`region_ids` is a non-empty list of integers and is always required.
`type_ids` is required (non-empty) by `market-history` and ignored by
`market-orders`, so one file can serve both commands; other keys are ignored.
Booleans and numeric strings are rejected, and duplicates are removed in file
order. Every region must exist in the static map-regions dataset, and every
history type must be published and listed in a market group. Malformed files and
invalid IDs are usage errors (exit status 2) reported before any requests; ID
errors list unknown, unpublished, and nonmarket IDs separately.

Industry selection requires a populated static blueprints dataset. It collects
each blueprint's own type ID, materials, and products from copying, invention,
manufacturing, reactions, material research, and time research. Skill-only IDs
are not included. IDs are deduplicated across blueprints and activities before
filtering, and the resulting selection is fetched for every selected region using
the same regional execution limits as the other modes. Missing blueprint data is
an explicit error before any history requests.

Scrapmetal selection requires populated static types, market groups, and fixed
type materials. It includes both primary type IDs (including parents with empty
component lists) and component material IDs, then intersects them with published
types listed in market groups. Randomized-material definitions are not included.
The deduplicated selection is reused for every selected region. Market-group
exclusions are optional, not implicit; missing type-material data is an explicit
error, while an empty eligible intersection is a successful no-op.

### Selection and filters

Regions are validated against the static map-regions dataset before network
requests. The original explicit single-pair invocation still permits regions
missing from static data; failures label them `Unknown region`.

`--include` and `--exclude` may be repeated with `--active`, `--market-types`,
`--industry-types`, and `--scrapmetal`, but not `--type-id` or `--from`. Includes form a union of market-group
subtrees, including each group's directly assigned types. Excludes apply afterward,
regardless of option order, and always win. Filters only remove candidates; they
never introduce inactive or otherwise unselected types. Unknown groups, missing
required static datasets, and inconsistent market paths fail before network
requests. An empty selection is a successful regional no-op.

All generated selections (`--active`, `--market-types`, `--industry-types`, and
`--scrapmetal`)
require published types with known market membership. Types with no
`market_group_id` and IDs missing from the static types dataset are excluded,
even without include/exclude filters. Unknown active/industry IDs produce a
warning, even with `--quiet`; routine output counts excluded unpublished types
and nonmarket/unknown types separately. Explicit `--type-id` requests remain
unrestricted.

Market selection requires populated static market groups and types. Active
selection uses ESI's paginated regional market-types endpoint, not every type
with historical trades. Industry selection follows the same publication,
market-membership, and filter rules as active selection. Unfiltered active and
industry selections use the types dataset to establish market membership and
do not require loading market groups.

For example, `--industry-types --exclude 2` excludes the Blueprints & Reactions
market-group subtree. Nonmarket blueprints (including many Tech II blueprints)
are also excluded because they have no market-group assignment, rather than
being treated as members of group 2.

### Execution, limits, and output

Regions run sequentially using a shared ESI client and resource lifecycle. Each
region finishes or aborts, and pending-task cleanup completes, before the next
region begins discovery or history updates.

| Option                         | Default                                       | Behavior                                                                               |
| ------------------------------ | --------------------------------------------- | -------------------------------------------------------------------------------------- |
| `--workers`                    | `MARKET_HISTORY_WORKER_COUNT` (currently 100) | Positive integer; maximum concurrent updates using continuously refilled workers       |
| `--failure-limit`              | `MARKET_HISTORY_FAILURE_LIMIT` (currently 50) | Positive integer; independent failure budget for each region                           |
| `--stale-after-days N`, `-s N` | `6`                                           | Nonnegative integer; only update pairs whose latest response is older than N days; 0 disables the age filter |
| `--progress auto\|live\|plain` | `auto`                                        | Live progress on interactive terminals by default; plain completion messages otherwise |
| `--quiet`                      | Off                                           | Hide routine output and progress, but retain warnings, failures, and abort notices     |

Defaults resolve from the shared runner's constants. Every implemented selection
mode uses a separate failure budget per region, including explicit IDs and market
types. Failed updates, including logged updater exceptions, consume that budget;
cached skips and cancellation do not. At the limit, pending tasks are cancelled
and awaited, and no new pairs for that region start. In-flight updates can
finish during cancellation, so the failure count can exceed the limit. Already
committed writes remain stored; requests already sent cannot be retracted.

Discovery failures and regional aborts do not stop later regions. Any discovery
or history-update failure causes a nonzero exit status after all regions finish.
User interruption stops the whole command after cleanup.

Live progress shows completed/total pairs, elapsed time, updated/skipped/failed
counts, and the latest type ID. The transient display clears on completion, abort,
or interruption. Plain output reports completion at the selected worker-count
interval. Regional and overall summaries reconcile updated, skipped, failed,
cancelled, and not-started pairs; overall totals separately count discovery-failed
regions, whose unknown pair counts are not included. Cancelled/unstarted pairs
are never shown as successfully completed. Explicit single-pair runs also retain
freshness and expiry details.

### Storage and failure details

Unexpired stored responses skip fetching; Argus expiry overrides ESI expiry, and
missing expiry triggers a refresh. Existing ESI caching and rate limiting apply.

Use `--stale-after-days 3` to additionally skip selected region/type pairs whose
latest response `received_at` is no more than three days old. Days are rolling
24-hour periods, not calendar dates; a response exactly N days old is skipped.
The check uses response metadata even for empty histories and counts recent
pairs as skipped in progress and summaries. Pairs without a stored response
are still fetched. Older responses must also pass the existing expiration
check before fetching. The default is six days; `-s 3` is shorthand for
`--stale-after-days 3`. Pass `-s 0` to disable the age filter.
This filter applies to every type-selection mode, independently for each region.

Successful updates store response metadata and daily history transactionally.
Overlapping dates are replaced and older dates remain stored. Empty responses
still record metadata. Failures are reported with a nonzero exit status.
Use `--quiet` to suppress progress and success messages, but not update errors.

All market-history fetch commands include the region and type names and IDs in
history-update failures, using static database records. Unpublished types include
`, Not Published`; published types have no publication label. For example:

```text
Failed: The Forge (10000002), Compressed Arkonor Blueprint (28368), Not Published. Error Message: HTTP 404 Not Found
```

Types absent from the static dataset are labeled `Unknown type` with their ID;
their publication status is unknown and is not labeled. For the single-pair
command, regions absent from static data are labeled `Unknown region` with their
ID. These labels do not change selection, expiry checks, or failure exit statuses.

History database initialization adds a region/type/received-time metadata index
to both new and existing databases without changing stored records. The first
initialization of an existing large database may take longer while the index is
built. Updates use indexed single-row latest-response lookups and exact duplicate
existence checks rather than loading all metadata for each pair.

### Previous history commands

The old commands have been removed. Use the unified command instead; there are no
compatibility aliases or shims.

| Previous command               | Unified replacement                              |
| ------------------------------ | ------------------------------------------------ |
| `market-history-active`        | `market-history --active`                        |
| `market-history-bulk`          | `market-history --market-types --progress plain` |
| `market-history-bulk-progress` | `market-history --market-types --progress live`  |

Pass the same region and filter arguments where supported. Active selection now
also supports filters. The unified command uses independent regional failure
budgets rather than the old bulk commands' global budget, and accepts
`--workers` and `--failure-limit` overrides. The former `--batch-size` option
has been replaced by `--workers` without a compatibility alias. Each worker
starts its next pair as soon as its current update finishes, without waiting
for other workers.

## Market orders

```bash
uv run eve-argus fetch market-orders --region-id 10000002
uv run eve-argus fetch market-orders --hubs
uv run eve-argus fetch market-orders --region-id 10000002 --region-id 10000043 --hubs
uv run eve-argus fetch market-orders --from ./selection.json
```

Provide at least one `--region-id`, a `--from` [selection file](#selection-files),
or `--hubs` to select all configured hub regions. Explicit regions are processed
first, then file regions, then hub regions, with duplicates removed in first-seen
order. File regions must exist in the static map-regions dataset. Each selected region's full order book
is fetched, not just the orders within the hub system. Current cached responses
are reused; a failed update stops the command with a nonzero exit status.
Each region reports its stored order count (buy and sell orders combined) for
the fetched or cached snapshot without loading the order records into memory.
`--quiet` suppresses progress messages but not errors.

This command only fetches and stores orders in the dynamic database; it does not
read them back or precompute regional or system-scoped price summaries. The
legacy `fetch hub-orders` command has been removed; use
`fetch market-orders --hubs` to fetch its regional order data.

## Price summaries

```bash
uv run eve-argus reports price-summaries \
  --region-id 10000002 \
  --system-id 30000142 \
  --filter-factor 100 \
  --to ./reports
```

Repeat `--region-id` or `--system-id` to request additional scopes. Supplying
both does not combine them: each region produces a region-wide summary, and each
system produces a separate system summary. A system's region is resolved from
the configured static database, so `--system-id` does not require `--region-id`.
Use `--hubs` to append the configured market-hub system scopes. Repeated and
overlapping scopes are deduplicated.

The command uses each selected region's latest stored order snapshot, calculates
summaries without fetching or saving data, and emits CSV and JSON files. Region
scope filenames use the region name; system scope filenames use the system name.
Both use the sanitized source receipt timestamp. The JSON uses schema version
`2`; for region-scoped reports, `system_id` and `system_name` are null. The filter
factor must be finite and greater than 1; it defaults to `100.00`.

The report includes type and market-group IDs/names, market paths,
independently nullable buy/sell summaries, source metadata, and freshness. Types
with neither side are omitted; a missing side is not a zero price. Prices are
exact decimal strings, not binary floats; absent values are null in JSON and
empty in CSV. Metrics use the existing whole-dataset calculations: `five_price`
is the price threshold reaching 5% of valid volume, including all orders tied at
the cutoff; `average` is volume-weighted. The filter factor and filtered counts
are included in each output.

Argus expiry overrides source expiry; absent expiry means unknown freshness.
Expired snapshots remain exportable with visible warnings. `--quiet` hides
progress, not errors or stale-data warnings. Use `--overwrite` to replace
existing files. Inputs are read-only and no market orders are fetched by the
report command; fetch required orders with `fetch market-orders --region-id`
or `fetch market-orders --hubs`.

## Market history summaries

```bash
uv run eve-argus reports history-summary --region-id 10000002 --period 10 --to ./reports
uv run eve-argus reports history-summary --hubs --start-date 2026-10-25 --period 10 --to ./reports
```

Creates one CSV and JSON report per selected region from locally stored market
history. Repeat `--region-id` to select multiple regions; `--hubs` appends the
regions used by the configured market hubs. Duplicate region IDs are removed.
At least one region or `--hubs` is required. The history database is read-only
and is never refreshed by this command.

`--period` is a positive number of calendar days and defaults to `10`.
`--start-date` is an optional ISO date (`YYYY-MM-DD`) that means the newest day
included in each window, inclusive; the period counts backward from it. For
example, `--start-date 2026-10-25 --period 10` covers October 16 through 25.
Without `--start-date`, each type uses its own latest possible history date,
derived from that type's latest stored history receipt. Consequently, rows in
one region report may have different date bounds.

The JSON uses schema version `1` and contains report metadata (`generated_at`,
region ID/name, period, and optional start date) plus records sorted by
`type_id`. Each type row includes its market-group ID/name and market path IDs
and names, actual newest/oldest window dates, missing-day count, volume-weighted
high/average/low prices, average daily order count and volume, and source
receipt/expiry metadata. Market paths follow the same static-data convention as
`price-summaries`. Prices are rounded to two decimal places using currency
rounding and emitted as strings; average daily volume remains a full-precision
decimal string. Unknown values are null in JSON and empty in CSV.

Types with stored history are included even when none of their records falls
inside the selected date window: their missing-day count equals the period,
summary metrics are null, and receipt/expiry metadata comes from their latest
stored history record. Those metadata fields are null only if the region/type
has no stored history at all. Stale history is reported with a warning and is
not refreshed. `--quiet` suppresses progress only; `--overwrite` allows replacing
existing report files.

Output names use the sanitized region name, period, date selector, and report
generation timestamp. For example:

```text
history-summary-The_Forge-10d-latest-2026-11-02T17_18_16_154Z.json
history-summary-The_Forge-10d-latest-2026-11-02T17_18_16_154Z.csv
history-summary-The_Forge-10d-2026-10-25-2026-11-02T17_18_16_154Z.json
```

## Scrapmetal reprocessing reports

```bash
uv run eve-argus fetch market-orders --hubs
uv run eve-argus fetch market-history --hubs --scrapmetal   # optional, slow
uv run eve-argus reports scrapmetal --to ./reports
uv run eve-argus reports scrapmetal --to ./reports --sales-tax 3.6 --broker-fee 1.5
```

Finds items with fixed reprocessing materials that can be bought from sell
orders in each hub system (Jita, Amarr, Dodixie, Hek, Rens) and reprocessed at
that hub for a profit. It also writes per-unit price points for sourcing items
elsewhere. Eligible items are published, listed on the market, outside the Raw,
Gas Cloud, and Reaction material market trees, and have fixed materials. Recovered
quantities are `floor(quantity * yield / 100)` per portion. Inputs are opened
read-only; nothing is fetched.

Per hub, from the newest regional order snapshot:

```text
scrapmetal-deals-Jita-2026-10-17T22_07_37_553890662Z.md
scrapmetal-deals-Jita-2026-10-17T22_07_37_553890662Z.csv
scrapmetal-deals-Jita-2026-10-17T22_07_37_553890662Z.json
```

Items are bought one portion at a time, cheapest hub sell order first. The walk
stops when the next portion would not be profitable after fees, would fall below
`--min-margin`, or when supply or material buy depth runs out (`limit_reason`).
Each item is evaluated under two material-sale scenarios:

- `sell_to_buy_orders`: materials are sold immediately by walking hub buy orders.
- `list_sell_orders`: materials are listed at the hub 5% sell price, assumed to
  fill in full, with the `--broker-fee` listing cost applied.

Reprocessing tax, sales tax, and listing cost are percentages of gross material
value and are reported as separate ISK columns (default 0). The Markdown report
has one table per scenario, ranked by margin and limited to 100 rows. A row is
ranked when its status is `profitable`, its profit is at least `--min-profit`
(default 100,000 ISK), and its margin is at least `--min-margin` (default 5%).
Rows whose output slippage exceeds `--max-slippage` (default 10%), or whose
material volume exceeds one day of regional history volume, are `thin`. Rows
missing a material price are `incomplete`. CSV and JSON keep every row with its
status and flags. The Markdown report ends with definitions of the `Limited by`
values.

One price-point list is written per run, stamped with the generation time:

```text
scrapmetal-price-points-2026-10-18T12_00_00Z.csv
scrapmetal-price-points-2026-10-18T12_00_00Z.json
```

Each eligible item gets a gross per-unit material value at each hub
(`<hub>_buy`, `<hub>_sell` at hub 5% prices, and `<hub>_hist` at the regional
10-day history average), plus `best_buy_hub` / `best_buy_value`. This is the
break-even bid before fees, hauling, and margin. A value is empty when any
material lacks a price. Per-hub `orders_received_at` and `history_newest_date`
columns identify the sources.

Every hub needs a stored order snapshot; otherwise the command fails before
writing. Market history is optional context (price sanity and liquidity flags)
and never sets a trade price. If the history database is missing, or a hub has
no history, or a hub's history ends more than 7 days before generation, the
command warns and continues. Expired order snapshots are reported, not
refreshed. `--quiet` hides progress, not warnings or errors. Use `--overwrite`
to replace existing files.

## Station trades reports

```bash
uv run eve-argus fetch market-orders --hubs
uv run eve-argus fetch market-history --hubs --market-types   # slow
uv run eve-argus reports station-trades --to ./reports
uv run eve-argus reports station-trades --to ./reports \
  --buy-broker-fee 1.5 --sell-broker-fee 1.5 --sales-tax 3.37 \
  --include 4   # Ships only
```

Finds items to buy with a buy order and relist with a sell order at each hub's
primary station (Jita IV - Moon 4, Amarr VIII, Dodixie IX - Moon 20, Hek VIII -
Moon 12, Rens VI - Moon 8). Inputs are opened read-only; nothing is fetched.
Three files per station share the stem
`station-trades-<system>-<station_id>-<file_safe_received_at>` (`.md`, `.csv`,
`.json`).

For each published market type with active orders at the station:

- Proposed prices are one valid tick above the best station buy and below the
  best station sell. Ticks use four significant figures with a 0.01 ISK
  minimum. Only station-anchored buy orders are considered; wider-range buy
  orders may compete but are not modeled.
- Broker fees on both orders and sales tax on the sale are percentages of the
  proposed prices. They default to 0%, which is flagged in every output.
- Regional daily volume is the average over a common 10-day history window that
  ends on the newest stored date before the generation date. Missing days count
  as zero. `--participation-percent` (default 1) sets the assumed share of that
  volume completed per day.
- Rows are ranked by estimated daily net profit, then net margin. Rows with
  missing books, invalid price targets, missing or zero-volume history, or no
  profit are kept unranked in CSV and JSON and counted in Markdown. Markdown
  shows the top 100 ranked rows.

`--include` and `--exclude` take market-group IDs and may be repeated. They use
the same subtree rules as `fetch market-history`: an empty include means all,
exclusions always win, and unknown groups are a usage error. Filtered types are
dropped from every output, and the filters and the filtered-out count are
recorded in each report.

Every hub needs a stored order snapshot; otherwise the command fails before
writing. A missing history database warns and leaves every row unranked.
Expired order snapshots are reported, not refreshed. `--quiet` hides progress,
not warnings or errors. Use `--overwrite` to replace existing files.

## Hub-to-hub trades reports

```bash
uv run eve-argus fetch market-orders --hubs
uv run eve-argus reports hub-trades --to ./reports
uv run eve-argus reports hub-trades --to ./reports \
  --sales-tax 3.37 --transport-per-m3 800 --min-profit 1000000 \
  --exclude 4   # No ships
```

Finds items to buy from sell orders at one hub's primary station, haul, and sell
immediately into buy orders at another hub's primary station. Each hub is a
source in turn, and the other four are its destinations. Inputs are opened
read-only; nothing is fetched. Three files per source share the stem
`hub-trades-from-<system>-<station_id>-<file_safe_generated_at>` (`.md`,
`.csv`, `.json`).

For each published market type with station sells at the source and station
buys at a destination:

- Both books are walked: the cheapest source sells fill the highest destination
  buys while each unit's `buy × (1 − sales tax) − sell − transport per unit`
  is positive. Buy orders whose minimum volume cannot be met are skipped and
  flagged. The row records why the walk stopped (`profit_exhausted`,
  `source_supply`, or `destination_demand`).
- Volume is packaged m³ when available, otherwise m³. Transport cost is total
  m³ times `--transport-per-m3`. Sales tax and transport default to 0, and each
  zero is flagged. Broker fees do not apply.
- Rows are ranked by total net profit, then profit per m³. Rows at or below
  `--min-profit` and rows with unknown m³ (when transport is above 0) are kept
  unranked in CSV and JSON. Routes with no profitable unit are only counted.
  Markdown shows the top 100 ranked rows.
- When an item is profitable to several destinations, every row records the
  match count, the best destination (highest net profit), and the alternates.
  Markdown marks the best row with ★ and lists these items in their own
  section. Each destination's walk uses the same source supply, so
  per-destination profits are alternatives. Summary totals count only best
  matches.

`--include` and `--exclude` follow the same market-group subtree rules as
`station-trades`. Every hub needs a stored order snapshot; otherwise the command
fails before writing. Expired snapshots, and snapshots received more than 30
minutes apart, are flagged rather than refreshed. Only primary-station orders
are matched. `--quiet` hides progress, not warnings or errors. Use
`--overwrite` to replace existing files.

## Corporation blueprints report

```bash
uv run eve-argus reports corporation-blueprints --corporation-id 98196252 --to ./reports
```

Uses the latest stored blueprint snapshot for the explicit or configured
corporation, without refreshing inventory. Populate it separately with
`uv run eve-argus fetch corporation-blueprints`. Types and market groups must
already exist in the configured static database.

Four files share the stem
`corporation-blueprints-<corporation_id>-<file_safe_received_at>`:

- `.json`: source metadata, all enriched inventory, original summaries, missing
  BPOs, and name-resolution diagnostics.
- `.md`: freshness, owned-original summaries and missing BPOs by market path,
  plus separate detailed originals/stacks and copies tables.
- `-owned.csv`: one row per original/stack/copy source record, including raw
  quantity/runs sentinels, names, location flags, and metadata.
- `-missing-bpo.csv`: one row per missing published market-blueprint type with
  nullable static base price (not a live market quote).

All originals, including unpublished/nonmarket types, appear in inventory and
original summaries. Missing originals are compared only against published types
beneath blueprint market group 2. Copies alone do not satisfy BPO ownership.
Quantity `-1` is one original, `-2` one copy, and positive quantities count stacked
originals; other values are errors. Copy runs are not item counts. Summary ME/TE
comes from one actual original, selected by highest ME, TE, raw quantity, then
smallest item ID.

CSV columns are fixed, optional values use empty cells, paths use `/`, and empty
views retain headers. JSON preserves nulls and raw fields. An empty snapshot has
no inventory but still lists all eligible missing originals. Missing snapshots
are errors; expired snapshots remain usable with stale-data notices.

Only corporation and station-range location IDs are sent to public name lookup.
Private/container locations remain `UNKNOWN`, with IDs and flags preserved.
Name-resolution warnings are omitted from CLI/Markdown but retained in JSON/logs;
actual lookup failures are errors.

The directory is created as needed. Source receipt time is sanitized with the
existing filename helper; generation time does not affect filenames. Use
`--overwrite` when regenerating a snapshot and `--quiet` to suppress progress,
not errors or stale-data warnings. All formats render before writes begin;
filesystem errors may still leave partial output and return a nonzero exit status.

## Corporation industry jobs report

Generate JSON, CSV, and Markdown from a corporation's latest stored jobs snapshot:

```bash
uv run eve-argus reports corporation-jobs --corporation-id 98196252 --to ./reports
```

Omit `--corporation-id` to use the configured corporation. The report command does
not refresh jobs; populate the dynamic database separately with
`uv run eve-argus fetch corporation-jobs`. A missing snapshot is an error; an empty
snapshot produces a valid report. Expired snapshots are reported with a warning.
Static types, market groups, and industry activities must already be available.
Public name lookups require ESI access; private location names remain `UNKNOWN`,
with their IDs preserved. Lookup errors are reported rather than hidden.
Name-resolution diagnostics remain in JSON and application logs, but are not
printed by the CLI or included as warnings in Markdown.

The destination directory is created when necessary. All three files use the stem
`corporation-jobs-<corporation_id>-<file_safe_received_at>`, where `received_at` is
the source snapshot's timestamp, not report generation time. For example:

```text
corporation-jobs-98196252-2026-10-17T22_07_37_553890662Z.json
corporation-jobs-98196252-2026-10-17T22_07_37_553890662Z.csv
corporation-jobs-98196252-2026-10-17T22_07_37_553890662Z.md
```

Use `--overwrite` to replace files from an earlier run of the same snapshot.
`--quiet` suppresses progress, but errors and warnings remain visible. All formats
are rendered before writing; filesystem errors can still leave partial output and
are reported with a nonzero exit status.

JSON includes source metadata and enriched jobs, with costs encoded as decimal
strings and absent values as null. CSV repeats metadata per job, uses empty cells
for absent values, slash-separated market paths, and headers only for empty
snapshots. Markdown includes source freshness, character summaries, and status
tables with job IDs, products, runs, and blueprint market paths.

Summary T/A/R/P counts mean current Total / Active / Ready / Paused; total excludes
historical and unrecognized statuses. Research aggregates copying, invention, ME,
and TE. An active job ending at or before report generation time is effectively
ready. Original statuses remain available in every format.
