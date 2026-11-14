"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "../market-orders.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function browser() {
  const elements = new Map();
  const document = {
    body: { append() {} },
    createElement() { return { click() {}, remove() {} }; },
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, {
          value: id === "language" ? "en" : id === "filter-factor" ? "100" : "",
          addEventListener(type, handler) { this[type] = handler; },
          replaceChildren() {},
          append() {},
        });
      }
      return elements.get(id);
    },
  };
  class BrowserURL extends URL {}
  BrowserURL.createObjectURL = () => "blob:test";
  BrowserURL.revokeObjectURL = () => {};
  const context = vm.createContext({ document, URL: BrowserURL, Date, Blob, AbortController, setTimeout });
  vm.runInContext(script, context);
  return context;
}

function run(context, expression) {
  return vm.runInContext(expression, context);
}

function schemaFixture() {
  return {
    openapi: "3.1.0", info: { version: "2026-08-18" }, components: {},
    paths: {
      "/universe/regions": { get: { operationId: "GetUniverseRegions" } },
      "/universe/names": { post: { operationId: "PostUniverseNames" } },
      "/markets/{region_id}/orders": { get: { operationId: "GetMarketsRegionIdOrders" } },
    },
  };
}

function order(id, price, volume, buy, overrides = {}) {
  return {
    order_id: id, type_id: 34, location_id: 60003760, system_id: 30000142,
    price, volume_remain: volume, volume_total: volume, is_buy_order: buy,
    duration: 90, issued: "2026-08-18T12:00:00Z", min_volume: 1, range: "station",
    ...overrides,
  };
}

const expiry = "Wed, 19 Aug 2026 11:05:00 GMT";
function response(data, headers = {}) {
  return {
    ok: true, headers: { get: (name) => headers[name.toLowerCase()] ?? null },
    json: async () => data,
  };
}

test("schema import resolves required operations and rejects invalid paths", () => {
  const c = browser();
  c.input = schemaFixture();
  assert.equal(run(c, "parseSchema(input, 'file').ordersPath"), "/markets/{region_id}/orders");
  assert.equal(run(c, "parseSchema({dereferenced_schema: input, timestamp: null}, 'file').namesPath"), "/universe/names");
  run(c, "input.components.pathItems = { names: input.paths['/universe/names'] }; input.paths['/universe/names'] = {$ref: '#/components/pathItems/names'}");
  assert.equal(run(c, "parseSchema(input, 'file').namesPath"), "/universe/names");
  run(c, "input.paths['//bad'] = input.paths['/universe/names']; delete input.paths['/universe/names']");
  assert.throws(() => run(c, "parseSchema(input, 'file')"), /path.*invalid/i);
});

test("pages are combined in page order with page-one expiry and selected language", async () => {
  const c = browser();
  c.input = schemaFixture();
  const calls = [];
  c.fetch = async (url, options) => {
    const parsed = new URL(url);
    const page = Number(parsed.searchParams.get("page"));
    calls.push({ page, language: options.headers["Accept-Language"], date: options.headers["X-Compatibility-Date"] });
    if (page === 2) await new Promise((resolve) => setTimeout(resolve, 5));
    return response([order(page, 100, 1, true)], { expires: expiry, "x-pages": "3" });
  };
  const result = await run(c, "fetchOrders(parseSchema(input, 'file'), 10000002, 'de', () => {})");
  assert.deepEqual(Array.from(result.orders, (item) => item.order_id), [1, 2, 3]);
  assert.equal(result.expires_at, "2026-08-19T11:05:00.000Z");
  assert.equal(result.region_id, 10000002);
  assert.ok(calls.every((call) => call.language === "de" && call.date === "2026-08-18"));
});

test("missing or inconsistent expiry and pagination headers reject the entire run", async () => {
  const c = browser();
  c.input = schemaFixture();
  for (const headers of [{ "x-pages": "1" }, { expires: expiry }, { expires: "invalid", "x-pages": "1" }]) {
    c.fetch = async () => response([], headers);
    await assert.rejects(run(c, "fetchOrders(parseSchema(input, 'file'), 10000002, 'en', () => {})"), /Expires|X-Pages/i);
  }
  c.fetch = async (url) => {
    const page = Number(new URL(url).searchParams.get("page"));
    return response([order(page, 100, 1, true)], { expires: page === 1 ? expiry : "Wed, 19 Aug 2026 11:10:00 GMT", "x-pages": "2" });
  };
  await assert.rejects(run(c, "fetchOrders(parseSchema(input, 'file'), 10000002, 'en', () => {})"), /Expires.*match/i);
});

test("page downloads are bounded and HTTP errors abort the remaining workers", async () => {
  const c = browser();
  c.input = schemaFixture();
  let running = 0;
  let maximum = 0;
  c.fetch = async (url) => {
    const page = Number(new URL(url).searchParams.get("page"));
    if (page !== 1) {
      running++;
      maximum = Math.max(maximum, running);
      await new Promise((resolve) => setTimeout(resolve, 5));
      running--;
    }
    return response([order(page, 100, 1, true)], { expires: expiry, "x-pages": "15" });
  };
  await run(c, "fetchOrders(parseSchema(input, 'file'), 10000002, 'en', () => {})");
  assert.equal(maximum, 10);
  let calls = 0;
  c.fetch = async (url, options) => {
    const page = Number(new URL(url).searchParams.get("page"));
    if (page === 1) return response([], { expires: expiry, "x-pages": "15" });
    calls++;
    if (page === 2) {
      await new Promise((resolve) => setTimeout(resolve, 5));
      return { ok: false, status: 429, statusText: "Too Many Requests", headers: { get: () => null }, text: async () => "" };
    }
    return new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new Error("Request aborted")));
    });
  };
  await assert.rejects(run(c, "fetchOrders(parseSchema(input, 'file'), 10000002, 'en', () => {})"), /Page 2: HTTP 429/);
  assert.equal(calls, 10);
});

test("orders reject duplicate IDs and unsafe integers", async () => {
  const c = browser();
  c.input = schemaFixture();
  for (const orders of [[order(1, 1, 1, true), order(1, 2, 1, false)], [order(9007199254740992, 1, 1, true)]]) {
    c.fetch = async () => response(orders, { expires: expiry, "x-pages": "1" });
    await assert.rejects(run(c, "fetchOrders(parseSchema(input, 'file'), 10000002, 'en', () => {})"), /Duplicate|safe range/i);
  }
});

test("a failed refresh removes the previous orders and disables their export", async () => {
  const c = browser();
  c.input = schemaFixture();
  run(c, "state.schema = parseSchema(input, 'file'); state.regions = [10000002]; state.dataset = {old: true}");
  c.document.getElementById("region").value = "10000002";
  c.fetch = async () => response([], { "x-pages": "1" });
  await c.document.getElementById("fetch-orders").click();
  assert.equal(run(c, "state.dataset"), null);
  assert.equal(c.document.getElementById("save-orders").disabled, true);
  assert.match(c.document.getElementById("orders-status").textContent, /Expires/i);
});

test("names imports reject conflicts and resolve only unknown IDs in batches", async () => {
  const c = browser();
  c.input = schemaFixture();
  c.names = [{ id: 1, name: "Existing", category: "inventory_type" }];
  assert.throws(() => run(c, "parseNames([{id: 1, name: 'A', category: 'station'}, {id: 1, name: 'B', category: 'station'}])"), /conflict/i);
  const batches = [];
  c.fetch = async (url, options) => {
    const ids = JSON.parse(options.body);
    batches.push(ids);
    assert.equal(options.headers["Accept-Language"], "fr");
    return response(ids.map((id) => ({ id, name: `Name ${id}`, category: "inventory_type" })));
  };
  const result = await run(c, "resolveNames(parseSchema(input, 'file'), parseNames(names), Array.from({length: 952}, (_, i) => i + 1), 'fr', () => {})");
  assert.deepEqual(batches.map((batch) => batch.length), [950, 1]);
  assert.ok(batches.every((batch) => !batch.includes(1)));
  assert.equal(result.names.get(1).name, "Existing");
  assert.equal(result.names.size, 952);
  assert.equal(result.unsupportedIds.length, 0);
  c.fetch = async () => response([]);
  await assert.rejects(run(c, "resolveNames(parseSchema(input, 'file'), parseNames(names), [1, 2], 'fr', () => {})"), /missing/i);
});

test("resolve known large IDs from cache, skip unsupported IDs and report them", async () => {
  const c = browser();
  c.input = schemaFixture();
  c.names = [{ id: 1050000000000, name: "Loaded structure", category: "structure" }];
  const batches = [];
  c.fetch = async (url, options) => {
    const ids = JSON.parse(options.body);
    batches.push(ids);
    return response(ids.map((id) => ({ id, name: `Name ${id}`, category: "station" })));
  };
  const result = await run(c, "resolveNames(parseSchema(input, 'file'), parseNames(names), [60003760, 1050000000000, 1050650201396], 'en', () => {})");
  assert.deepEqual(batches, [[60003760]]);
  assert.equal(result.names.get(1050000000000).name, "Loaded structure");
  assert.equal(result.names.get(1050000000000).category, "structure");
  assert.equal(result.names.get(60003760).name, "Name 60003760");
  assert.deepEqual(Array.from(result.unsupportedIds), [1050650201396]);
});

test("order-name resolution shows unsupported IDs while retaining other names", async () => {
  const c = browser();
  c.input = schemaFixture();
  c.dataset = {
    region_id: 10000002, received_at: "2026-08-18T12:00:00Z",
    expires_at: "2026-08-19T11:05:00.000Z",
    orders: [order(1, 100, 1, true, { location_id: 1050650201396 })],
  };
  run(c, "state.schema = parseSchema(input, 'file'); state.dataset = dataset");
  c.fetch = async (url, options) => response(JSON.parse(options.body).map((id) => ({
    id, name: `Name ${id}`, category: "station",
  })));
  await run(c, "resolveOrderNames()");
  assert.equal(run(c, "state.names.size"), 3);
  assert.match(c.document.getElementById("names-status").textContent, /32-bit.*1050650201396/);
  assert.match(c.document.getElementById("order-counts").textContent, /Unresolved \(1050650201396\)/);
});

test("name endpoint errors include the server's diagnostic", async () => {
  const c = browser();
  c.input = schemaFixture();
  c.fetch = async () => ({
    ok: false, status: 400, statusText: "Bad Request", headers: { get: () => null },
    text: async () => '{"error":"invalid id"}',
  });
  await assert.rejects(run(c, "resolveNames(parseSchema(input, 'file'), new Map(), [34], 'en', () => {})"), /HTTP 400.*invalid id/);
});

test("conflicting names file does not replace the existing cache", async () => {
  const c = browser();
  run(c, "state.names = parseNames([{id: 1, name: 'Existing', category: 'station'}])");
  const target = { files: [{ name: "conflict.json", text: async () => JSON.stringify([{ id: 1, name: "Other", category: "station" }]) }], value: "conflict.json" };
  await c.document.getElementById("names-file").change({ target });
  assert.equal(run(c, "state.names.get(1).name"), "Existing");
  assert.match(c.document.getElementById("names-status").textContent, /conflict/i);
});

test("summary matches filtering, scope, tie handling and decimal rounding", () => {
  const c = browser();
  c.dataset = {
    region_id: 10000002, received_at: "2026-08-18T12:00:00Z",
    expires_at: "2026-08-19T11:05:00.000Z",
    orders: [
      order(1, 100, 10, true), order(2, 90, 20, true), order(3, 5, 30, true),
      order(4, 110, 10, false), order(5, 120, 20, false), order(6, 1200, 30, false),
      order(7, 1000, 5, true, { system_id: 30000143, location_id: 60003761 }),
      order(8, 1, 1, false, { type_id: 35, system_id: 30000143, location_id: 60003761 }),
    ],
  };
  const result = JSON.parse(run(c, "JSON.stringify(calculateSummaries(dataset, {systemId: 30000142, locationId: null, filterFactor: '10'}))"));
  const buy = result.records["34"].buy_summary;
  assert.deepEqual([buy.five_price, buy.five_orders, buy.five_items, buy.total_items, buy.total_orders, buy.average, buy.filtered_items, buy.filtered_orders], [100, 1, 10, 30, 2, 93.33, 30, 1]);
  assert.equal(result.records["34"].sell_summary.average, 116.67);
  assert.equal(Object.hasOwn(result.records, "35"), false);
  assert.equal(result.system_id, 30000142);
  assert.throws(() => run(c, "calculateSummaries(dataset, {systemId: null, locationId: null, filterFactor: '1'})"), /greater than 1/i);
});

test("summary excludes types with zero volume on both sides", () => {
  const c = browser();
  c.dataset = {
    region_id: 10000002, received_at: "2026-08-18T12:00:00Z",
    expires_at: "2026-08-19T11:05:00.000Z",
    orders: [order(1, 100, 0, true), order(2, 100, 0, false)],
  };
  const result = JSON.parse(run(c, "JSON.stringify(calculateSummaries(dataset, {systemId: null, locationId: null, filterFactor: '100'}))"));
  assert.deepEqual(result.records, {});
});

test("summary includes tied depth prices and rounds weighted averages half up", () => {
  const c = browser();
  c.dataset = {
    region_id: 10000002, received_at: "2026-08-18T12:00:00Z",
    expires_at: "2026-08-19T11:05:00.000Z",
    orders: [order(1, 100, 5, true), order(2, 100, 5, true), order(3, 99, 100, true),
      order(4, 1, 1, false, { type_id: 35 }), order(5, 1.01, 1, false, { type_id: 35 })],
  };
  const result = JSON.parse(run(c, "JSON.stringify(calculateSummaries(dataset, {systemId: null, locationId: 60003760, filterFactor: '100'}))"));
  const buy = result.records["34"].buy_summary;
  assert.deepEqual([buy.five_price, buy.five_orders, buy.five_items, buy.total_items], [100, 2, 10, 110]);
  assert.equal(result.records["35"].sell_summary.average, 1.01);
  assert.equal(result.location_id, 60003760);
});

test("summary prices use the same half-even input rounding as stored orders", () => {
  const c = browser();
  c.dataset = {
    region_id: 10000002, received_at: "2026-08-18T12:00:00Z",
    expires_at: "2026-08-19T11:05:00.000Z",
    orders: [order(1, 1.005, 1, true), order(2, 1.015, 1, true)],
  };
  const buy = JSON.parse(run(c, "JSON.stringify(calculateSummaries(dataset, {systemId: null, locationId: null, filterFactor: '100'}).records['34'].buy_summary)"));
  assert.deepEqual([buy.five_price, buy.lowest, buy.highest, buy.average], [1.02, 1, 1.02, 1.01]);
});

test("filenames use source expiry and identify summary scope", () => {
  const c = browser();
  assert.equal(run(c, "ordersFilename(10000002, '2026-08-19T11:05:00.000Z')"), "market-orders-10000002-2026-08-19T11_05_00_000Z.json");
  assert.equal(run(c, "summaryFilename({region_id:10000002, system_id:null, location_id:60003760, expires_at:'2026-08-19T11:05:00.000Z'})"), "order-summary-location-60003760-2026-08-19T11_05_00_000Z.json");
});
