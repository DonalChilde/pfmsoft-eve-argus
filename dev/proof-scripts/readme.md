# proof-scripts

This directory contains scripts that prove the operation of various components of eve-argus.

The python scripts are expected to be run with `uv run` from the project root directory, so that the dev env settings are used.

## Market-order summary performance comparison

Compare three ways of calculating both buy and sell summaries:

1. Load a whole stored snapshot and call `order_summary.calculate_dataset_summaries`.
2. Discover types through `read.market_order_types` and call
   `read.calculate_market_order_summary` **once per type**, returning a
   `(buy_summary, sell_summary)` tuple from a single order query.
3. Call `read.market_orders_filtered` once for the requested scope, then pass the
   returned tuple to `order_summary.calculate_order_summaries`.

```bash
# Start with a bounded smoke run against the latest Forge snapshot.
uv run dev/proof-scripts/market_order_summary_performance.py \
  --region-id 10000002 --limit-types 3 --repeats 1

# Complete comparison: all types, three runs for each of the three methods.
uv run dev/proof-scripts/market_order_summary_performance.py \
  --region-id 10000002 > dev/tmp/order-summary-timing.json
```

The default database is `dev/app-dir/argus-dynamic-db.sqlite`, opened read-only.
Use `--database PATH` to select another database, and `--response-metadata-id ID`
instead of `--region-id` to pin a snapshot. Without either selector, the newest
stored snapshot in any region is selected. No settings, ESI clients, schema
initialization, saved summaries, or database/index writes are involved. `--help`
does not open the database.

The dynamic schema now creates `market_orders_response_type_order` on
`(response_metadata_id, type_id, order_id)`. Normal application database
initialization installs it idempotently on existing databases as well as new ones.
The read-only proof does **not** initialize the schema: make sure the index is
installed before comparing indexed performance. The report lists existing indexes
and includes a query plan so this is verifiable.

`--system-id` or `--location-id` restricts the workload to types with orders in
that scope. All methods use the same `--filter-factor` (default 100), types,
snapshot, and buy/sell sides. Exact summary equality is checked after every round,
outside the timers; missing sides and zero-volume books must match too. Invalid
inputs, empty workloads, missing snapshots, or differing results fail nonzero.

The tuple calculator requires the source `MarketOrdersResponse` as its `response`
keyword argument, plus the same scope passed to the filtered reader. This preserves
snapshot timestamps even for an empty tuple, and rejects orders from another
snapshot, region, or scope. It includes only types present in the filtered tuple;
the original whole-dataset calculator still preserves all its input type keys,
even when a scope leaves some with no summaries. The proof compares the same
scoped type keys in all three paths.

The JSON report on stdout contains all run timings, median stages, the on-demand
total-time ratio (greater than 1 means slower), extra elapsed seconds, average
seconds per on-demand call, workload counts, existing index names, and a
representative on-demand query plan. Progress goes to stderr.

- **Dataset setup:** load and convert the entire regional snapshot, then retain
  the selected types. **Dataset calculation:** calculate both sides in memory.
- **On-demand setup:** discover, sort, and optionally limit scoped type IDs.
  **On-demand calculation:** query, convert, and summarize both sides per type.
- **Filtered dataset setup:** read source metadata and all orders in the scope
  once, retaining selected types. **Filtered dataset calculation:** group the flat
  tuple by type and calculate both sides, without constructing price-sorted
  `BuySellOrders` containers first.
- **Total:** setup plus calculation. Connection opening, snapshot selection,
  initial workload validation/discovery, equality checks, and JSON output are
  excluded. Result dictionaries are retained in all paths. The dataset path
  always loads the entire regional snapshot, even for a system/location scope.
  On-demand progress is printed every 250 completed types; its small output
  overhead is included in calculation time.

`--limit-types N` calculates only the first N sorted scoped types in **both**
methods, while the dataset path still pays the full snapshot load cost and the
filtered-dataset path still loads every order in the scope.
`sampled: true` explicitly identifies an incomplete comparison. This is useful
for estimating runtime, but its ratio is **not** the full-workload penalty or a
guaranteed break-even point; type/order distributions differ. Omit the limit for
the actual all-types comparison.

**Expect long runs on an unindexed database.** Each per-side query may scan the
entire `market_orders` table, including other stored snapshots; a regional
comparison can require tens of thousands of scans. The original implementation
made two such scans per type; the paired implementation now makes one.
The proof does not silently
add indexes, copy/filter the database, or optimize away production queries.
It uses one read transaction for a consistent snapshot; run when ingestion is
idle, since this can delay writers depending on SQLite's journal mode.

Execution order alternates between repetitions to reduce order bias. There is
no explicit warmup or cache clearing: preliminary discovery/counts warm some
pages, and SQLite/OS caches are shared across measurements. These are repeated
elapsed-time measurements, not cold-disk or memory benchmarks. Per-function INFO
timing logging is not configured, avoiding thousands of log writes. Run different
benchmark commands sequentially on the same otherwise-idle machine.

## Market history performance comparison

For a **fetch-only** measurement of 500 direct
`pfmsoft.eve_argus.esi.fetch.market_history` calls:

```bash
uv run dev/proof-scripts/market-history-performance/fetch_only.py
```

This selects 500 distinct published market types in The Forge (10000002), schedules
all 500 calls concurrently, and lets the ESI client enforce its rate limits.
Unlike the batch/worker update proofs, it does not validate Argus response models
or write the market-history database. Timing excludes static selection, schema
acquisition, and client startup/cleanup, but includes ESI client caching, retries,
rate-limit waits, and response handling. Completed calls/minute is not a count of
actual HTTP attempts.

It explicitly reads `dev/market-history-perf-fetch/eve-argus.env.dev`, selecting
its own fresh `app-dir`. The same warm-directory and environment-override guards
described below apply. Use `--env-file` to select another benchmark env file or
`--static-db` to pin the static build. Results and selected IDs are saved as
`fetch-only-result.json` and `type-ids.json` in the isolated app directory.
Failures are counted and logged in `logs/fetch-only.log`; all calls are awaited
and any failures produce a nonzero exit status. No live calls run with `--help`.

Two live benchmarks compare production batch scheduling with a proof-only fixed
worker pool. No worker changes are made to the application source.

```bash
uv run dev/proof-scripts/market-history-performance/batch.py
uv run dev/proof-scripts/market-history-performance/worker.py
```

Each selects the first **2,000 sorted published market type IDs** from the same
latest Argus static build under `dev/app-dir/static-db-store` and updates history
in **The Forge (10000002)**. Use the same `--static-db /path/to/build.sqlite`
for both scripts to pin the source build. Selection fails if fewer types exist.
Both validate and write responses to isolated history databases, so these compare
the entire update pipeline, not only HTTP latency.

Each script explicitly reads its own environment file (not the root env file):

- Batch: `dev/market-history-perf-batch/eve-argus.env.dev`
- Worker: `dev/market-history-perf-worker/eve-argus.env.dev`

The files select separate `app-dir` subdirectories for **all** application state,
including ESI Link/API Request caches, logs, schema caches, and history databases.
An exported `PFMSOFT_EVE_ARGUS_APPLICATION_DIRECTORY` is rejected rather than
silently overriding isolation. Application directories must be fresh; reruns
refuse a nonempty directory to avoid cache hits or expiry skips distorting results.
For another run, change the directory in each env file to a new sibling such as
`app-dir-2`. Do not point either file at your normal development application data.
The benchmark does not delete caches or databases.

`--count` defaults to 2000. `--concurrency` defaults to the current production
batch-size constant (currently 200), used as the batch size or fixed worker count
respectively. For example, pass `--concurrency 100` to **both** commands for a
100-way comparison. The worker immediately takes another type when one finishes
instead of waiting for every update in a batch. Both preserve the failure limit
of 20 and await cancelled work before closing resources.

Fresh settings use the same default client rate limit for both scripts, printed
at startup; they do not inherit the normal app's TOML rate override. Server-side
limits still apply, and local cache isolation does not eliminate upstream caches
or network variability. Run sequentially, not simultaneously.

Timing excludes static selection, schema acquisition, database creation, and client
startup. It includes fetching, client cache handling, validation, history writes,
and commits. A separate setup-and-run timer includes schema/client/database setup.
Each application directory receives `type-ids.json`, `benchmark-result.json`, and
`logs/benchmark.log`. Results include inputs, concurrency, rate settings, elapsed
seconds, completed pairs/minute, and outcome counts. This is **pair throughput**,
not an instrumented count of HTTP attempts/retries. A fresh successful run should
show 2000 updated, zero skipped/failed/cancelled/unstarted. Incomplete or skipped
runs exit nonzero and must not be treated as complete timing comparisons.

These scripts make real public ESI requests. Offline tests use mocked clients;
running `--help` does not create application state or contact ESI.

## Refactored ESI proofs

[`esi-data-new/`](esi-data-new/) exercises all eight fetch functions in
[`pfmsoft.eve_argus.esi.fetch`](../../src/pfmsoft/eve_argus/esi/fetch.py) directly,
then calls their matching validators. The original [`esi-data/`](esi-data/) scripts
remain unchanged. Market group fetching and blueprint reports are not part of the
new fetch package.

Run an individual proof or the sequential suite from the project root:

```bash
uv run dev/proof-scripts/esi-data-new/region-market-history.py
bash dev/proof-scripts/esi-data-new/run-all.sh
```

The eight scripts cover market history (types 34, 35, and 36 in The Forge),
system cost indices, regional orders (The Forge), market prices, universe type IDs,
universe names (34, 35, 36, and 10000002), corporation industry jobs, and corporation
blueprints. They use the configured ESI schema and client without opening the
application's unrelated databases. Regional orders and universe type IDs may
download many pages.

Authenticated proofs require the existing `dev/secrets/auth.json` identity
references (`character_id`, `corporation_id`, and `cred_id`, a UUID string), plus
credentials/tokens configured in the EVE Link auth manager. The character must
have the endpoint's required corporation roles and scopes. Missing or invalid auth
data is an error, not a successful skip; identity references are not printed.

Raw endpoint data is saved before validation under
[`proof-output/esi-data-new/`](proof-output/esi-data-new/) as `*-raw.json`.
Successful validation produces a separate `*-validated.json` containing the new
model, including request identity and response timestamps. Names save one raw file
per batch. Logs are isolated under [`logging/esi-data-new/`](logging/esi-data-new/);
each successful script prints record counts and total elapsed time. Output files
are overwritten on subsequent runs; after a failed run, older validated output
may still exist, so use the exit status rather than file presence to judge success.
Corporation output may contain private corporation data; keep outputs and auth
files local.

These are live diagnostic scripts, not offline tests. Fetch failures and validation
errors propagate with a nonzero exit status. The suite continues after individual
failures and summarizes them at the end.

## Station-trades report proof

The initial station-trades proof reads the latest stored regional order snapshot
for each configured market hub, scopes books to each hub's primary station, and
adds regional history context from a common ten-calendar-day window. It does not
fetch or refresh application data. All three input databases are opened
read-only; a missing history database is reported as missing history.

```bash
uv run dev/proof-scripts/station-trades/station_trades.py \
  --to dev/proof-scripts/proof-output/station-trades
```

Use `--orders-database`, `--history-database`, or `--static-database` to select
other local SQLite files. Existing output is protected unless `--overwrite` is
passed. The script writes per-hub Markdown, CSV, and JSON files only after all
reports have been collected and rendered. A filesystem failure during writing
can still leave a partial output set.

The default static database is build `3607705` at
`dev/app-dir/static-db-store/build_3607705_2026-10-12T11_08_38Z_sqlite`.
For static types, the proof reads only `type_id`, `market_group_id`, `name`, and
`published`; market-group paths use the existing static reader.

The prototype uses the provided rule that prices have four significant figures,
with a `0.01 ISK` minimum price step. It proposes the next legal tick above the
current best station buy and below the current best station sell. This remains
provisional until verified in game, especially at tick boundaries. It
calculates fees at the configured proof constants (currently 0%), daily
estimates from 1% of regional average daily volume, and station-local ranks for
positive estimated daily profit. Missing history leaves daily estimates
unknown; zero history volume yields zero daily units and is not ranked. Regional
volume is not station-specific volume or a fill forecast, and buy-order
competition is station-anchored only.

The assumed step at price `P` is `max(0.01, 10^(floor(log10(P)) - 3))`.
At a power-of-ten boundary, the lower-price target uses the tick from the price
band immediately below the boundary: for example, the step below `1,000,000`
is `100`, producing `999,900`; the step above `999,900` produces `1,000,000`.
Markdown ranks the top 100 opportunities; CSV and JSON retain all candidates.
The Markdown ranking includes station best prices, order/depth context, history
coverage, price deviations from the regional history average, and per-unit and
daily fee details. JSON and CSV keep per-order IDs, range, minimum volume, price,
and remaining quantity for the station book.

Offline synthetic checks:

```bash
uv run pytest dev/proof-scripts/station-trades/test_station_trades.py
```
