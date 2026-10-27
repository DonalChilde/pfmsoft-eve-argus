# Report requirements

Use this as an outline; fill only applicable sections. Label each important
decision as established convention, report-specific decision, or optional
prototype idea. Replace placeholders with measurable statements.

## Purpose

- Report name and proposed CLI command:
- Audience and decision supported:
- Questions answered:
- Non-goals:
- Closest implemented report and why:

## Inputs and scope

| Input | Scope/key | Selection rule | Required? | Provenance/freshness |
| ----- | --------- | -------------- | --------- | -------------------- |
| Source snapshot | | | | |
| Static enrichment | | | | |
| Other inputs | | | | |

- Required preparation/fetch/import commands:
- Explicit options and configured defaults:
- Network access for enrichment, if any:
- Cross-source alignment and permitted age differences:

| Condition | Required outcome |
| --------- | ---------------- |
| No stored snapshot | |
| Empty stored snapshot | |
| Stale snapshot | |
| Unknown expiry | |
| Missing name/static reference | |
| Inconsistent scope or provenance | |

## Data and calculations

- Row grain and unique key:
- IDs and human-readable names:
- Filters and exclusion precedence:
- Grouping and summary definitions:
- Formulas, units, and denominators:
- Monetary precision and rounding:
- Missing-value effects on totals/ranking:
- Sort order and tie-breakers:

Include a small worked example with exact expected rows and totals. For ranked
opportunities, define eligibility, direction, and the ranking metric.

## Outputs

| Artifact | Audience/grain | Schema or outline | Ordering |
| -------- | -------------- | ----------------- | -------- |
| JSON, if needed | | | |
| CSV view(s), if needed | | | |
| Markdown, if needed | | | |
| HTML, if needed | | | |

- Fields/columns with types, units, null representation, and precision:
- Provenance and freshness displayed/exported:
- Agreement rules across formats and summary/detail views:
- Filename pattern and source versus generation timestamps:
- Compatibility/versioning expectations:
- Markdown must be formatted with `mdformat` through the shared
  `pfmsoft.eve_argus.helpers.markdown.format_markdown()` helper, which enables
  the `tables` extension.
- HTML document/layout, autoescaping, accessible table headings, styling, and
  embedded versus linked asset requirements, if applicable:

## CLI and operations

- `--to`, `--overwrite`, `--quiet` behavior:
- Report-specific options and validation:
- Destination/collision checks and partial-write behavior:
- Progress, warnings, actionable errors, and exit status:
- Expected data volume and measurable performance target, if required:

## Implementation plan

- CLI registration and orchestration:
- Existing read helpers, models, and calculations to reuse:
- Collector inputs and typed output:
- Renderers, contexts, and packaged templates:
- Related help/user documentation:
- Intentional deviations from current patterns:
- Prototype ideas adopted, with justification:

## Acceptance examples

For each applicable requirement, state fixture/input, action, and exact expected
output or failure. Cover normal, empty, missing, stale, inconsistent, and
overwrite cases, plus numerical/schema checks and cross-format consistency.
For Markdown, verify shared-helper formatting, aligned tables, and formatting
idempotence.
For HTML, verify escaped content, document/table structure, asset availability,
and agreement with the other report formats.

## Open decisions and verification

- Decisions requiring user confirmation:
- Checks to run:
- Checks actually run and results:
- Limitations or deferred scope:
