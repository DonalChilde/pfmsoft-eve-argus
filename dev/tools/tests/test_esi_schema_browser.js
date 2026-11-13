"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const html = fs.readFileSync(
  path.join(__dirname, "../esi-schema.html"), "utf8",
);
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function browser() {
  const elements = new Map();
  function element() {
    return {
      children: [],
      addEventListener(type, handler) { this[type] = handler; },
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      scrollIntoView() {},
    };
  }
  const document = {
    createElement() { return element(); },
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, element());
      }
      return elements.get(id);
    },
  };
  const context = vm.createContext({ document, URL, Date });
  vm.runInContext(script, context);
  return context;
}

function evaluate(context, expression) {
  return vm.runInContext(expression, context);
}

test("raw and dereferenced schema formats preserve provenance", () => {
  const context = browser();
  evaluate(context, `globalThis.raw = {
    openapi: "3.1.0", info: {}, paths: {}, components: {}
  }`);
  assert.equal(evaluate(context, 'parseSchema(raw, "file").timestamp'), null);
  assert.equal(evaluate(context, 'parseSchema(raw, "file").raw === raw'), true);
  assert.equal(evaluate(context, `parseSchema({
    dereferenced_schema: raw, timestamp: "2026-08-18T12:00:00Z"
  }, "file").timestamp`), "2026-08-18T12:00:00Z");
  assert.throws(() => evaluate(context, `parseSchema({
    dereferenced_schema: raw, timestamp: "invalid"
  }, "file")`), /timestamp/);
  assert.throws(() => evaluate(context, `parseSchema({
    dereferenced_schema: raw, timestamp: "2026"
  }, "file")`), /timestamp/);
  assert.throws(() => evaluate(context, `parseSchema({
    dereferenced_schema: {...raw, paths: {p: {$ref: "#/x"}}}, timestamp: null
  }, "file")`), /still contains/);
});

test("dereferencing follows pointers and preserves siblings without changing raw input", () => {
  const context = browser();
  evaluate(context, `globalThis.raw = {
    components: { schemas: { "a/b": { type: "string", description: "original" } } },
    item: { $ref: "#/components/schemas/a~1b", description: "specific" }
  }; globalThis.result = dereference(raw);`);
  assert.equal(evaluate(context, "result.item.type"), "string");
  assert.equal(evaluate(context, "result.item.description"), "specific");
  assert.equal(evaluate(context, "raw.item.$ref"), "#/components/schemas/a~1b");
  assert.equal(evaluate(context, "raw.components.schemas['a/b'].description"), "original");
  assert.equal(evaluate(context, `dereference({
    components: { "spaced name": 3 }, item: { $ref: "#/components/spaced%20name" }
  }).item`), 3);
  assert.equal(evaluate(context, `dereference({
    b: { type: "string" }, a: { $ref: "#/b", sibling: { $ref: "#/b" } }
  }).a.sibling.type`), "string");
});

test("dereferencing rejects missing, external and cyclic references", () => {
  const context = browser();
  assert.throws(() => evaluate(context, 'dereference({a: {$ref: "#/missing"}})'), /Missing reference target/);
  assert.throws(() => evaluate(context, 'dereference({a: {$ref: "https://example.test/x"}})'), /Only internal/);
  assert.throws(() => evaluate(context, 'dereference({a: {$ref: "#/b"}, b: {$ref: "#/a"}})'), /Cyclic reference/);
  assert.throws(() => evaluate(context, 'dereference({a: {$ref: "#/b", sibling: {$ref: "#/a"}}, b: {type: "string"}})'), /Cyclic reference/);
  assert.throws(() => evaluate(context, 'dereference({a: {$ref: "#/bad~2name"}})'), /Invalid JSON pointer/);
});

test("operation index uses all tags, includes untagged operations, and counts skipped paths", () => {
  const context = browser();
  evaluate(context, `globalThis.index = operationIndex({ paths: {
    "/one": { get: { operationId: "One", tags: ["Market", "Other", "Market"] } },
    "/two": { post: { operationId: "Two" } },
    "/three": { $ref: "#/other" },
    "/four": { get: {} }
  }});`);
  assert.equal(evaluate(context, 'index.groups.get("Market").length'), 1);
  assert.equal(evaluate(context, 'index.groups.get("Other")[0].operation.operationId'), "One");
  assert.equal(evaluate(context, 'index.groups.get("(Untagged)")[0].method'), "POST");
  assert.equal(evaluate(context, "index.skipped"), 2);
});

test("date validation rejects malformed and impossible dates", () => {
  const context = browser();
  assert.equal(evaluate(context, 'isDate("2024-02-29")'), true);
  assert.equal(evaluate(context, 'isDate("2025-02-29")'), false);
  assert.equal(evaluate(context, 'isDate("2026-2-1")'), false);
});

test("a late schema fetch cannot replace a newer date selection", async () => {
  const context = browser();
  const response = (title) => ({
    ok: true,
    json: async () => ({
      openapi: "3.1.0", info: { title }, paths: {}, components: {},
    }),
  });
  let finishOld;
  context.fetch = (url) => {
    if (url.searchParams.get("compatibility_date") === "2026-01-01") {
      return new Promise((resolve) => { finishOld = resolve; });
    }
    return Promise.resolve(response("new"));
  };
  evaluate(context, "applySchema = (schema) => { globalThis.applied = schema; }");
  const select = context.document.getElementById("compatibility-date");
  const fetchButton = context.document.getElementById("fetch-schema");
  select.value = "2026-01-01";
  const oldRequest = fetchButton.click();
  select.value = "2026-02-01";
  select.change();
  await fetchButton.click();
  finishOld(response("old"));
  await oldRequest;
  assert.equal(evaluate(context, "applied.raw.info.title"), "new");
  assert.equal(
    context.document.getElementById("schema-status").textContent,
    "Schema for 2026-02-01 loaded.",
  );
});

test("schema and selected operation default to dereferenced and switch to raw", () => {
  const context = browser();
  evaluate(context, `applySchema(parseSchema({
    openapi: "3.1.0", info: {}, components: {schemas: {Thing: {type: "string"}}},
    paths: {"/items": {get: {operationId: "GetItems", tags: ["Market"],
      response: {$ref: "#/components/schemas/Thing"}}}}
  }, "file"))`);
  const display = context.document.getElementById("schema-json");
  const raw = context.document.getElementById("schema-view-raw");
  const dereferenced = context.document.getElementById("schema-view-dereferenced");
  assert.equal(dereferenced.checked, true);
  assert.equal(raw.checked, false);
  assert.equal(JSON.parse(display.textContent).paths["/items"].get.response.type, "string");
  evaluate(context, `state.selectedOperation = {path: "/items", method: "get"}; showCurrentView()`);
  assert.equal(JSON.parse(display.textContent).response.type, "string");
  raw.checked = true;
  dereferenced.checked = false;
  raw.change();
  assert.equal(JSON.parse(display.textContent).response.$ref, "#/components/schemas/Thing");
  assert.match(context.document.getElementById("view-heading").textContent, /GetItems/);
  context.document.getElementById("show-schema").click();
  assert.equal(JSON.parse(display.textContent).paths["/items"].get.response.$ref, "#/components/schemas/Thing");
  raw.checked = false;
  dereferenced.checked = true;
  dereferenced.change();
  assert.equal(JSON.parse(display.textContent).paths["/items"].get.response.type, "string");
});

test("dereferenced-only imports disable raw view; failed conversion remains visible", () => {
  const context = browser();
  evaluate(context, `applySchema(parseSchema({dereferenced_schema: {
    openapi: "3.1.0", info: {}, paths: {}, components: {}
  }, timestamp: null}, "file"))`);
  assert.equal(context.document.getElementById("schema-view-raw").disabled, true);
  assert.equal(context.document.getElementById("schema-view-dereferenced").checked, true);
  evaluate(context, `applySchema(parseSchema({
    openapi: "3.1.0", info: {}, paths: {"/bad": {$ref: "https://example.test/x"}},
    components: {}
  }, "file"))`);
  assert.equal(context.document.getElementById("schema-view-raw").checked, true);
  assert.equal(context.document.getElementById("schema-view-dereferenced").disabled, true);
  assert.match(context.document.getElementById("view-status").textContent, /Only internal/);
  assert.equal(context.document.getElementById("save-raw").disabled, false);
});

test("schema filenames use the loaded schema version, not the current selection", () => {
  const context = browser();
  evaluate(context, `downloadJson = (data, name) => { globalThis.downloadName = name; };
    applySchema(parseSchema({
      openapi: "3.1.0", info: {version: "2026-08-18"}, paths: {}, components: {}
    }, "file"));`);
  context.document.getElementById("compatibility-date").value = "2026-08-04";
  context.document.getElementById("save-raw").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-2026-08-18-raw.json");
  context.document.getElementById("save-dereferenced").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-2026-08-18-dereferenced.json");
  evaluate(context, `applySchema(parseSchema({dereferenced_schema: {
    openapi: "3.1.0", info: {version: "2025-01-01"}, paths: {}, components: {}
  }, timestamp: null}, "file"))`);
  context.document.getElementById("save-dereferenced").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-2025-01-01-dereferenced.json");
});

test("schema with an unknown compatibility date downloads without one and warns", () => {
  const context = browser();
  evaluate(context, `downloadJson = (data, name) => { globalThis.downloadName = name; };
    applySchema(parseSchema({
      openapi: "3.1.0", info: {version: "../invalid"}, paths: {}, components: {}
    }, "file"));`);
  context.document.getElementById("save-raw").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-raw.json");
  assert.match(context.document.getElementById("schema-status").textContent, /compatibility date.*unknown/i);
  context.document.getElementById("save-dereferenced").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-dereferenced.json");
  assert.match(context.document.getElementById("schema-status").textContent, /compatibility date.*unknown/i);
});

test("metadata filenames use the latest date regardless of input order", () => {
  const context = browser();
  evaluate(context, `downloadJson = (data, name) => { globalThis.downloadName = name; };
    state.dates = {compatibility_dates: ["2025-01-01", "2026-03-15", "2026-01-01"]};
    state.changelog = {"2025-01-01": [], "2026-03-01": [], "2026-01-01": []};`);
  context.document.getElementById("save-dates").click();
  assert.equal(evaluate(context, "downloadName"), "esi-compatibility-dates-2026-03-15.json");
  context.document.getElementById("save-changelog").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-changelog-2026-03-01.json");
  evaluate(context, `state.changelog = {changelog: {
    "2026-03-01": [], "2026-04-04": [], "2026-01-01": []
  }};`);
  context.document.getElementById("save-changelog").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-changelog-2026-04-04.json");
});

test("empty or invalid metadata dates download without a date and warn", () => {
  const context = browser();
  evaluate(context, `downloadJson = (data, name) => { globalThis.downloadName = name; };
    state.dates = {compatibility_dates: []};
    state.changelog = {"2026-03-01": [], "../invalid": []};`);
  context.document.getElementById("save-dates").click();
  assert.equal(evaluate(context, "downloadName"), "esi-compatibility-dates.json");
  assert.match(context.document.getElementById("dates-status").textContent, /date.*unknown/i);
  context.document.getElementById("save-changelog").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-changelog.json");
  assert.match(context.document.getElementById("changelog-status").textContent, /date.*unknown/i);
  evaluate(context, "state.changelog = {changelog: null}");
  context.document.getElementById("save-changelog").click();
  assert.equal(evaluate(context, "downloadName"), "esi-schema-changelog.json");
  assert.match(context.document.getElementById("changelog-status").textContent, /date.*unknown/i);
});
