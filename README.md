# Pfmsoft Eve Argus

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
`--region-id`, `--hubs`, or both, and exactly one type-selection mode:

| Mode                 | Candidate types                                                                                    | Market-group filters |
| -------------------- | -------------------------------------------------------------------------------------------------- | -------------------- |
| Repeated `--type-id` | Explicit IDs, including unpublished, nonmarket, and unknown types                                  | Not allowed          |
| `--active`           | Published, market-listed active types discovered independently for each region                     | Allowed              |
| `--market-types`     | Published types listed in static market groups                                                     | Allowed              |
| `--industry-types`   | Published, market-listed blueprint IDs plus materials and products across all blueprint activities | Allowed              |

Explicit regions run in command-line order, followed by hub regions for Jita,
Amarr, Dodixie, Hek, and Rens, with duplicates removed. Types are deduplicated
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
```

Industry selection requires a populated static blueprints dataset. It collects
each blueprint's own type ID, materials, and products from copying, invention,
manufacturing, reactions, material research, and time research. Skill-only IDs
are not included. IDs are deduplicated across blueprints and activities before
filtering, and the resulting selection is fetched for every selected region using
the same regional execution limits as the other modes. Missing blueprint data is
an explicit error before any history requests.

### Selection and filters

Regions are validated against the static map-regions dataset before network
requests. The original explicit single-pair invocation still permits regions
missing from static data; failures label them `Unknown region`.

`--include` and `--exclude` may be repeated with `--active`, `--market-types`,
and `--industry-types`, but not `--type-id`. Includes form a union of market-group
subtrees, including each group's directly assigned types. Excludes apply afterward,
regardless of option order, and always win. Filters only remove candidates; they
never introduce inactive or otherwise unselected types. Unknown groups, missing
required static datasets, and inconsistent market paths fail before network
requests. An empty selection is a successful regional no-op.

All generated selections (`--active`, `--market-types`, and `--industry-types`)
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

## Market hub price summaries

```bash
uv run eve-argus reports hub-prices --to ./reports
```

Exports the newest stored **system-scoped** price summary for each configured hub:
Jita, Amarr, Dodixie, Hek, and Rens. These are not regional or primary-station
prices. Inputs are opened read-only; no network, credentials, order fetching, or
summary recalculation is required. The configured static database build (latest
when unspecified) must already contain types and market groups.

Each hub produces CSV and JSON with a shared source-timestamp stem, for example:

```text
price-summary-Jita-2026-10-17T22_07_37_553890662Z.csv
price-summary-Jita-2026-10-17T22_07_37_553890662Z.json
```

Names and timestamps use the existing filename sanitizer. Hubs may have different
source timestamps; this is not a synchronized cross-hub snapshot. Missing hub
summaries fail with the complete list before any output is written. A newer
empty snapshot does not fall back to an older populated one. The separate
`fetch hub-orders` command saves summaries when fresh order data arrives; rerunning
a cached fetch does not necessarily recreate a missing summary.

JSON schema version `1` contains metadata and a `records` array sorted by
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
   `system_name`, `order_summary_response_id`, `generated_at`, `is_stale`.
2. `type_id`, `type_name`, `market_group_id`, `market_group_name`,
   `market_path_ids`, `market_path_names`, `has_buy_summary`, `has_sell_summary`.
3. Each metric below with `buy_` prefixes, then the same with `sell_` prefixes:
   `five_price`, `five_orders`, `five_items`, `lowest`, `highest`, `average`,
   `total_items`, `total_orders`, `filtered_items`, `filtered_orders`.

Prices are exact plain decimal strings, never binary floats; counts are
integers. JSON absent values are null; CSV absent values are empty cells, and
flags use `True` / `False`. Empty exports retain CSV headers and JSON metadata.
The summary response ID and source response metadata ID are separate provenance
keys, both preserved.

Metrics retain their stored meanings: `five_price` is the price threshold
reaching 5% of valid volume, including all orders tied at that cutoff—not a 5%
price band. `average` is volume-weighted over valid orders. `total_items` /
`total_orders` count valid orders; `filtered_items` / `filtered_orders` count
excluded outliers. The historical filter factor is not stored and is not
invented in exports.

Argus expiry overrides source expiry; absent expiry means unknown freshness.
Expired snapshots remain exportable with visible warnings. `--quiet` hides
progress, not errors or stale-data warnings. Use `--overwrite` to replace
existing files. All hub snapshots, paths, static references and renderings are
validated before writes; filesystem failures may still leave partial output
and return a nonzero exit status. No Markdown report is generated.

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
