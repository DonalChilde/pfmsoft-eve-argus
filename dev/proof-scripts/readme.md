# proof-scripts

This directory contains scripts that prove the operation of various components of eve-argus.

The python scripts are expected to be run with `uv run` from the project root directory, so that the dev env settings are used.

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
