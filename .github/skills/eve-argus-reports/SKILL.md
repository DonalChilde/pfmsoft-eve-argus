---
name: eve-argus-reports
description: 'Design, implement, extend, or review eve-argus CLI reports. Use when defining report requirements, snapshot inputs, calculations, JSON/CSV/Markdown/HTML outputs, report templates, freshness warnings, or report acceptance tests. Ground decisions primarily in implemented CLI reports and secondarily in proof-scripts.'
---

# Eve Argus reports

Develop reports that turn stored EVE data into trustworthy, reproducible answers
and useful exports. Cover both requirements/design and implementation; do not
start coding when the request is only for a design or review.

## Authority and goals

Use this evidence order:

1. Current registered CLI reports, their collectors, renderers, templates, and
   tests.
2. Related report prompts and documentation, checked against current code.
3. Prototypes in `dev/proof-scripts`, as ideas to evaluate, not requirements.

The current exemplars are `reports corporation-jobs`, `reports
corporation-blueprints`, and `reports hub-prices`. Read the relevant paths in the
[evidence guide](./references/report-patterns.md) before applying a pattern.
Re-check the command registry: this guide is a starting map, not a frozen API.
When code and tests disagree, identify the discrepancy rather than silently
choosing one or copying a defect.

Optimize for:

- A clear question and decision the report helps its reader make.
- Traceable inputs, explicit assumptions, and meaningful missing-data behavior.
- Consistent results across formats, stable schemas, and predictable ordering.
- A practical CLI with safe output handling and visible failures.
- Reuse of the existing data, calculation, collection, and rendering layers.

These are design goals. Do not claim that every existing report already meets
every proposed acceptance criterion.

## Workflow

### 1. Establish the report contract

Identify the audience, question, scope, input datasets, and desired outputs.
Use the [requirements template](./assets/report-requirements.md) as a checklist
or response outline. Create a filled-in document only when requested.

Separate requirements into:

- **Established convention**: supported by implemented CLI behavior.
- **Report-specific decision**: needed for this report, not a universal rule.
- **Optional prototype idea**: requires explicit adoption and production tests.

Ask about unresolved decisions that materially affect behavior: selection scope,
aggregation, exclusions, missing inputs, ranking, precision, or output schema.
Do not invent a default or expose new options merely because a prototype does.
Record intentional departures from existing reports.

### 2. Trace inputs and provenance

- Follow the nearest existing command through snapshot selection, collection,
  rendering, and tests.
- Report from stored source snapshots; do not implicitly fetch or refresh them.
  This is not a blanket promise of offline operation: existing corporation
  collectors can resolve names through ESI resources. Specify any enrichment
  network access separately.
- Define what "latest" means per scope and how rows are tied to their response
  metadata. Never mix snapshots accidentally.
- Preserve the metadata needed to identify the inputs and judge freshness.
  Follow existing Argus-expiry precedence over source expiry where applicable.
- Distinguish absent snapshots, empty snapshots, stale snapshots, missing
  enrichment, and invalid/inconsistent data.
- Follow the established stale-data behavior: warn and render, without silent
  refresh. If expiry is unknown, do not invent a fresh/stale value.
- Make missing required data actionable, naming the relevant fetch/import step
  after checking its actual command.
- For multiple sources, specify alignment and freshness per source; one source
  timestamp must not imply that every input was collected together.

### 3. Define rows, summaries, and calculations

- Define the row key and grain before grouping or joining. State whether rows
  represent jobs, blueprint instances, types, systems, or another entity.
- Keep database selection/orchestration separate from report collection.
  Collectors should accept explicit inputs and return typed report models.
- Reuse existing models, read helpers, calculations, and name/path resolution
  where appropriate. Follow the nearby synchronous or asynchronous pattern;
  neither is universal.
- Preserve IDs alongside readable identity where needed for traceability.
  Specify treatment of unknown names and locations rather than discarding rows.
- Define filters, group keys, totals, sorting, tie-breakers, and exclusions.
  Validate scopes, references, and provenance where relevant.
- Define units, denominators, rounding stage, precision, and nullable fields.
  Preserve `Decimal` precision for monetary calculations; do not casually
  convert prices to binary floats.
- Treat unknown values as unknown, not zero. Define how they affect totals,
  rankings, and eligibility.
- Build the report model once for a scope and render its formats from that same
  model. Avoid repeated queries and duplicated business logic in renderers.

### 4. Specify presentation and artifacts

- Choose output formats for the audience. Corporation reports demonstrate
  JSON/CSV/Markdown; hub prices deliberately have CSV/JSON only.
  HTML is also an optional format for future reports, not an output currently
  supplied by these CLI exemplars.
- Define JSON structure, CSV columns/order, and Markdown/HTML layouts separately.
  Multiple CSVs are appropriate for distinct grains, as with owned and missing
  blueprints; do not force every report into one flat file.
- Keep calculations out of templates. For Markdown, follow the packaged Jinja
  template and typed-context pattern used by corporation reports.
- Format all generated Markdown with `mdformat` through the shared
  `pfmsoft.eve_argus.helpers.markdown.format_markdown()` helper before returning
  or writing it. The helper enables the `tables` extension; do not duplicate
  formatter configuration in report modules.
- For HTML, render from the same collected model using packaged templates and
  HTML autoescaping. Define document structure, accessible table headings,
  styling, and whether assets are embedded or local/external dependencies.
  Do not apply Markdown formatting or cell-escaping helpers to HTML.
- Define deterministic ordering in each output. Summary views may differ in
  grain, but overlapping facts and totals must agree.
- Specify null/empty representation and CSV quoting. For nullable hub-price
  sides, the precedent is JSON `null` and empty CSV cells, not numeric zero.
- Use sanitized scope and source receipt timestamps in filenames, following
  the closest command. Distinguish generation time from source time.
- Define output names, schema compatibility, overwrite policy, and how a user
  locates the files. Do not generalize hub prices' `schema_version=2` into a
  required version for other reports.

### 5. Wire the CLI safely

- Register new production report commands under the existing `reports` group.
- Follow `--to`, `--overwrite`, and `--quiet` conventions. Where corporation
  scope applies, follow explicit ID overriding the configured default and
  positive-ID validation.
- Keep progress/success output on stderr in the existing Rich style.
  `--quiet` suppresses progress, not warnings or errors.
- Validate destination type, output collisions, and overwrite protection before
  writing. Follow the current reports' render-before-write pattern so collection
  and rendering failures do not leave report files.
- Use UTF-8 and the existing newline handling. Preserve exclusive creation
  unless overwrite is explicitly enabled.
- Surface expected operational failures with repository-standard logging,
  actionable stderr diagnostics, and nonzero exit status. Do not add broad
  exception catches or success-shaped fallbacks.
- State partial-write behavior honestly. Preflight checks are not an atomic
  multi-file transaction; do not promise rollback unless implemented and tested.
- Avoid speculative frameworks, base classes, or universal report options.

### 6. Verify the contract

Use Red/Green tests for new functions and behavior. Mock external dependencies.
Cover the applicable cases below; mark exclusions with a reason.

- CLI registration, help, defaults, explicit overrides, and invalid inputs.
- Latest scoped snapshot selection and response-ID linkage.
- Missing, empty, stale, and unknown-freshness inputs.
- Reference validation, enrichment gaps, filters, grouping, and exact
  calculations with known expected results.
- Numeric precision, missing values, sorting, and tie-breakers.
- Actual JSON shape and CSV header/row values, quoting, and cross-format
  agreement; Markdown/HTML content and summary totals where supplied.
- Markdown formatting through the shared helper, including aligned tables and
  stable formatting on repeated calls.
- HTML escaping, document/table structure, and asset availability where supplied.
- Filename sanitization, destination creation, existing-path protection,
  overwrite behavior, and collisions.
- Quiet mode retaining warnings/errors and failures returning nonzero.
- Collection/render/write failures, including documented partial-write behavior.
- No unintended source refresh; enrichment calls follow the agreed contract.

Run the smallest relevant existing pytest selection, then focused Ruff lint
and format checks for changed Python files. Use `uv run pytest ...`,
`uv run ruff check ...`, and `uv run ruff format --check ...`.
Follow repository type-safety checks where configured. Update related CLI help
and user documentation. Documentation-only skill edits do not need application
test runs unless documentation tests exist.

## Using proof scripts

Consult the prototype section of the [evidence guide](./references/report-patterns.md)
only after choosing the closest production exemplar. A proof can establish
feasibility, calculations, or presentation, but promotion requires explicit
requirements, production integration, and tests.

Do not read secrets, environment files, live databases, generated private
corporation reports, or logs to infer requirements. Prefer source and synthetic
fixtures. Do not run live ESI proofs or refresh application data as an incidental
part of designing a report.

## Deliverable

For design work, return the report contract, evidence-backed decisions, open
questions, and measurable acceptance criteria. For implementation, also provide
the completed CLI-to-output changes, related documentation, checks actually run,
and any known limitations. Distinguish verified behavior from proposals.
