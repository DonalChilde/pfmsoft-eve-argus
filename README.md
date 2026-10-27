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

## Market hub price summaries

```bash
uv run eve-argus reports hub-prices --to ./reports
```

Calculates **system-scoped** price summaries on demand for Jita, Amarr, Dodixie,
Hek, and Rens from each region's newest stored order snapshot. These are not
regional or primary-station prices. Each regional dataset is loaded once and
summarized in memory for its hub systems, without per-type database queries.
Inputs are opened read-only; no network, credentials, or order fetching is
required, and calculated summaries are not saved to the database. The configured
static database build (latest when unspecified) must already contain types and
market groups.

Each hub produces CSV and JSON with a shared source-timestamp stem, for example:

```text
price-summary-Jita-2026-10-17T22_07_37_553890662Z.csv
price-summary-Jita-2026-10-17T22_07_37_553890662Z.json
```

Names and timestamps use the existing filename sanitizer. Hubs may have different
source timestamps; this is not a synchronized cross-hub snapshot. Missing regional
order snapshots fail with the complete list of affected hubs before any output
is written. Use `fetch market-orders --hubs` to fetch source orders. A newer empty
snapshot, or one with no orders in the hub system, does not fall back to an older
populated one. Persisted price-summary tables are not read.

JSON schema version `2` contains metadata and a `records` array sorted by
`type_id`. Each record has type and market-group IDs/names, nullable
`market_path_ids` / `market_path_names` arrays, and nested `buy_summary` /
`sell_summary` objects (or null). Unpublished stored types are included. Types
with neither side are omitted; a missing side is not a zero price.

CSV has one record per exported type, with both sides on the same row. It uses
UTF-8 without a BOM, comma delimiters, standard quoting, LF record terminators,
and `/`-joined paths. Embedded newlines in names remain quoted field content.
The fixed columns, in order, are:

1. `response_metadata_id`, `received_at`, `expires_at`, `argus_expires_at`,
   `schema_version`, `scope`, `region_id`, `region_name`, `system_id`,
   `system_name`, `filter_factor`, `generated_at`, `is_stale`.
2. `type_id`, `type_name`, `market_group_id`, `market_group_name`,
   `market_path_ids`, `market_path_names`, `has_buy_summary`, `has_sell_summary`.
3. Each metric below with `buy_` prefixes, then the same with `sell_` prefixes:
   `five_price`, `five_orders`, `five_items`, `lowest`, `highest`, `average`,
   `total_items`, `total_orders`, `filtered_items`, `filtered_orders`.

Prices are exact plain decimal strings, never binary floats; counts are
integers. JSON absent values are null; CSV absent values are empty cells, and
flags use `True` / `False`. Empty exports retain CSV headers and JSON metadata.
The source `response_metadata_id` identifies the regional order snapshot. Schema
v2 removes `order_summary_response_id` because on-demand summaries have no stored
summary ID, and adds `filter_factor` as an exact decimal string in JSON and CSV.

Metrics use the existing whole-dataset summary calculations: `five_price` is the
price threshold reaching 5% of valid volume, including all orders tied at that cutoff—not a 5%
price band. `average` is volume-weighted over valid orders. `total_items` /
`total_orders` count valid orders; `filtered_items` / `filtered_orders` count
excluded outliers. The default outlier `filter_factor` is `100.00`: buy prices
below best/factor and sell prices above best*factor are excluded. The actual
factor used for the calculation is recorded in the export.

Argus expiry overrides source expiry; absent expiry means unknown freshness.
Expired snapshots remain exportable with visible warnings. `--quiet` hides
progress, not errors or stale-data warnings. Use `--overwrite` to replace
existing files. All hub snapshots, paths, static references and renderings are
validated before writes; filesystem failures may still leave partial output
and return a nonzero exit status. No Markdown report is generated.

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
