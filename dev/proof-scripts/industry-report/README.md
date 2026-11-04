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

Produces `industry-report.csv`, `industry-report.md`, and `industry-report.html`.
The demo has three **fictional** products covering T1, a component chain, a T2
module, and a T2 rig. Its prices, type IDs, recipes, and indices are synthetic,
not actual EVE quotes.

Use `--overwrite` to replace existing artifacts. All formats render before
writing, and existing paths are checked first. Writes are not an atomic
three-file transaction: a filesystem failure can leave partial output.
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

Optionally repeat `--type-id PRODUCT_TYPE_ID`. These are product IDs, not
blueprint IDs. Without explicit IDs, select at most four representatives:
an ordinary product, a component chain, a T2 non-ship/non-rig product, and a T2
ship/rig. Missing sample categories produce warnings; ambiguous routes are not
chosen automatically.

All databases open with SQLite `mode=ro` and `query_only`. No settings
initialization, migrations, data writes, ESI requests, or implicit refreshes occur.
Each source selects its latest scoped response and reads rows by that response
ID. The latest blueprint snapshot is corporation-scoped; orders are
region-scoped and filtered to each hub's primary station.

Required preparation includes stored corporation blueprints, CCP adjusted
prices, Osmeden industry indices, and market orders. Missing price/industry/BPO
snapshots fail with fetch hints. Missing hub orders/history retain unavailable
outcomes; missing required material prices or blueprint access retain explicitly
incomplete production estimates. Warnings appear on stderr. A successfully
rendered report may contain incomplete rows; operational failures exit nonzero.

## Fixed proof assumptions

- Osmeden high-sec NPC station, Omega, all relevant skills 5, no implants,
  structures/rig bonuses, or decryptors. Station service availability is not
  verified: this is an estimate, not an executable installation plan.
- BPC-only manufacturing. Copies preserve the selected real BPO's ME/TE pair.
  Invented T2 BPCs use ME2/TE4, one run for ships/rigs and ten otherwise.
- Copying consumables are fully consumed per licensed run of the copied BPC,
  without manufacturing ME reductions. Include them at Jita input prices in BPC
  preparation, rolled-up costs, per-job inputs, and the external shopping list.
  Copies used for invention include materials for all budgeted source-copy runs.
  Stored Jita price lookups include copying-only inputs as well as manufacturing
  and invention inputs.
- Ten manufacturing runs for unit costs, except one for T2 ships/rigs. Actual
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
  always purchased. Missing required BPOs leave make-all incomplete.
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
