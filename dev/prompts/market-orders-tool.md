# Market Orders Tool

## Usage and snapshot limitation

Open [the market-orders tool](../tools/market-orders.html) directly in a modern
browser. Load or fetch a schema, optionally load a names file, choose a language,
and fetch the region list. Select a region and fetch its orders. Use the names
pane to retry missing name resolution or save the merged names. Select a scope
and calculate a price summary on demand.

On 2026-11-13, a live ESI request for page one of The Forge's orders returned
`Last-Modified`, `Expires`, and `X-Pages`. Its
`Access-Control-Expose-Headers` included `X-Pages` but not `Last-Modified`.
`Last-Modified` is not a CORS-safelisted response header, so a browser opening
the HTML directly cannot read it, even though ESI sends it. `Expires` is
CORS-safelisted. The tool instead requires every page's `Expires` to match page
one. This is a practical approximation, **not proof** that the pages represent
the same snapshot. It rejects missing, invalid or mismatched expiry headers.

## Requirements

### Schema and region selection

- Require an ESI schema before fetching; derive endpoint paths from its
  operation IDs. Import raw OpenAPI or the dereferenced, timestamped format, or
  fetch the latest schema as in [the market-groups tool](../tools/market-groups.html).
- Fetch region IDs and display region names and IDs for selection.
- Provide language selection as in the market-groups tool, defaulting to `en`.

### Download and display

- Fetch all buy and sell orders for one region. Show progress and use bounded
  concurrency for pages.
- Require the relevant pagination and metadata headers. Each page's
  `Expires` must match page one's; missing headers, a mismatch, or a
  failed page invalidates the run. Do not export partial orders.
- Save JSON with `received_at` (the last completed orders response),
  `expires_at` (from page one), `region_id`, and `orders` (all pages combined).
- Display order counts by solar system and station using resolved names and IDs.
  Raw-order display is optional; if included, page the display because a region
  can contain approximately 450,000 orders.
- Use a file-safe version of the dataset's `expires_at` in the default orders
  filename, for example
  `market-orders-10000002-2026-08-19T11_05_00_000Z.json`. Follow the
  [existing filename-safe convention](../../src/pfmsoft/eve_argus/helpers/file_safe_string.py).

### Names

- Resolve region, solar-system, station and item-type IDs using
  `PostUniverseNames` from the loaded schema. Send the selected language and
  compatibility date. Deduplicate IDs and use batches of at most 950; the
  inspected schema permits up to 1,000 unique IDs per request.
- Optionally load a JSON names file and request only IDs not already present.
  Save a deduplicated JSON array of `{id, name, category}` records containing
  all loaded entries plus newly resolved names. Reject malformed or conflicting
  records without replacing the existing cache.
- Loaded names remain unchanged; the user is responsible for ensuring the file
  is in the desired language. Surface resolution failures and missing IDs
  explicitly rather than silently treating them as resolved.
- ESI currently rejects IDs above 2,147,483,647 despite the inspected schema
  describing them as int64. Skip and report those IDs, which may represent
  player structures, while resolving other IDs. A loaded names file can supply
  their names using the additional `structure` category. Other request failures
  remain visible, including the response diagnostic.

### Summaries

- Calculate, display and save a summary only when requested. The user selects
  region, one solar system, or one station/location and supplies a filter
  factor, defaulting to 100.
- Match [the current calculation](../../src/pfmsoft/eve_argus/dynamic/order_summary.py)
  and [summary models](../../src/pfmsoft/eve_argus/dynamic/models.py): preserve
  the buy/sell records and their scope, outlier filtering, 5% depth and tied
  prices, weighted averages, and rounding. Omit database-only metadata fields.
  Ensure browser numeric handling does not silently lose ID or price precision.
- Unlike the current dataset calculator, omit type records when both the buy
  and sell summaries are null.
- Use the source dataset's file-safe `expires_at` and selected scope in the
  default summary filename.

## Verification

- Add focused tests for schema imports and operations, language headers, page
  counts and ordering, missing or mismatched headers, page failures, metadata,
  and no partial order export.
- Test name-file validation, existing and unknown IDs, batch boundaries,
  merges, categories, and resolution failures.
- Compare summary results to existing Python calculation fixtures, including
  scoped results, empty sides, filter boundaries, tied prices, and rounding.
  Check output shapes and expiry-based filenames.
- Exercise the UI with mocked responses and check live headers and name
  resolution with a limited request. A limited live check cannot establish
  that every region or ID will work. Run the tests with
  `node --test dev/tools/tests/test_market_orders.js`.
