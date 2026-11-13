"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "../market-groups.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function browser() {
  const elements = new Map();
  class BrowserURL extends URL {}
  BrowserURL.createObjectURL = () => "blob:test";
  BrowserURL.revokeObjectURL = () => {};
  const document = {
    body: { append() {} },
    createElement() {
      return {
        click() { document.downloadName = this.download; },
        remove() {},
      };
    },
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, {
          value: id === "language" ? "en" : "",
          addEventListener(type, handler) { this[type] = handler; },
        });
      }
      return elements.get(id);
    },
  };
  const context = vm.createContext({
    document, URL: BrowserURL, Date, Blob, AbortController, setTimeout: (callback) => callback(),
  });
  vm.runInContext(script, context);
  return context;
}

function evaluate(context, expression) {
  return vm.runInContext(expression, context);
}

function schemaFixture() {
  return {
    openapi: "3.1.0",
    info: { version: "2026-08-18" },
    components: {},
    paths: {
      "/markets/groups": { get: { operationId: "GetMarketsGroups" } },
      "/markets/groups/{market_group_id}": {
        get: { operationId: "GetMarketsGroupsMarketGroupId" },
      },
    },
  };
}

test("raw and dereferenced schemas identify both market operations and compatibility date", () => {
  const context = browser();
  context.input = schemaFixture();
  evaluate(context, "globalThis.raw = parseMarketSchema(input, 'file')");
  assert.equal(evaluate(context, "raw.compatibilityDate"), "2026-08-18");
  assert.equal(evaluate(context, "raw.listPath"), "/markets/groups");
  assert.equal(evaluate(context, "raw.detailPath"), "/markets/groups/{market_group_id}");
  evaluate(context, `globalThis.wrapped = parseMarketSchema({
    dereferenced_schema: input, timestamp: "2026-08-18T12:00:00Z"
  }, "file")`);
  assert.equal(evaluate(context, "wrapped.compatibilityDate"), "2026-08-18");
  assert.equal(evaluate(context, "wrapped.timestamp"), "2026-08-18T12:00:00Z");
  assert.throws(() => evaluate(context, `parseMarketSchema({
    ...input, info: {version: "invalid"}
  }, "file")`), /compatibility date/i);
  assert.throws(() => evaluate(context, `parseMarketSchema({
    ...input, paths: {"/markets/groups": input.paths["/markets/groups"]}
  }, "file")`), /GetMarketsGroupsMarketGroupId/);
  assert.throws(() => evaluate(context, `parseMarketSchema({
    ...input, paths: {
      "//example.test/path": {get: {operationId: "GetMarketsGroups"}},
      "/markets/groups/{market_group_id}": input.paths["/markets/groups/{market_group_id}"]
    }
  }, "file")`), /paths are invalid/);
  evaluate(context, `input.components.pathItems = {list: input.paths["/markets/groups"]};
    input.paths["/markets/groups"] = {$ref: "#/components/pathItems/list"};`);
  assert.equal(evaluate(context, "parseMarketSchema(input, 'file').listPath"), "/markets/groups");
});

test("market group records include parent paths but omit fields not supplied by ESI", () => {
  const context = browser();
  context.groups = [
    { market_group_id: 9, name: "Child", description: "C", parent_group_id: 4, types: [99, 50] },
    { market_group_id: 4, name: "Root", description: "R", types: [] },
  ];
  const result = JSON.parse(evaluate(context, `JSON.stringify(buildDataset({
    groups, receivedAt: "2026-08-18T12:00:01.000Z",
    expiresAt: "2026-08-19T11:05:00.000Z"
  }))`));
  assert.deepEqual(result, {
    received_at: "2026-08-18T12:00:01.000Z",
    expires_at: "2026-08-19T11:05:00.000Z",
    market_groups: {
      4: { market_group_id: 4, description: "R", int_path: [4], name: "Root",
        parent_group_id: null, str_path: ["Root"], types: [] },
      9: { market_group_id: 9, description: "C", int_path: [4, 9], name: "Child",
        parent_group_id: 4, str_path: ["Root", "Child"], types: [50, 99] },
    },
  });
});

test("invalid market groups, missing parents, and cycles fail explicitly", () => {
  const context = browser();
  assert.throws(() => evaluate(context, `buildDataset({
    groups: [{market_group_id: 1, name: "A", description: "", types: [], parent_group_id: 2}],
    receivedAt: "now", expiresAt: null
  })`), /parent/i);
  assert.throws(() => evaluate(context, `buildDataset({
    groups: [
      {market_group_id: 1, name: "A", description: "", types: [], parent_group_id: 2},
      {market_group_id: 2, name: "B", description: "", types: [], parent_group_id: 1}
    ], receivedAt: "now", expiresAt: null
  })`), /cycle/i);
  assert.throws(() => evaluate(context, `buildDataset({
    groups: [{market_group_id: 1, name: "A", description: "", types: [0]}],
    receivedAt: "now", expiresAt: null
  })`), /type/i);
});

test("downloads details concurrently and uses list response expiry and schema date", async () => {
  const context = browser();
  context.input = schemaFixture();
  let tick = 0;
  context.Date = class extends Date {
    constructor(...args) {
      super(...(args.length ? args : [Date.UTC(2026, 7, 18, 12, 0, tick++)]));
    }
  };
  const calls = [];
  let running = 0;
  let maximum = 0;
  context.fetch = async (url, options) => {
    calls.push({ path: new URL(url).pathname, date: options.headers["X-Compatibility-Date"] });
    const detailId = Number(new URL(url).pathname.split("/").at(-1));
    if (!detailId) {
      return {
        ok: true, headers: { get: (name) => name === "Expires" ? "Wed, 19 Aug 2026 11:05:00 GMT" : null },
        json: async () => Array.from({ length: 15 }, (_, index) => index + 1),
      };
    }
    running++;
    maximum = Math.max(maximum, running);
    await new Promise((resolve) => setTimeout(resolve, 5));
    running--;
    return {
      ok: true, headers: { get: () => "Thu, 20 Aug 2026 11:05:00 GMT" },
      json: async () => ({ market_group_id: detailId, name: `Group ${detailId}`, description: "", types: [] }),
    };
  };
  const result = await evaluate(context, "fetchMarketGroups(parseMarketSchema(input, 'file'), () => {}, 'en')");
  assert.equal(Object.keys(result.market_groups).length, 15);
  assert.equal(result.expires_at, "2026-08-19T11:05:00.000Z");
  assert.equal(result.received_at, "2026-08-18T12:00:15.000Z");
  assert.equal(maximum, 10);
  assert.ok(calls.every((call) => call.date === "2026-08-18"));
  assert.equal(calls.length, 16);
});

test("selected language is sent on every request and locked during a fetch", async () => {
  const context = browser();
  context.input = schemaFixture();
  evaluate(context, "state.schema = parseMarketSchema(input, 'file')");
  const language = context.document.getElementById("language");
  const headers = [];
  let release;
  context.fetch = async (url, options) => {
    headers.push(options.headers["Accept-Language"]);
    const id = Number(new URL(url).pathname.split("/").at(-1));
    if (!id) {
      await new Promise((resolve) => { release = resolve; });
      return { ok: true, headers: { get: () => null }, json: async () => [1] };
    }
    return { ok: true, headers: { get: () => null },
      json: async () => ({ market_group_id: 1, name: headers.at(-1), description: "", types: [] }) };
  };
  for (const selected of ["en", "de"]) {
    language.value = selected;
    const request = context.document.getElementById("fetch-groups").click();
    assert.equal(language.disabled, true);
    release();
    await request;
    assert.equal(language.disabled, false);
    assert.equal(evaluate(context, "state.dataset.market_groups[1].str_path[0]"), selected);
  }
  assert.deepEqual(headers, ["en", "en", "de", "de"]);
  language.value = "ja";
  context.document.getElementById("save-groups").click();
  assert.match(context.document.downloadName, /^market-groups-de-\d{4}-\d{2}-\d{2}\.json$/);
});

test("missing expiry is unknown and a detail failure never yields a dataset", async () => {
  const context = browser();
  context.input = schemaFixture();
  context.fetch = async (url) => {
    const pathname = new URL(url).pathname;
    if (pathname === "/markets/groups") {
      return { ok: true, headers: { get: () => null }, json: async () => [1] };
    }
    return { ok: true, headers: { get: () => null },
      json: async () => ({ market_group_id: 1, name: "One", description: "", types: [] }) };
  };
  const result = await evaluate(context, "fetchMarketGroups(parseMarketSchema(input, 'file'), () => {}, 'en')");
  assert.equal(result.expires_at, null);
  context.fetch = async (url) => {
    if (new URL(url).pathname === "/markets/groups") {
      return { ok: true, headers: { get: () => null }, json: async () => [1] };
    }
    return { ok: false, status: 429, statusText: "Too Many Requests", headers: { get: () => null } };
  };
  await assert.rejects(
    evaluate(context, "fetchMarketGroups(parseMarketSchema(input, 'file'), () => {}, 'en')"),
    /429/,
  );
});

test("the first detail error stops workers and remains visible after aborts", async () => {
  const context = browser();
  context.input = schemaFixture();
  let detailCalls = 0;
  context.fetch = async (url, options) => {
    const id = Number(new URL(url).pathname.split("/").at(-1));
    if (!id) {
      return { ok: true, headers: { get: () => null }, json: async () => Array.from({ length: 11 }, (_, index) => index + 1) };
    }
    detailCalls++;
    if (id === 1) {
      await new Promise((resolve) => setTimeout(resolve, 5));
      return { ok: false, status: 429, statusText: "Too Many Requests", headers: { get: () => null } };
    }
    return new Promise((resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new Error("Request aborted")));
    });
  };
  await assert.rejects(
    evaluate(context, "fetchMarketGroups(parseMarketSchema(input, 'file'), () => {}, 'en')"),
    /Market group 1: HTTP 429/,
  );
  assert.equal(detailCalls, 10);
});

test("a failed run clears an old dataset and keeps export disabled", async () => {
  const context = browser();
  context.input = schemaFixture();
  evaluate(context, "state.schema = parseMarketSchema(input, 'file'); state.dataset = {old: true}");
  context.fetch = async () => ({
    ok: false, status: 503, statusText: "Unavailable", headers: { get: () => null },
  });
  await context.document.getElementById("fetch-groups").click();
  assert.equal(evaluate(context, "state.dataset"), null);
  assert.equal(context.document.getElementById("save-groups").disabled, true);
  assert.match(context.document.getElementById("groups-status").textContent, /503/);
});

test("latest schema fetch selects the newest date and enables market downloads", async () => {
  const context = browser();
  const calls = [];
  context.fetch = async (url) => {
    const parsed = new URL(url);
    calls.push(parsed);
    return {
      ok: true, headers: { get: () => null },
      json: async () => parsed.pathname.endsWith("compatibility-dates")
        ? { compatibility_dates: ["2025-01-01", "2026-08-18", "2026-01-01"] }
        : schemaFixture(),
    };
  };
  await context.document.getElementById("fetch-schema").click();
  assert.equal(calls[1].searchParams.get("compatibility_date"), "2026-08-18");
  assert.equal(context.document.getElementById("fetch-groups").disabled, false);
  assert.match(context.document.getElementById("schema-status").textContent, /2026-08-18/);
});

test("duplicate IDs and invalid list expiry fail before detail requests", async () => {
  const context = browser();
  context.input = schemaFixture();
  let calls = 0;
  context.fetch = async () => {
    calls++;
    return { ok: true, headers: { get: () => null }, json: async () => [1, 1] };
  };
  await assert.rejects(evaluate(context, "fetchMarketGroups(parseMarketSchema(input, 'file'), () => {}, 'en')"), /duplicate/);
  assert.equal(calls, 1);
  context.fetch = async () => ({
    ok: true, headers: { get: () => "not a date" }, json: async () => [1],
  });
  await assert.rejects(evaluate(context, "fetchMarketGroups(parseMarketSchema(input, 'file'), () => {}, 'en')"), /invalid Expires/);
});

test("an empty ID list yields an empty dataset without detail requests", async () => {
  const context = browser();
  context.input = schemaFixture();
  let calls = 0;
  context.fetch = async () => {
    calls++;
    return { ok: true, headers: { get: () => null }, json: async () => [] };
  };
  const result = await evaluate(context, "fetchMarketGroups(parseMarketSchema(input, 'file'), () => {}, 'en')");
  assert.equal(calls, 1);
  assert.equal(Object.keys(result.market_groups).length, 0);
  assert.equal(result.expires_at, null);
});

test("invalid schema file leaves the previous schema and dataset usable", async () => {
  const context = browser();
  context.input = schemaFixture();
  evaluate(context, "state.schema = parseMarketSchema(input, 'file'); state.dataset = {old: true}");
  const target = { files: [{ name: "broken.json", text: async () => "{" }], value: "broken.json" };
  await context.document.getElementById("schema-file").change({ target });
  assert.equal(evaluate(context, "state.dataset.old"), true);
  assert.equal(evaluate(context, "state.schema.compatibilityDate"), "2026-08-18");
  assert.equal(context.document.getElementById("save-groups").disabled, false);
  assert.match(context.document.getElementById("schema-status").textContent, /Could not open/);
});

test("saved filename uses the current UTC date rather than the dataset receipt date", () => {
  const context = browser();
  let now = "2026-11-14T00:01:00.000Z";
  context.Date = class extends Date {
    constructor(...args) {
      super(...(args.length ? args : [now]));
    }
  };
  evaluate(context, `state.dataset = { received_at: "2026-11-13T23:59:00Z", market_groups: {} }; state.datasetLanguage = "en"`);
  context.document.getElementById("save-groups").click();
  assert.equal(context.document.downloadName, "market-groups-en-2026-11-14.json");
  now = "2026-11-15T00:01:00.000Z";
  context.document.getElementById("save-groups").click();
  assert.equal(context.document.downloadName, "market-groups-en-2026-11-15.json");
});
