# Corporation jobs report

    Note there is code for an old non-working implementation of this report at

    - src/pfmsoft/eve_argus/reports/old/corp_industry_jobs_markdown.py
    - src/pfmsoft/eve_argus/reports/old/corp_industry_jobs.py
    - src/pfmsoft/eve_argus/templates/corp_industry_jobs
    - output examples at dev/proof-scripts/proof-output/esi-data-loader/corporation_industry_jobs*

    This is provided for reference, but may not provide all the desire new features. This code will be removed after new implementation is complete. Do not attempt to force the new implementation to fit the old code.

I want to implement a report for Corporation jobs.

The jobs are found in the dynamic database, and can be accessed via src/pfmsoft/eve_argus/dynamic/read.py

static data can be accesed by src/pfmsoft/eve_argus/static/read.py

The most current set of jobs should be used, and the received_at and expires_at information should be included in the markdown version of the report.

The public report function should take data arguments, accessing databases is outside the scope of the report.

## Required data

- Corporation jobs from the dynamic database
- types dataset from the static database
- market groups dataset from the static database
- industry_activities from the static dataset
- EsiLink and EsiSchema to allow name dereferencing.

## Data collection

id fields in the job records need to be dereferenced into names. Some of these are available from the static database types dataset, but others are more easily gotten from the src/pfmsoft/eve_argus/esi/fetch.universe_names. one or two will cause universe names to error. when we figure out which ones these are, they will be excluded, and we should note them in the docstring for the dynamic database model. Collect all valid ids, then make the universe_names call.

We should also include the market path for the blueprint. this can be found by getting the market group from static->types and getting the path from static->market-groups.

Use a dataclass to hold the collected data.

## Outputs

- A json file of the collected, dereferenced data.
- A csv file of same
- A markdown report of same.

Use jinja templates to generate the markdown version of the report.
templates are collected in src/pfmsoft/eve_argus/templates

## Flow

I envision one function that collects the required data. Then other functions that output that collected data into various formats.

## Agreed report behavior

- Preserve character summaries and status tables from the old report, improving
  columns with job IDs, blueprint market paths, products, and runs as appropriate.
- Markdown status tables show facility and installation location in separate
  `Facility` and `Location` columns, each retaining its name and ID.
- Use the static industry activities dataset for activity names.
- Preserve the raw status; derive an effective `ready` status only for an `active`
  job whose end time is at or before the captured report-generation time.
- Character summary T/A/R/P counts mean current total, active, ready, and paused.
  Current total excludes delivered, cancelled, and reverted jobs. Research aggregates
  copying, invention, ME, and TE.
- Unresolved location/facility names use the exact string `UNKNOWN`, retaining their
  raw IDs. Authenticated private-location resolution is a future enhancement.
- Name-resolution warnings are omitted from CLI output and Markdown. Keep the
  diagnostics in collected report data/JSON and application logs. Stale-snapshot
  warnings and actual lookup errors remain visible.
- Unsupported locations are expected limitations, not reasons to suppress network,
  validation, or other unexpected lookup failures.
- JSON, CSV, and Markdown use one collected dataset and one generation timestamp.
  Preserve all original fields and exact Decimal costs in JSON/CSV.

## CLI integration

Add `eve-argus reports corporation-jobs --corporation-id <id> --to <directory>`.
Use the configured corporation when `--corporation-id` is omitted; do not require
character or credential arguments for public name lookups.

The command reads the latest stored snapshot for that corporation without refreshing
jobs. No snapshot is an actionable error; an empty snapshot is a valid empty report.
Use the latest snapshot even when expired, showing its freshness in Markdown.
Load static types with `only_published=False`.

Write all three UTF-8 output files with this shared stem:

```text
corporation-jobs-<corporation_id>-<file_safe_received_at>
```

Sanitize the source snapshot's `received_at` using
[`file_safe_string`](../../src/pfmsoft/eve_argus/helpers/file_safe_string.py), not the
generation timestamp. Append `.json`, `.csv`, and `.md`. Create the destination
directory if necessary. Refuse existing files unless `--overwrite` is supplied.
Collect and render all formats before writing, and report any write failure.

## Name lookup investigation and policy

On 2026-10-18, one row from the latest configured corporation snapshot was tested
against `PostUniverseNames`, one ID field per request. The snapshot contained 113
jobs, received at `2026-10-17T22:07:37.553890662Z`.

| Field | Observed result | Report policy |
| --- | --- | --- |
| `corporation_id` | Resolved as corporation | Look up |
| `installer_id`, `completed_character_id` | Resolved as character | Look up when present |
| `facility_id`, `location_id` | Resolved as station | Look up eligible public IDs; exclude values outside positive int32 range |
| `blueprint_type_id`, `product_type_id` | Resolved as inventory type | Use static types |
| `blueprint_location_id`, `output_location_id` | HTTP 400: cannot coerce 64-bit ID to int32 | Exclude; unresolved names are `UNKNOWN` |
| `blueprint_id` | HTTP 400: cannot coerce item ID to int32 | Preserve ID only; exclude |
| `job_id` | HTTP 404: invalid ID | Preserve ID only; exclude |
| `activity_id` | Accepted `4` as inventory type "Constellation", not an activity | Use static industry activities |
| `response_metadata_id` | Accepted `29` as inventory type "Credits", not response metadata | Local identifier only; exclude |

Across the complete snapshot, both blueprint/output location fields contained six
distinct 64-bit IDs. Facility and installation location fields each contained one
public station ID. This supports the current exclusions but does not prove that
every other snapshot uses the same kinds of locations.

The candidate helper was then exercised over all 113 jobs. Its five deduplicated
IDs resolved successfully in one batch: one corporation, three characters, and
one station. Returned IDs and categories matched the expected identities exactly.

Use
[`collect_universe_name_ids`](../../src/pfmsoft/eve_argus/reports/corp_industry_jobs.py)
to build the deduplicated candidate set. Check response failures and expected name
categories during enrichment: a successful HTTP response alone does not establish
that the name belongs to the intended ID namespace. Do not infer invalid IDs from
timeouts, rate limits, or server errors.

## Implementation status

- Completed: read-only snapshot investigation and singleton live ESI probes.
- Completed: documented ID policy and tested candidate collection helper.
- Completed: immutable collected report dataclasses and async enrichment using
  static names/market paths and validated public universe names.
- Completed: JSON, CSV, and packaged Jinja Markdown rendering, including character
  summaries, status sections, source metadata, and enrichment limitations.
- Completed: registered `reports corporation-jobs` CLI with `--to`, source-timestamp
  filenames, `--overwrite`, and `--quiet` (warnings/errors remain visible).
- Completed: mocked ESI tests, in-memory database CLI integration tests, output
  consistency/precision checks, and Markdown table layout tests.
- Legacy report modules/templates remain in place; deletion requires approval.

## Validation

- 63 report/CLI tests pass with external resources mocked.
- 88 tests pass when including related dynamic-reader and fetch-helper regressions.
- Focused statement/branch coverage is 98% across report collection, rendering, and
  CLI modules; the report CLI module has 100% coverage.
- Scoped Ruff lint/format checks pass. Production report modules have no Pylance
  diagnostics.
- A live in-memory rendering smoke test used read-only configured databases and
  public ESI names: all 113 stored jobs appeared in JSON, CSV, and Markdown with
  exactly matching job ID sets, three character summaries, and seven status
  sections. No report files were written by that smoke test.
