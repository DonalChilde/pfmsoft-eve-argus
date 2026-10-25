# Market hub system price summary exports: planning prompt

## Approved implementation decisions

Implementation requested on 2026-10-18:

- Command: `eve-argus reports hub-prices --to ./reports`.
- All configured hubs; no hub-selection option or Markdown output.
- Fail before writing and list every hub missing a stored regional order snapshot.
- **Omit types with neither buy nor sell summaries**, overriding the original
  preservation recommendation below.
- UTF-8 without BOM, JSON schema version 2.
- Filenames: `price-summary-<file_safe_system_name>-<file_safe_received_at>`.
  The source receipt timestamp, including fractional seconds, uses the existing
  helper and is not replaced by generation time.

Implemented with offline read-only loading, typed collection, pure CSV/JSON
renderers, registered CLI, focused tests, and README schema documentation.
The original planning material below is retained as rationale; the approved
decisions above take precedence over its open proposals.

### On-demand refactor (2026-10-25)

- Select the newest regional order response with `market_orders_responses()`.
- Load the whole region once with `market_orders()` and reuse that dataset for
  any hubs sharing the region.
- Call `calculate_dataset_summaries()` with each hub's `system_id`; do not issue
  per-type queries or read/write the deprecated persisted summary tables.
- No new database read-query functions are required.
- Schema v2 removes the persisted `order_summary_response_id`, retains the raw
  order snapshot's `response_metadata_id`, and adds the actual `filter_factor`.
  The current factor is the existing calculation default, `100.00`.
- Keep offline, read-only inputs, source-timestamp filenames, nullable sides,
  stale-data warnings, and preflight-before-write behavior.
- Fetch source orders with `fetch market-orders --hubs`. An empty latest region
  or one without orders in a hub system produces an empty export, not fallback.

Current validation covers real SQLite raw-order snapshots with no stored
summaries, system-vs-station scope, depth/outlier calculations, metadata and both
export formats, missing/empty snapshots, read-only inputs, and one dataset read
per distinct region (including hubs sharing a region).

Historical validation for the original stored-summary implementation included
synthetic collector/renderer contracts and registered CLI
tests using real local SQLite readers/writers, alongside the existing corporation
report and summary-calculation regressions. The collector and CLI have 100%
focused coverage; combined export coverage is 99%. A read-only smoke test against
the configured databases generated ten temporary files and verified matching
CSV/JSON type sets: Jita 19,000; Amarr 14,148; Dodixie 11,896; Hek 9,691;
Rens 8,163. Temporary outputs were removed after verification.

## Original planning material (historical)

The stored-summary requirements below describe the original implementation.
The approved on-demand refactor above supersedes them.

Develop an evidence-based implementation plan for exporting the current stored
market hub system pricing summaries as CSV and JSON. Read applicable repository
instructions and current code first. Do not implement application changes until
the plan and unresolved behavior decisions have been approved.

## Requested outcome

- Separate CSV and JSON files for each configured market hub system.
- Include market paths and IDs paired with their names.
- One CSV record per item type, with buy and sell summaries on the same record.
- Use the hub system name, not its numeric ID, in filenames.
- Optimize the exports for spreadsheet import and third-party applications.
- No Markdown price report is required.

Follow the established corporation-report separation of data loading, collection,
rendering, and file writing, without importing corporation-specific report models
or creating a generic export framework.

## Verified repository starting points

- [Configured hubs](../../src/pfmsoft/eve_argus/models/market_hubs.py):
  `MARKET_HUBS` supplies region/system IDs and names, plus primary-station identity.
  Current hubs are Jita, Amarr, Dodixie, Hek, and Rens. Use this source rather than
  duplicating the list or parsing the explanatory market-hubs document.
- [Market orders fetch command](../../src/pfmsoft/eve_argus/cli/fetch/region_orders.py):
  `fetch market-orders --hubs` stores regional orders only. The legacy
  `fetch hub-orders` command was removed; it previously saved summaries scoped
  with `system_id=hub.system_id`, not the primary station. The current report
  report now calculates summaries on demand from the stored regional orders.
- [Dynamic readers](../../src/pfmsoft/eve_argus/dynamic/read.py):
  `order_summary_responses` lists saved scopes newest-first by source receipt time,
  then summary response ID; `order_summaries` loads a saved summary response.
- [Summary models](../../src/pfmsoft/eve_argus/dynamic/models.py):
  `OrderSummaryResponse`, `OrderSummaryDataset`, `BuySellSummary`, and
  `OrderSummaryRecord`. A type can have either, both, or neither summary side.
  Dataset records retain type membership even when both sides are absent.
- [Summary calculations](../../src/pfmsoft/eve_argus/dynamic/order_summary.py):
  inspect the existing depth, outlier-filter, weighted-average, and count semantics.
  Export these values as stored; do not recalculate or redefine them.
- [Static readers](../../src/pfmsoft/eve_argus/static/read.py) and
  [models](../../src/pfmsoft/eve_argus/static/models.py): type names and market groups
  with precomputed ID/name paths.
- [Reports CLI](../../src/pfmsoft/eve_argus/cli/reports/__init__.py),
  [blueprint CLI](../../src/pfmsoft/eve_argus/cli/reports/corporation_blueprints.py),
  and [jobs CLI](../../src/pfmsoft/eve_argus/cli/reports/corporation_jobs.py):
  patterns for `--to`, `--overwrite`, `--quiet`, source-timestamp filenames,
  preflight checks, and error reporting.
- [Filename helper](../../src/pfmsoft/eve_argus/helpers/file_safe_string.py):
  use for both hub name and source timestamp.

## Scope and snapshot selection

Export system summaries, not regional summaries and not primary-station summaries.
For each hub:

1. Find saved summary responses for its region.
2. Filter to the exact system scope:
   `region_id == hub.region_id`, `system_id == hub.system_id`,
   and `location_id is None`.
3. Select the newest matching saved summary using the reader's existing ordering.
4. Load with `order_summary_response_id`, not the source `response_metadata_id`.
   These IDs represent different things and are not interchangeable.

Do not select an entire region's newest response before filtering scope. Never
merge snapshots or substitute a region/station report for a missing system report.

"Current" means newest stored matching summary, not necessarily unexpired data.
Retain receipt/expiry metadata and stale-data notices. Do not fetch orders, generate
missing summaries, or silently refresh anything while exporting. Hubs may have
different source timestamps; do not claim a synchronized cross-hub snapshot.

The hub fetch command currently writes summaries only when new order data arrives.
If orders exist but the required summary does not, report that explicitly; do not
assume rerunning a cached fetch will necessarily repair it. Planning should explain
an accurate remediation without broadening this export into a fetch refactor.

## Collected data contract

Use documented, typed, slotted, keyword-only dataclasses, preferably frozen.
Public collection takes supplied datasets and hub identity, not connections or
paths. Rendering is pure, with no network, database, clock, or file-writing access.
All names should be available from static datasets and configured hubs: no ESI
name calls or character/credential requirements are needed.

Suggested per-hub metadata:

- Explicit schema version, proposed `1`, for third-party consumers.
- Hub system and region IDs/names.
- Summary response ID and source response metadata ID.
- Source `received_at`, `expires_at`, `argus_expires_at`.
- Export generation time and nullable freshness, following existing report policy.
- Scope clearly identified as `system`.

Suggested item fields:

- `type_id`, `type_name`.
- Nullable `market_group_id`, `market_group_name`.
- Market path ID components and name components in JSON.
- Corresponding separator-joined path columns in CSV.
- Buy and sell summaries, including every stored metric:
  `five_price`, `five_orders`, `five_items`, `lowest`, `highest`, `average`,
  `total_items`, `total_orders`, `filtered_items`, `filtered_orders`.

Use `buy_` and `sell_` prefixes for CSV metrics, for example `buy_five_price` and
`sell_five_price`. Do not create separate buy and sell CSV rows.

Pair exported entity IDs with names. Internal response IDs are provenance keys
and do not need invented names. Do not include a station identity as if it were the
scope; primary-station context is unnecessary for the requested system export.

Load types with `only_published=False` so stored historical/unpublished types remain
exportable. A type with no market group has null/empty group and path values, not
an invented path. Missing required static records are explicit errors or an agreed
diagnostic policy, not silently dropped rows.

Validate row type IDs, side flags, and scopes against the enclosing dataset/hub.
Include deterministic record ordering, proposed ascending `type_id`.

## CSV and JSON contracts

CSV:

- Fixed documented columns and exactly one record per exported type per hub.
- Repeat hub identity and provenance metadata on each row so files/rows remain
  meaningful when combined in a spreadsheet or database.
- Flatten metrics using the side prefixes above.
- Add `has_buy_summary` and `has_sell_summary` flags so absence is explicit.
- Missing side metrics use empty cells, never artificial zero prices/counts.
- Write Decimal prices as exact plain decimal strings without currency symbols,
  thousands separators, or float conversions. Counts remain integer strings.
- UTF-8, standard CSV quoting, documented delimiter/newline behavior. No formulas.
- Header-only output for an empty dataset. Decide explicitly whether a UTF-8 BOM
  is wanted; recommend normal UTF-8 unless spreadsheet compatibility requires it.

JSON:

- One metadata envelope and an ordered array of enriched type records.
- Buy and sell summaries are nested objects or null; metric keys match their
  source meanings.
- Prices are exact decimal strings, counts are JSON integers, missing values null.
- Paths are arrays of IDs/names rather than ambiguous delimiter-encoded strings.
- Preserve both summary and source IDs; do not lose metadata merely because the
  dataset is empty.

Keep both outputs consistent about which types are included. Recommended default:
preserve all source dataset members, including types with neither side, with both
flags false and absent metrics. Such rows are not evidence of a zero market price.
Confirm this behavior before implementation rather than silently filtering them.

Document metrics accurately: `five_price` is the existing 5%-of-valid-volume depth
threshold, not a 5% price band or arithmetic average; ties at that price are included.
`average` is volume-weighted over valid orders, and filtered counts describe excluded
outliers. The calculation's filter factor is not persisted, so do not invent a
historical factor in metadata. Derive best buy/sell interpretation from actual
stored metrics rather than introduce unrelated spread/profit calculations.

## CLI and filenames

Proposed command:

```bash
uv run eve-argus reports hub-prices --to ./reports
```

Default to all configured hubs, producing two files per hub. Use `--overwrite` and
`--quiet` consistently with existing commands. Optional hub selection is a proposal,
not a prerequisite; avoid extra options unless requested.

Suggested shared stem:

```text
price-summary-<file_safe_system_name>-<file_safe_received_at>
```

Example:

```text
price-summary-Jita-2026-10-18T18_00_00Z.csv
price-summary-Jita-2026-10-18T18_00_00Z.json
```

Use source receipt time, not generation time. Retain numeric system IDs inside the
data, not as a substitute for the system name in filenames. Detect empty sanitized
names and filename collisions before writing; do not silently overwrite another hub.

Create `--to` when needed. Preflight all selected hub snapshots and output paths,
then collect/render before writing. Recommend failing with a list of missing hubs
rather than silently exporting an incomplete set. Ask for approval if partial export
with warnings is preferred. Filesystem failures may still leave partial output;
do not claim all-file atomicity without implementing/testing it.

Prefer existing read-only connection/static-store helpers for an offline export;
inspect resource lifecycle before choosing the CLI resources. Do not require an
ESI schema download or working network merely to export stored local summaries.

## Markdown recommendation

Do not generate a Markdown copy of the full price tables. It would be large, harder
to filter/join, and less useful than CSV/JSON for this workflow.

If a human-readable artifact becomes useful later, consider a small optional export
manifest showing hubs, scope, source timestamps/freshness, type/side counts, and links
to data files. This is a navigation/health summary, not another price report, and is
out of scope unless requested. CLI completion messages can serve that purpose now.

## Implementation plan and tests to produce

Plan narrowly scoped collection, CSV/JSON renderers, CLI orchestration/registration,
and README/schema documentation. Do not change summary calculations or database
schema unless investigation proves a blocking requirement.

Use red/green tests with synthetic datasets, in-memory SQLite, temporary paths,
and mocked external dependencies. Cover:

- Exact region/system scope selection amid newer unrelated region/station scopes.
- Newest matching receipt time and summary-ID tie-breaker.
- Different timestamps across hubs, stale/unknown expiry, and missing hub summaries.
- Buy-only, sell-only, two-sided, neither-sided, and completely empty datasets.
- One CSV record per type, side prefixes, stable columns/order and explicit absence.
- Exact Decimal preservation, integer counts, JSON nulls and CSV empty cells.
- Static names, path IDs/names, unpublished types, no market group, missing references.
- Scope/type/side inconsistencies rejected explicitly.
- CSV quoting for commas/newlines/quotes in names and paths; do not use line counts
  as proof of CSV record counts.
- Matching type sets, scope, metadata, and metrics across CSV and JSON.
- Per-hub names in exact filenames, sanitization/collision detection, and shared
  source-timestamp stems.
- All configured hubs, overwrite refusal, invalid destination, quiet behavior,
  visible errors, and no success-shaped partial export.
- End-to-end root CLI export using real readers/renderers without live ESI access.

Return verified current behavior, proposed function/data contracts and file changes,
dependency-ordered implementation steps, acceptance criteria, validation commands,
and explicit decisions needing approval. In particular settle missing-hub policy,
neither-sided rows, command naming, and any need for hub selection. The recommendations
above are planning defaults, not a claim that these choices were already approved.
