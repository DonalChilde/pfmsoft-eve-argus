# Industry report proof

Standalone proof of the [industry report contract](../../prompts/industry-report.md).
All code, templates, and tests for this proof live here. Application source and
the project test tree are unchanged.

## Synthetic preview

From the project root:

```bash
uv run dev/proof-scripts/industry-report/run_report.py \
  --demo \
  --to dev/proof-scripts/proof-output/industry-report-demo
```

Produces a CSV plus linked Markdown and HTML page sets:

```text
OUTPUT/
  industry-report.csv
  html/
    index.html
    profit-opportunities.html
    assumptions.html
    sources.html
    group-GROUP_ID.html
  markdown/
    index.md
    profit-opportunities.md
    assumptions.md
    sources.md
    group-GROUP_ID.md
```

Open `html/index.html` (or `markdown/index.md`) for the Item Index table.
Profit Opportunities has its own page. Detailed product stories are grouped by
**static item group** (Frigate, Energy Weapon, etc.), not the broader category,
market group, or manufacturing family. Page titles and navigation use group names.
Stable numeric group filenames avoid name collisions and unsafe path characters;
missing classification uses `group-unknown`.
Navigation connects the index, opportunities, assumptions, provenance, and every
group. Product/strategy links and index/summary return links work across files
within each format. All pages remain usable locally, without external assets.
HTML uses the full available viewport width with side padding, without a
maximum-width cap; sidebar layouts give the remaining width to the content.
The index has a separate Item Index table per static group, ordered by group
name (unknown groups last), retaining market-path ordering within each group.
The HTML index lists product-group links in a sticky, independently scrollable
sidebar that jumps to these tables on the same page. Group links are listed under
static category headings, with categories and groups ordered alphabetically
(unknown categories last). Product links in each table
open their detailed entries; detail return links target the matching index row.
Main report links stay above the tables;
on narrow screens the group navigation stacks above it.
HTML group-detail pages use the same responsive sidebar layout, listing only
the product entries on that page, with same-page anchor links. Product links
move out of the top navigation; main report links and return links remain.
Group-detail pages omit links to other product-group pages from top navigation.
Profit Opportunities omits product-group page links from its top navigation;
its table's product and strategy links still open the detailed entries.
Assumptions and source provenance also omit product-group links from top
navigation, retaining the main report-page links.
Top navigation omits links to the current page and redundant page-heading
anchors; sidebar links and detail return links remain available.
The page has one table per hub in configured hub order, without a redundant Hub
column. Each retains descending-return ordering and all opportunity values.
The HTML sidebar links to each hub table; hubs with no qualifying scenarios show
an explicit empty message. Markdown uses the same hub table split.
CSV columns and calculations are unchanged. The in-memory single-document
render helpers remain available for focused tests; the CLI writes only page sets.

The demo has three **fictional** products covering T1, a component chain, a T2
module, and a T2 rig. Its prices, type IDs, recipes, and indices are synthetic,
not actual EVE quotes.

Use `--overwrite` to replace existing artifacts. All formats render before
writing, and existing paths are checked first. Writes are not an atomic
multi-file transaction: a filesystem failure can leave partial output.
Nested file collisions and directory blockers are checked before writing.
Overwrite replaces current generated paths but does not delete obsolete
group/category files or older monolithic exports; the new index links only current
pages. Use a fresh output directory when an exact current-file inventory matters.
Fixed filenames deliberately simplify prototype iteration; source metadata and
generation time are in the detailed companions rather than the filename.

The **External Shopping List** is an aligned plain-text **Name / Quantity** block
for copying into the game: a fenced text block in Markdown and preformatted text
in HTML. Material pricing and valuation remain in the per-job input table rather
than a duplicate shopping detail table.
Per-job inputs show total **m3** after Quantity, using the same volume basis as
the product summaries. The section displays **Total m3** and **Total Cost** summed
over its rows; any missing required value makes its total unavailable.
The table ends with a Total row summing m3 and Value ISK.
These are material-input totals, including internal component transfers, not an
external shopping or production-cost total: component inputs appear at their
own stages too. Quantities retain per-job ME rounding and internal transfer
values allocate whole component batches without surplus credit.
Names are left-aligned and integer quantities right-aligned, without grouping
separators or pipe delimiters. Quantities are combined by type ID across purchase
reasons, including external inputs whose prices are unavailable.

In Markdown and HTML, the item index links each Product to its detail section,
with a return link to the matching index entry. Index strategy labels are plain
text. Each product's Strategy Summaries table links its strategies to their
details, with return links to the matching summary rows.
The top-level **Profit Opportunities** table lists only `history_average`
product/strategy/hub scenarios with unrounded return at least 20%, sorted by
descending return, then product name, type ID, strategy, station ID, and sale
basis. It reuses history-average Sales Data economics, omits the constant Sale
basis column, and adds Product, Strategy, regional Avg traded Units/day, and
Unit cost ISK (the strategy's full production cost per produced unit).
Hub appears immediately after Strategy.
Alongside History avg Price/unit, Sell 5% Price/unit and the immediately following
5% depth show the same
hub's stored sell-order boundary price and depth, not historical depth.
These sell-order values do not change profit or return calculations. Missing
volume, sell price, or depth stays unavailable. Status warns when the unrounded
Sell 5% price is below the history-average price; otherwise it is blank, rather
than repeating the generic regional-proxy notice. An empty result is explicitly
stated. Detailed Sales Data statuses and CSV remain unchanged.
The index includes batch cost and total job-hours alongside unit cost; detail
anchors are used by navigation links rather than displayed as a separate column.
Index rows sort by the product's full market-path string (not displayed), then
product name and type ID. Strategies retain their existing order within each
product; products without a market path sort last. Detail and CSV ordering are
unchanged.

Each product's **Strategy Summaries** table displays the static **Portion Size**;
actual produced units still come from the manufacturing recipe and batch runs.
Its **m3** column follows Units and shows produced units times packaged volume,
falling back to item volume when packaged volume is unavailable. Unknown volume
or unavailable output is shown as Unavailable.
The Item Index includes the same **m3** column immediately after Units.

Between **Sales Data** and **Per-job material inputs**, jobs are grouped under
**Copying**, **Invention**, and **Manufacturing**, each with job details.
Blueprint and BPC details are shown in the job tables, without separate
blueprint-allocation or BPC-input subsections.
Invention job rows include per-attempt success probability, the resulting
invented blueprint followed by Licensed runs/BPC and ME/TE, and total invention consumables plus invention
installation fees for the budgeted attempts. This job total excludes source
copying costs; missing input prices leave it unavailable.
Invention job rows omit remaining runs and place dependency references last.
Copying job rows also omit remaining runs and show Copying Cost ISK before
dependencies, including copying consumables and installation fees.
Copying and invention job durations are displayed as Job-hours rather than seconds.
Manufacturing job durations are also displayed only as Job-hours.
Activity cost columns are labeled Copying Cost ISK, Invention Cost ISK, and
Manufacturing Cost ISK. Manufacturing cost includes the job's materials and
installation fees, excluding its own BPC preparation. Internally manufactured
components use their fully rolled-up transfer prices, as in per-job inputs.
**Installation Costs** follows with the per-job installation-charge breakdown,
grouped by activity with Job-hours as its final column; these costs exclude materials and internal
transfers, and job-hours are not elapsed completion time. Empty activities are
explicitly marked; incomplete plans show only the known jobs.

Markdown/HTML tables show product, material, and blueprint names instead of game
IDs; redundant ID columns are omitted. Missing names are explicitly shown as
`UNKNOWN <id>`. CSV retains its numeric IDs for data processing, and generated
job references remain visible for tracing dependencies. Unique owned BPO item
IDs are not displayed; the planner still uses the selected instance internally.

## Stored snapshots

Supply explicit database paths and a corporation ID:

```bash
uv run dev/proof-scripts/industry-report/run_report.py \
  --static-database /path/to/argus-static.sqlite \
  --dynamic-database /path/to/argus-dynamic-db.sqlite \
  --history-database /path/to/market-history-db.sqlite \
  --corporation-id CORPORATION_ID \
  --to dev/proof-scripts/proof-output/industry-report-stored
```

Choose one mutually exclusive selection:

- `--owned`: all supported published BPO types in the corporation's latest stored
  blueprint inventory, plus every supported published invention product reachable
  from those source BPOs. Existing BPCs do not count as owned BPOs.
- `--not-owned`: all supported published source BPO types absent from that
  inventory, plus their supported published invention products. Assume access to
  missing published BPOs (including component BPOs) at `--me 10 --te 20` by
  default. Override with `--me 0..10` and `--te 0..20`; these values apply only
  to hypothetical BPOs, not actual owned research or invented BPC ME2/TE4.
  Acquisition and research costs/time are excluded. Hypothetical access is
  explicitly warned in stderr and report assumptions; no fake owned item IDs
  are generated.
- `--sample`: at most four representatives: an ordinary product, a component
  chain, a T2 non-ship/non-rig product, and a T2 ship/rig. This remains the default
  when no selection flag is given. Missing categories produce warnings.
- Repeat `--type-id PRODUCT_TYPE_ID` to select exact products, not blueprint IDs.
  This does not automatically expand invention products.

The BPO catalog uses published blueprint/product types with supported ordinary
manufacturing and a copying activity; invention-result blueprints and reactions
are not source BPOs. Selections are deduplicated and sorted by product type ID.
Not-owned selection rejects zero/negative copying-time stubs with named warnings
before granting hypothetical BPO access. This is a static-data eligibility
heuristic, not proof that an original is available for purchase.
For not-owned source BPOs, both the blueprint and its manufactured product must
be published and have a non-null `market_group_id`. The same restriction applies
to hypothetical component BPO access. This checks market membership, not current
order availability. Invented BPC results retain their existing published
eligibility; they are not purchased source BPOs. In not-owned mode, manufactured
outputs must also have `meta_level` 0 or 5, including invention products and
hypothetical component BPO outputs. Other or missing meta levels are excluded;
the blueprint's own meta level is not used. Owned/sample/explicit product
selection is unchanged.
Invalid copying, invention, or manufacturing durations encountered during planning
produce named incomplete estimates rather than aborting the report.
No matching BPOs is an explicit error. Ambiguous manufacturing/invention routes
remain incomplete rather than being chosen arbitrarily.
`--corporation-id` must be positive and is required with stored database paths;
`--to` is the required output directory. Existing exports require `--overwrite`.

For example, add `--owned` to the stored command above for all owned routes, or
`--not-owned --me 8 --te 16` for hypothetical unowned routes. Both use only stored
snapshots; a large selection may have many unavailable prices or histories.

For an Atron invention example, add `--type-id 608`, `--type-id 11200`, and
`--type-id 11202` to include Atron, Taranis, and Ares. The latter two products are
resolved from the Atron Blueprint's static invention results (Taranis Blueprint
and Ares Blueprint), with access verified against the owned source BPO.
Selecting Atron alone by `--type-id 608` does not automatically add its invention
products; `--owned` includes all three when the Atron BPO is owned.

All databases open with SQLite `mode=ro` and `query_only`. No settings
initialization, migrations, data writes, ESI requests, or implicit refreshes occur.
Each source selects its latest scoped response and reads rows by that response
ID. The latest blueprint snapshot is corporation-scoped; orders are
region-scoped and filtered to each hub's primary station.
History freshness uses snapshot `received_at`: stale only when strictly older
than `--history-stale` days (default 7; nonnegative integer). Exactly seven days
is still fresh with the default. This overrides expiry-based freshness for
history receipts only; other sources retain Argus/source expiry precedence.
The same rule applies to stderr warnings and Markdown/HTML provenance.

Required preparation includes stored corporation blueprints, CCP adjusted
prices, Osmeden industry indices, and market orders. Missing price/industry/BPO
snapshots fail with fetch hints. Missing hub orders/history retain unavailable
outcomes; missing required material prices or blueprint access retain explicitly
incomplete production estimates. Warnings appear on stderr. A successfully
rendered report may contain incomplete rows; operational failures exit nonzero.
Planner diagnostics identify products, blueprints, and materials by name and
type ID (for example, `Missing Jita sell 5% price: Ion Thruster (11531).`).
Unknown names are explicitly labeled `UNKNOWN` alongside the ID. The same
warnings are retained in exported detail pages; CSV schema remains unchanged.

## Fixed proof assumptions

- Osmeden high-sec NPC station, Omega, all relevant skills 5, no implants,
  structures/rig bonuses, or decryptors. Station service availability is not
  verified: this is an estimate, not an executable installation plan.
- BPC-only manufacturing. Copies preserve the selected real BPO's ME/TE pair,
  or use the explicitly assumed unowned BPO ME/TE in `--not-owned` mode.
  Invented T2 BPCs use ME2/TE4; licensed runs come from the static invention
  product's `quantity` field, not hard-coded family defaults. Nonpositive
  quantities leave estimates explicitly incomplete.
- Copying consumables are fully consumed per licensed run of the copied BPC,
  without manufacturing ME reductions. Include them at Jita input prices in BPC
  preparation, rolled-up costs, per-job inputs, and the external shopping list.
  Copies used for invention include materials for all budgeted source-copy runs.
  Stored Jita price lookups include copying-only inputs as well as manufacturing
  and invention inputs.
- Ten manufacturing runs for unit costs, except T2 ships/rigs use the invention
  product's licensed-run quantity. Actual
  output uses recipe output per run, separately from static portion size.
- Invention budgets `ceil(1/p)` attempts **per required BPC**. All budgeted
  attempts incur datacores, source copying, job charges and job-hours. This
  rounded-up expected-attempt convention is not an exact statistical expectation
  or a confidence guarantee. No extra successful BPCs are credited.
- NPC facility tax 0.25%, production SCC 4%, Alpha surcharge zero. Use
  activity-specific PTV: manufacturing `EIV * runs`, copying
  `0.02 * source EIV * licensed runs`, invention `0.02 * target EIV * attempts`.
  The mechanics reference's 2% research SCC is not applied.
- All external inputs use **Jita primary-station sell 5%**, including datacores,
  purchased components and reaction products. Use the existing order summary
  with its default outlier factor 100. No other prices are substituted.
- Make-all expands supported manufacturing dependencies; reaction products are
  always purchased. Missing required BPOs leave make-all incomplete except for
  hypothetical published BPO access in `--not-owned` mode.
  When a product has no supported manufacturing subassemblies, omit its redundant
  make-all estimate from CSV, Markdown, and HTML. Reaction-only inputs do not
  qualify; a missing subassembly BPO still retains an incomplete make-all estimate.
- Aggregate shared component demand within each product/strategy, round per
  actual BPC-sized manufacturing job, and charge full batch costs without surplus
  credit. Do not share costs across independent compared products.
- Ignore existing BPCs/inventory. Exclude hauling and historical BPO
  purchase/research expenses. Sum job-hours without claiming elapsed scheduling.
- Sales tax defaults to 3.6% and the sell-order broker fee to 1%. The `build_report()` proof
  API accepts fractional overrides. Sales tax applies to all sale bases;
  broker fees apply to `sell_5pct` and `history_average`, but not `buy_5pct`.
  Relisting fees are not modeled.
  Markdown/HTML sale outcome tables are labeled **Sales Data** and display sales
  tax and broker fee separately as batch totals.
  Detail Sales Data tables include regional Avg traded units/day immediately
  before Status for every sale basis; missing volume remains unavailable.
- Sell all reference output. Return means profit divided by production cost,
  not profit divided by revenue. A zero cost has no defined percentage return.
- History uses ten consecutive calendar days ending at each region/type's
  latest stored completed date. Reuse the existing history summary: volume
  divided by ten, prices weighted by observed volume, coverage shown. Missing
  days are not represented as confirmed zero trades. No history is unknown;
  observed zero volume gives zero daily sales but no usable history sale price.

Currency stays in `Decimal`; PTV and fee composition are proof-local Decimal
translations of the reference equations to avoid binary-float currency
conversion. Material quantities and durations reuse project formulas.
Reference durations are floats converted using `Decimal(str(value))`.
Detailed reports round display to two decimals; CSV retains calculation
precision. Game-client whole-ISK rounding, two-decimal material rounding, and
stored SCI precision retain the mechanics reference's caveats.

## Validation

```bash
uv run pytest -q dev/proof-scripts/industry-report
uv run ruff check dev/proof-scripts/industry-report
uv run ruff format --check dev/proof-scripts/industry-report
```

Tests use synthetic recipes and temporary databases built from existing project
SQL schemas. They cover known monetary totals, invention budgeting, ME/TE
selection, shared demand, surplus, copy limits, missing/ambiguous/cyclic routes,
zero/missing history, latest snapshot linkage, station sell 5% valuation, source
freshness, unchanged database hashes, output escaping, Markdown formatting,
overwrite protection, and CLI failures.

## Project-code observations

No project-code changes are required for this proof.

- There is no production-chain resolver or HTML renderer to reuse; those remain
  proof-local.
- The reference monetary formulas accept floats. A future production report
  would benefit from a deliberately agreed Decimal interface rather than
  silently converting ISK to floats.
- Static identity loading includes unpublished types because current blueprint
  recipes reference unpublished skills. The production reader already supports
  this through `only_published=False`; no project-code change is needed.
- The history helper returns zero prices for zero volume; this adapter marks
  those sale prices unavailable. Its public latest-date reader is region-wide,
  so the proof uses a narrow region/type query to anchor each selected window.
- History rows expose receipt/expiry metadata but not response IDs. Preserve
  each receipt actually used; do not claim historical response-ID linkage.
- Unsupported/ambiguous blueprint routes and multi-output manufacturing recipes
  remain outside this first proof.
