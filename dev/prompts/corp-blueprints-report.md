# Corporation blueprints reports: planning prompt

Investigate and plan the migration of the corporation blueprint reports to the
current dynamic/static datasets and report architecture established by the
corporation jobs report. Produce an evidence-based implementation plan first;
do not implement application changes until the plan and open decisions are approved.

Read applicable repository instructions and current code. Treat this prompt as
desired behavior, not proof of current implementation. Distinguish verified facts,
proposals, and unanswered questions.

## Goal and scope

Provide useful corporation blueprint inventory and owned-vs-missing blueprint
original (BPO) reporting from the latest stored corporation blueprints snapshot,
with JSON, CSV, and Jinja Markdown outputs and CLI integration.

The existing owned/missing BPO behavior is the comparison baseline. Include an
enriched item-level inventory of all owned originals and copies, including
unpublished and nonmarket types. See the approved scope and implementation plan
below for resolved decisions.

Do not force the new implementation to fit legacy models. Do not migrate the
unrelated static blueprint-summary report, add production calculations, refresh
ESI inventory automatically, or implement authenticated private-location resolution.
Do not delete legacy files without approval.

## Repository references

### Current report architecture to follow

- [Jobs collection and dataclasses](../../src/pfmsoft/eve_argus/reports/corp_industry_jobs.py)
- [Jobs renderers and Markdown context](../../src/pfmsoft/eve_argus/reports/corp_industry_jobs_render.py)
- [Jobs CLI orchestration](../../src/pfmsoft/eve_argus/cli/reports/corporation_jobs.py)
- [Reports command registration](../../src/pfmsoft/eve_argus/cli/reports/__init__.py)
- [Jobs Jinja template](../../src/pfmsoft/eve_argus/templates/corp_industry_jobs/report.md.jinja2)
- [Report tests](../../tests/pfmsoft/eve_argus/reports/test_corp_industry_jobs.py)
- [CLI tests](../../tests/pfmsoft/eve_argus/test_cli_corporation_jobs_report.py)

Reuse appropriate helpers and patterns, but avoid importing job-specific models
or introducing a generic reporting framework for this migration.

### Legacy corporation reports: reference only

- [Owned/missing BPO collection](../../src/pfmsoft/eve_argus/reports/old/corp_missing_bpo.py)
- [Owned/missing BPO Markdown renderer](../../src/pfmsoft/eve_argus/reports/old/corp_missing_bpo_markdown.py)
- [Existing BPO templates](../../src/pfmsoft/eve_argus/templates/corp_missing_bpo)

The legacy BPO report:

- Limits its owned and missing lists to published types under blueprint market
  group ID `2`.
- Excludes copies (`quantity == -2`) from ownership.
- Counts `quantity == -1` as one original and positive quantities as stacks of
  that many originals.
- Aggregates originals by type and sums original counts.
- Selects one actual best original/stack by highest ME, then TE, then quantity.
  It does not independently combine maximum ME and maximum TE from different items.
- Groups Markdown owned/missing sections by market path and shows missing base prices.

Verify these rules against current ESI semantics and static data before preserving
them. Published market membership is not proof of NPC availability, current sale
availability, or a complete catalogue of all possible BPOs.

### Data sources and existing helpers

- [Dynamic models](../../src/pfmsoft/eve_argus/dynamic/models.py):
  `CorporationBlueprintRecord`, `CorporationBlueprintsDataset`, and response metadata.
- [Dynamic readers](../../src/pfmsoft/eve_argus/dynamic/read.py):
  `corporation_blueprints_responses` and `corporation_blueprints`.
- [Static readers](../../src/pfmsoft/eve_argus/static/read.py) and
  [models](../../src/pfmsoft/eve_argus/static/models.py): types and market groups.
- [Legacy market-path filter](../../src/pfmsoft/eve_argus/helpers/market_path_filters.py):
  deprecated and typed for legacy MarketGroup models; do not use it in new reports.
- [Universe-name fetch](../../src/pfmsoft/eve_argus/esi/fetch.py) and
  [validation](../../src/pfmsoft/eve_argus/esi/validate.py).
- [Resource lifecycle](../../src/pfmsoft/eve_argus/eve_argus.py).
- [Filename sanitization](../../src/pfmsoft/eve_argus/helpers/file_safe_string.py).

## Architecture and data contracts

Keep database selection/loading and file writing outside public report collection
and rendering functions.

```text
CLI / caller
  -> resolve corporation and select latest stored blueprint snapshot
  -> load blueprint, types, and market-groups datasets
  -> collect/enrich once, using one captured generation timestamp
  -> derive inventory and owned/missing views from that collected data
  -> render JSON, CSV, and Markdown without network/database access
  -> write the selected outputs
```

Use documented, typed, slotted, keyword-only dataclasses; prefer immutable collected
records. Specify concrete function signatures and output schemas in the plan.

Include corporation identity, source response ID, `received_at`, `expires_at`,
`argus_expires_at`, and generation time. Keep source timestamps separate from
generation time and reuse jobs-report freshness semantics.

For item-level inventory, preserve all original blueprint fields, including:

- Corporation ID, item ID, type ID, source response metadata ID.
- Location ID and location flag.
- Raw quantity, ME, TE, and runs.

Add type name, market-group ID/path, derived original/copy classification and
physical count where valid, and optional location name. Do not reinterpret copy
runs as number of copies or overwrite raw ESI sentinel values.

For aggregated owned BPOs, specify type/name/path, total originals, and the
ME/TE pair from the selected best actual original. If including the chosen item ID,
use a deterministic tie-breaker after existing preference criteria.

For missing BPOs, specify type/name/path and nullable static base price. Base price
is a static reference value, not a live market quote. Do not introduce float
round-trips for Decimal values or invent precision absent from the source.

## Snapshot and static-data behavior

- Select the newest response for the requested corporation using the existing
  reader's ordering and deterministic metadata-ID tie-breaker.
- Never merge snapshots or substitute an older nonempty snapshot.
- No snapshot is an actionable error suggesting `fetch corporation-blueprints`.
- An empty snapshot is valid: inventory and owned lists are empty, but the missing
  list still contains the complete eligible comparison universe.
- Use expired snapshots without fetching new inventory; retain stale-data notices.
- Load types with `only_published=False` so owned historical/unpublished items can
  be enriched. Apply published filtering explicitly to the BPO comparison universe.
- Reuse precomputed static market paths; do not reconstruct market-group ancestry.
- Distinguish a type with no market group from a missing referenced static record.
- Missing required type/group records must be explicit errors or documented,
  visible diagnostics, not silent row loss or invented values.

The plan must explain whether owned items outside the eligible BPO universe remain
visible in a separate inventory section. Do not silently change legacy comparison
semantics while broadening inventory coverage.

## Name-resolution policy

Learn from the jobs-report investigation: accepting an integer does not prove it
belongs to the expected namespace.

- Resolve blueprint type names from static types, not universe names.
- Resolve corporation name through the existing public name-lookup flow.
- Never send item IDs, response metadata IDs, location flags, quantity/efficiency
  values, or runs to universe names.
- Location IDs may refer to public stations, private structures, or containers.
  Investigate representative blueprint locations before defining eligibility;
  do not assume job-location behavior proves blueprint-location behavior.
- Exclude values outside the endpoint's positive int32 range. An in-range value
  is only a candidate, not proof of public resolvability.
- Use exact `UNKNOWN` for unresolved location names and preserve raw IDs/flags.
- Do not print name-resolution warnings in CLI output or add a Markdown warning
  section. Diagnostics may remain in collected JSON/application logs.
- Preserve actual API/transport/validation errors; do not disguise an ESI outage
  as a successful report of entirely unknown names.
- Deduplicate eligible IDs, reuse existing batching/validation, and check returned
  categories. Do not duplicate endpoint batching logic.

Live probes are optional investigation, not required tests. If needed and approved,
use read-only database samples and bounded singleton requests; distinguish expected
rejection from rate limits/timeouts/server failures. Do not modify inventory or
expose credentials/private data in committed fixtures.

## Markdown requirements

- Use packaged Jinja templates, `StrictUndefined`, and typed context dataclasses.
- Header: corporation name/ID, generation time, source response ID, received time,
  both expiry fields where available, and freshness.
- Preserve the owned/missing BPO sections grouped by market path.
- Owned table: type ID/name, original count, and selected ME/TE pair.
- Missing table: type ID/name and nullable static base price.
- If inventory is included, distinguish originals/stacks from copies and show
  item ID, type/name, market path, quantity/count, ME, TE, copy runs, location,
  and location flag as appropriate. Avoid a single unreadably wide table.
- Treat location name/ID and location flag as distinct concepts/columns.
- Escape Markdown pipes, line breaks, and other formatting-sensitive names/paths.
- Specify stable sorting and clear empty-state messages for every view.
- Test actual table row boundaries and equal header/separator/data column counts,
  not just presence of expected strings.

## CLI and output conventions

Propose a command under the existing reports group, for example:

```bash
uv run eve-argus reports corporation-blueprints --corporation-id <id> --to <directory>
```

- Use `--to`, not `--output-dir`; create the destination directory as necessary.
- Default corporation from settings; require neither character nor credential
  arguments for public name lookups.
- Use `--overwrite` to replace existing files and `--quiet` to hide progress.
  Actual errors and stale-snapshot warnings remain visible.
- Include corporation ID and the source snapshot's `received_at`, sanitized with
  `file_safe_string`, in all filenames; use a consistent shared stem per view.
- Render all requested formats before writing; errors have nonzero exit status.
  Do not claim multi-file atomicity unless implemented and tested.
- Document exact JSON/CSV contracts, fixed CSV columns and null handling, stable
  order, and preservation of raw IDs/sentinels.

Resolve whether inventory and BPO comparison are separate commands, separately
named output sets from one command, or sections of one report. In particular,
define how CSV represents item-level, owned-aggregate, and missing rows without
silently dropping a view or creating an ambiguous mixed-row schema.

## Tests and validation

Use red/green tests for new functions, mock external dependencies, and use in-memory
databases and temporary output directories. Cover:

1. Corporation-scoped latest snapshot selection, ordering, empty-latest behavior,
   missing snapshots, and stale/unknown expiry.
2. Original sentinel `-1`, copy sentinel `-2`, positive stacks, and explicit policy
   for unexpected quantity values. Preserve raw runs/sentinels.
3. Counts across multiple originals/stacks/locations; copies alone do not satisfy
   BPO ownership.
4. Best actual ME/TE pair rather than independent maxima; deterministic ties.
5. Eligible published market-blueprint universe; unpublished, nonmarket, and
   out-of-scope owned items handled according to the agreed contract.
6. Missing BPO set difference, including empty inventories and duplicate owned types.
7. Static names/paths/base prices, missing references, no-market-group cases,
   null values, and deterministic order.
8. ID allowlisting/deduplication, unsupported locations, expected name categories,
   omitted names, failed batches, and malformed responses.
9. Matching records/aggregates across formats, CSV quoting/nulls, JSON precision,
   escaped Markdown and aligned tables, empty sections, and renderer purity.
10. Root CLI registration, configured/explicit corporation, `--to`, exact
    timestamp-based filenames, overwrite refusal, quiet behavior, and failure paths.
11. End-to-end CLI tests using real dynamic readers and renderers with mocked ESI,
    verifying that no inventory refresh is triggered.

Run targeted pytest tests and scoped Ruff lint/format checks. Validate new Python
types/diagnostics. If a live smoke test is appropriate, report its limitations
and verify exact output item/type sets and aggregate counts, not just file existence.

## Required planning output

Return:

1. Verified current behavior and relevant file/symbol references.
2. Recommended scope, report schemas, function interfaces, and CLI/output layout.
3. Open decisions requiring approval, especially inventory/BPC scope, comparison
   universe, owned items outside that universe, unexpected quantity semantics,
   location lookup policy, and CSV delivery.
4. Ordered implementation steps, affected files, and true dependencies.
5. Acceptance criteria and focused validation commands.
6. Risks and migration/legacy cleanup notes.

Keep the implementation focused. Reuse small, genuinely shared helpers where useful;
do not refactor unrelated jobs-report behavior or add dependencies without approval.

## Output

- collected data as json
- markdown report
- csv of all owned bp
- csv of missing bpo

## Approved scope (2026-10-18)

- Include every owned blueprint item/stack in JSON and the owned CSV, whether
  original or copy, published or unpublished, market-listed or nonmarket.
- Compare against published static types beneath blueprint market group `2`.
  A copy alone does not satisfy ownership of an original.
- Markdown includes owned-original summaries and missing originals grouped by
  market path, plus separate detailed originals/stacks and copies inventory tables.
- Unexpected quantity values (`0` or below `-2`) are explicit data errors.
- Produce exactly four files from one command and one collected report:
  JSON, Markdown, all-owned inventory CSV, and missing-BPO CSV.
- Keep the existing `--to`, `--overwrite`, `--quiet`, snapshot timestamp filename,
  stale-data, and name-resolution-output conventions established by the jobs report.

## Concrete implementation plan

### 1. Contracts and verified inputs

Use `CorporationBlueprintsDataset`, `TypesDataset`, and `MarketGroupsDataset`.
The dynamic readers already select responses newest-first by `received_at` and
response metadata ID and preserve empty snapshots. No schema changes or new
latest-response query are required.

Build the comparison universe from published types whose referenced market group's
`int_path` contains `2`, using the supplied static datasets. The deprecated legacy
filter accepts a different model and must not be imported. Validate required group
references and the blueprint root so missing static data cannot masquerade as an
empty comparison universe.

Define these frozen, slotted, keyword-only dataclasses in a new
`reports/corp_blueprints.py` module:

- `CorporationBlueprintReportRow`: every source record field plus `type_name`,
  `published`, nullable `market_group_id`/`market_path`, `location_name`,
  `blueprint_kind` (`original`, `stack`, or `copy`), and `item_count`.
  For `-1` and `-2`, `item_count` is one; positive quantities retain their count.
  Raw `quantity` and `runs` remain unchanged.
- `OwnedBpoSummary`: type ID/name/path, total original count, selected item ID, and
  its actual ME/TE pair. Aggregate all owned originals, not just eligible comparison
  types, so nonmarket/unpublished originals remain visible. Include an
  `in_comparison_universe` boolean to distinguish the broader summary from the
  legacy comparison scope.
- `MissingBpoRow`: eligible type ID/name/path and nullable static base price.
- `CorporationBlueprintsReport`: source metadata, corporation identity,
  generation time, nullable freshness, item inventory, original summaries,
  missing originals, and optional structured/text diagnostics.

Select the best actual original by ME, TE, then raw quantity (legacy preference);
break remaining ties by smallest item ID. Never combine efficiencies from separate
items. Missing types are the comparison universe minus owned original type IDs.

Sort inventory by item ID. Sort summary/missing rows by path components, name, and
type ID; define a stable no-market bucket distinct from missing static references.

### 2. Collection and enrichment

Public collector interface:

```python
async def collect_corporation_blueprints_report(
    *,
    blueprints: CorporationBlueprintsDataset,
    types: TypesDataset,
    market_groups: MarketGroupsDataset,
    esi_link: EsiLink,
    schema: EsiSchema,
    generated_at: Instant,
) -> CorporationBlueprintsReport: ...
```

Validate quantity semantics, row corporation/response consistency, and required
static references before building aggregates. No database access or file writing
belongs here. Use static names and existing path tuples.

Before implementing location enrichment, inspect distinct stored blueprint location
values read-only. Public station candidates may be resolved with the corporation;
unsupported/private locations remain `UNKNOWN`. Verify any station eligibility rule
against endpoint semantics, not just int32 fit. If eligibility remains ambiguous,
ask for a policy decision rather than send arbitrary item/container IDs in a batch.
Live probing, if needed, requires approval as described above.

Reuse existing name batching and response validation, checking categories and
required corporation identity. API/transport/validation errors fail explicitly.
Keep location diagnostics out of CLI/Markdown. Keep source timestamps and raw
inventory fields unchanged.

Pure helpers should handle quantity classification, candidate collection,
comparison-universe construction, and aggregation only where useful for clarity
and testing; avoid a new framework.

### 3. Rendering contracts

Add `reports/corp_blueprints_render.py`. Every renderer receives only the collected
report and returns text; none accesses a clock, network, database, or filesystem.

- JSON: one object containing metadata, all inventory rows, all original summaries,
  missing BPO rows, and diagnostics. Preserve nulls and raw sentinel fields.
- Owned CSV: one row per original/stack/copy record, not one row per type or per
  physical blueprint. Repeat metadata, preserve raw fields, and include all enriched
  inventory fields. Use fixed columns and slash-separated market paths.
- Missing CSV: one row per missing eligible type, with repeated metadata, type ID,
  name, market-group ID/path, and nullable base price. Both CSVs use empty optional
  cells, standard quoting, and headers even when empty.
- Markdown: metadata/freshness header, original summary by market path, missing
  BPOs by market path, detailed originals/stacks, and detailed copies. Include
  unpublished/nonmarket originals in the broader summary and explain its scope.
  Keep name/ID and location flag separate. For wide inventory sections, group by
  market path/location to avoid repeating unnecessary columns. Do not display
  copy run counts as original counts or invent runs for originals.

Use typed Jinja context dataclasses, packaged templates, and `StrictUndefined`.
Add templates under `templates/corp_blueprints/`, leaving legacy BPO templates
unchanged until removal is separately approved. Escape names/paths and explicitly
test real table structure, including optional/empty sections.

### 4. CLI and file layout

Add `cli/reports/corporation_blueprints.py` and register it in the existing reports
group:

```bash
uv run eve-argus reports corporation-blueprints --corporation-id <id> --to <directory>
```

Read the newest scoped snapshot, static types with `only_published=False`, and
market groups. Collect once, render all four outputs, then write UTF-8 files.
Capture generation time once. Do not call the inventory refresh endpoint.

For shared stem
`corporation-blueprints-<corporation_id>-<file_safe_received_at>`, write:

```text
<stem>.json
<stem>.md
<stem>-owned.csv
<stem>-missing-bpo.csv
```

Use the existing filename helper on source receipt time. Preflight all destinations
before enrichment/writing; do not overwrite any existing output without
`--overwrite`. Validate destinations and report write failures with nonzero status.
As with jobs reports, multi-file writes are not promised atomic.

### 5. Red/green implementation sequence and dependencies

1. Add quantity/model/universe/aggregation tests, then implement collection models
   and pure transformations. This is prerequisite to enrichment/rendering.
2. Establish the location eligibility policy, add mocked enrichment tests, and
   implement async collection. This depends on step 1.
3. Add JSON/CSV contract tests and Markdown context/table tests, then implement
   renderers/templates. This depends on the agreed models in step 1 and must be
   verified with the completed collector from step 2.
4. Add CLI tests, then wire the command and registration. This depends on collection
   and all four renderers.
5. Update README usage/output examples and this prompt's status. Run focused
   validation and inspect the final diff. Legacy deletion is not part of this work.

Tests mirror the production layout under `tests/pfmsoft/eve_argus/`. Add
`reports/test_corp_blueprints.py`, `reports/test_corp_blueprints_render.py`, and
`test_cli_corporation_blueprints_report.py` as appropriate.

### 6. Acceptance and validation

In addition to the test matrix above, explicitly verify:

- Every source record appears exactly once in JSON inventory and owned CSV.
- Copy-only ownership still leaves that type in the missing-original list.
- Unpublished/nonmarket originals appear in inventory and original summaries but
  never expand the missing-BPO comparison universe.
- An empty latest snapshot yields no inventory/owned summaries and every eligible
  comparison type in the missing output.
- Summary quantities equal the sum of original counts, never copy runs.
- Selected ME/TE values and selected item ID identify one real original record.
- All four files share metadata and source timestamp; no extra mixed-schema CSV
  or aggregate CSV is produced.
- Invalid quantity/static references and failed lookups produce explicit errors;
  unsupported locations alone do not.
- Existing jobs-report behavior remains unchanged.

Suggested commands after the proposed files exist:

```bash
uv run pytest tests/pfmsoft/eve_argus/reports/test_corp_blueprints.py \
  tests/pfmsoft/eve_argus/reports/test_corp_blueprints_render.py \
  tests/pfmsoft/eve_argus/test_cli_corporation_blueprints_report.py
uv run ruff check src/pfmsoft/eve_argus/reports/corp_blueprints*.py \
  src/pfmsoft/eve_argus/cli/reports tests/pfmsoft/eve_argus/reports \
  tests/pfmsoft/eve_argus/test_cli_corporation_blueprints_report.py
uv run ruff format --check src/pfmsoft/eve_argus/reports/corp_blueprints*.py \
  src/pfmsoft/eve_argus/cli/reports tests/pfmsoft/eve_argus/reports \
  tests/pfmsoft/eve_argus/test_cli_corporation_blueprints_report.py
```

Check Pylance diagnostics on touched Python modules and run existing jobs-report
tests as a registration/regression check. No application implementation or live
blueprint-location probing has been performed during this planning step.

## Implementation progress (2026-10-18)

- Implemented collection/immutable models in
  [corp_blueprints.py](../../src/pfmsoft/eve_argus/reports/corp_blueprints.py).
- Implemented JSON, owned CSV, missing-BPO CSV, and typed Markdown contexts in
  [corp_blueprints_render.py](../../src/pfmsoft/eve_argus/reports/corp_blueprints_render.py)
  and packaged [templates](../../src/pfmsoft/eve_argus/templates/corp_blueprints).
- Registered [corporation-blueprints](../../src/pfmsoft/eve_argus/cli/reports/corporation_blueprints.py)
  under the reports CLI, with all four timestamped files and agreed options.
- Quantity, aggregation, enrichment, rendering, and CLI tests share synthetic
  fixtures in [test_corp_blueprints.py](../../tests/pfmsoft/eve_argus/reports/test_corp_blueprints.py)
  rather than duplicating fixtures across three test modules.
- Extracted unchanged Markdown escaping to a small
  [shared helper](../../src/pfmsoft/eve_argus/helpers/markdown.py); jobs report
  behavior is preserved and covered by regression tests.
- Legacy report modules/templates have not been removed.

### Location investigation

A read-only inspection of the latest configured snapshot found 1,249 records:
794 original records, 109 copy records, and 346 stack records. Location values
included two station-range IDs and eleven 64-bit private IDs. Counts here refer
to records, not physical originals summed from stacks.

The [ESI asset-location reference](https://github.com/esi/esi-docs/blob/master/docs/asset_location_id.md)
documents the station namespace as 60000000-64000000 and distinguishes private
structures, containers, asset safety, and corporation offices. The blueprint
collector conservatively submits only station candidates in `[60000000, 64000000)`
and verifies returned categories. Other locations are `UNKNOWN`; int32 fit alone
does not qualify an ID. No live blueprint-location requests were needed.

### Implementation validation

- 52 blueprint tests and 64 jobs-report/CLI regression tests pass (116 total).
- Focused statement/branch coverage is 99% across blueprint collection, renderers,
  and CLI. Blueprint CLI and renderers have 100% coverage.
- Scoped Ruff lint/format and diff whitespace checks pass; new production modules
  and tests have no Pylance diagnostics.
- A read-only real-dataset smoke check with mocked public names rendered all four
  formats in memory: 1,249 inventory records, 784 owned-original types, 1,075
  missing-original types, and 1,265 physical originals. Item/type sets, original
  counts, and selected actual ME/TE pairs matched the source data. No report files
  were written and no live ESI requests were made by that check.
