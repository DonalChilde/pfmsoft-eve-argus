# proof-scripts

This directory contains scripts that prove the operation of various components of eve-argus.

The python scripts are expected to be run with `uv run` from the project root directory, so that the dev env settings are used.

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
