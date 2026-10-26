# Report evidence guide

Paths below are starting points. Read current implementations and tests before
using their details as requirements. Historical prompts record intent, not proof
that a behavior remains implemented.

## Primary evidence: registered reports

The [report registry](../../../../src/pfmsoft/eve_argus/cli/reports/__init__.py)
exposes the following commands.

| Command under `eve-argus reports` | Scope | Outputs |
| -------------------------------- | ----- | ------- |
| `corporation-jobs` | One corporation's latest stored jobs response | JSON, CSV, Markdown |
| `corporation-blueprints` | One corporation's latest stored blueprints response | JSON, Markdown, owned CSV, missing-BPO CSV |
| `hub-prices` | All entries in `MARKET_HUBS`, using stored regional orders | CSV and JSON per hub |

All three require `--to` and offer `--overwrite` and `--quiet`. Corporation
commands accept a positive `--corporation-id`, falling back to configuration.
Hub prices currently has no hub-selection option and deliberately no Markdown.
Do not impose either decision on unrelated reports.

HTML is an optional format for future reports supported by this skill's design
workflow. None of these current CLI exemplars emits HTML; treat HTML layout,
templates, and assets as report-specific decisions, not established CLI behavior.

### Corporation jobs

- [CLI orchestration](../../../../src/pfmsoft/eve_argus/cli/reports/corporation_jobs.py):
  `corporation_jobs()` and `_generate_reports()`.
- [Collection and models](../../../../src/pfmsoft/eve_argus/reports/corp_industry_jobs.py):
  `collect_corporation_jobs_report()`, `CorporationJobReportRow`,
  `CorporationJobsReport`.
- [Renderers and Markdown context](../../../../src/pfmsoft/eve_argus/reports/corp_industry_jobs_render.py):
  `build_markdown_context()`, `render_corporation_jobs_json()`,
  `render_corporation_jobs_csv()`, `render_corporation_jobs_markdown()`.
- [Packaged template](../../../../src/pfmsoft/eve_argus/templates/corp_industry_jobs/report.md.jinja2).
- [Report tests](../../../../tests/pfmsoft/eve_argus/reports/test_corp_industry_jobs.py).
- [CLI tests](../../../../tests/pfmsoft/eve_argus/test_cli_corporation_jobs_report.py).

Use this exemplar for instance-level rows, character/status summaries, and
identity/location enrichment. Output stems are
`corporation-jobs-{corporation_id}-{received_at}`.

### Corporation blueprints

- [CLI orchestration](../../../../src/pfmsoft/eve_argus/cli/reports/corporation_blueprints.py):
  `corporation_blueprints()` and `_generate_reports()`.
- [Collection and models](../../../../src/pfmsoft/eve_argus/reports/corp_blueprints.py):
  `classify_blueprint_quantity()`, `collect_corporation_blueprints_report()`,
  `CorporationBlueprintReportRow`, `OwnedBpoSummary`, `MissingBpoRow`,
  `CorporationBlueprintsReport`.
- [Renderers and Markdown context](../../../../src/pfmsoft/eve_argus/reports/corp_blueprints_render.py):
  `build_markdown_context()`, `render_corporation_blueprints_json()`,
  `render_corporation_blueprints_markdown()`, `render_owned_blueprints_csv()`,
  `render_missing_bpo_csv()`.
- [Packaged template](../../../../src/pfmsoft/eve_argus/templates/corp_blueprints/report.md.jinja2).
- [Report tests](../../../../tests/pfmsoft/eve_argus/reports/test_corp_blueprints.py).

Use this exemplar for classification, owned-versus-expected comparisons, and
multiple export views with distinct grains. Do not transfer blueprint quantity
semantics or BPO analysis to other datasets.
Output stems are `corporation-blueprints-{corporation_id}-{received_at}`,
with `-owned.csv` and `-missing-bpo.csv` for the CSV views.

### Hub prices

- [CLI orchestration](../../../../src/pfmsoft/eve_argus/cli/reports/hub_prices.py):
  `hub_prices()` and `_generate_reports()`.
- [Collection and models](../../../../src/pfmsoft/eve_argus/reports/market_hub_prices.py):
  `collect_market_hub_prices()`, `PriceSummaryMetrics`, `MarketHubPriceRow`,
  `MarketHubPricesReport`.
- [Renderers](../../../../src/pfmsoft/eve_argus/reports/market_hub_prices_render.py):
  `render_market_hub_prices_json()`, `render_market_hub_prices_csv()`.
- [Report tests](../../../../tests/pfmsoft/eve_argus/reports/test_market_hub_prices.py).

Use this exemplar for local on-demand summaries, system scope, validation of
response provenance/static paths, nullable buy/sell sides, and precise prices.
It calculates dataset summaries from stored orders, then collects per-hub
models. Types with neither side are omitted. The current model uses
`schema_version=2`; that is not a universal starting version.
Output stems are `price-summary-{hub}-{received_at}`.

## Shared lifecycle and important distinctions

The CLI resolves settings/scope and selects stored responses; collectors receive
datasets and produce typed report models. Snapshot rows are selected using their
response metadata ID. Source metadata includes receipt and expiry information.
Stale inputs warn but still render, with Argus expiry preferred when available.

Corporation collection is asynchronous and uses `EveArgusResources`, including
ESI universe-name resolution. Hub-price orchestration uses synchronous read-only
connections and local calculations. **No source snapshot refresh** does not mean
**no possible network access** for the corporation reports.

Both corporation Markdown renderers pass template output through
[`format_markdown()`](../../../../src/pfmsoft/eve_argus/helpers/markdown.py),
the shared `mdformat` wrapper with `extensions=["tables"]`. Future Markdown
reports must use this helper rather than configure `mdformat` independently.
Cell escaping remains a separate responsibility handled by `markdown_cell()`.

All three commands collect/render before creating report files and preflight
existing output paths. Hub prices additionally validates all required hub inputs
before writing. Writes are not an atomic multi-file transaction; a filesystem
failure may leave a partial output set. Filenames use sanitized components.

Warnings/errors remain visible with `--quiet`; progress uses Rich stderr output.
Expected operational failures are logged and exit nonzero. Missing corporation
scope uses CLI parameter validation.

There is no common report base class or universal output manifest to extend.
Do not add one just to make a new report resemble all the others.

At the time this guide was created, the discovered standalone CLI report test
file was for corporation jobs. The blueprint and hub report suites do not imply
equivalent CLI coverage. Add focused coverage for new/changed CLI behavior
rather than treating historical test counts as current evidence.

## Secondary evidence: prompts and prototypes

Historical production design records:

- [Jobs prompt](../../../../dev/prompts/corp-jobs-report.md).
- [Blueprints prompt](../../../../dev/prompts/corp-blueprints-report.md).
- [Hub-price prompt](../../../../dev/prompts/market-hub-price-summary.md).

Prototype sources:

- [Reprocessing value report](../../../../dev/proof-scripts/reprocessing/generate_value_report.py).
- [Reprocessing price proof](../../../../dev/proof-scripts/reprocessing/test_hub_prices.py).
- [Earlier blueprint summary](../../../../dev/proof-scripts/blueprints-report-summary-1.py).
- [Proof-script guidance](../../../../dev/proof-scripts/readme.md).
- [Reprocessing design prompt](../../../../dev/prompts/scrap-metal-reprocessing.md).

Optional ideas demonstrated by the reprocessing value report:

- Normalized value CSVs and separate deal CSVs, with input/material detail and
  per-hub presentation in Markdown.
- Explicit missing-data names, thin-market flags, and assumption status rather
  than silently dropping incomplete rows.
- Separate ranked positive-profit opportunities from incomplete/unrankable
  rows, while retaining those rows in exports.
- Explicit calculation rules: recovered quantities rounded down; incomplete
  material values yield an unknown total rather than a misleading partial sum.
- Stated cost/revenue direction and margin denominator. The prototype's margin
  uses profit divided by cost; do not assume a conventional revenue denominator.
- Readable numeric formatting in Markdown, with pipe escaping and flattened
  newlines in table cells.

These are not production requirements. In particular, fixed yields, depth
thresholds, profitability assumptions, hub directions, rounding, and ranking
rules require report-specific confirmation before adoption.

Use proof scripts to test assumptions with isolated or synthetic data, not as a
reason to run live requests or inspect private generated outputs. Promotion
requires typed production code, CLI integration, deterministic tests, and an
explicit report contract.
