# Pfmsoft Eve Argus

## Fetch market history

```bash
uv run eve-argus fetch market-history --region-id 10000002 --type-id 34
```

Fetches history for one region and item type into the configured market-history
database. Both IDs are required. Unexpired stored responses skip fetching; Argus
expiry overrides ESI expiry, and missing expiry triggers a refresh.

Successful updates store response metadata and daily history transactionally.
Overlapping dates are replaced and older dates remain stored. Empty responses
still record metadata. Failures are reported with a nonzero exit status.
Use `--quiet` to suppress progress and success messages, but not update errors.

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
