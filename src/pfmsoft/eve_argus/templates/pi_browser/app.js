(function () {
  "use strict";
  const payload = JSON.parse(document.getElementById("pi-data").textContent);
  const engine = PIEngine.create(payload);
  const state = engine.initialState(), selections = {};
  const byId = id => document.getElementById(id);
  const labels = {
    "jita-buy-5": "Jita buy 5%", "jita-sell-5": "Jita sell 5%",
    "the-forge-history-10d": "The Forge ten-day history"
  };
  let result = null;
  function node(tag, text, attributes = {}) {
    const element = document.createElement(tag);
    if (text !== null && text !== undefined) element.textContent = text;
    for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
    return element;
  }
  function number(value) { return value === null || value === undefined ? "Unavailable" : value.toFixed(2); }
  function decimalText(value) { return value === null || value === undefined ? "Unavailable" : String(value); }
  function table(headers) {
    const element = node("table");
    const head = node("thead"), row = node("tr");
    for (const header of headers) row.append(node("th", header, { scope: "col" }));
    head.append(row);
    const body = node("tbody");
    element.append(head, body);
    return { element, body };
  }
  function cell(row, text, className = "") {
    const element = node("td", text, { class: className });
    row.append(element);
    return element;
  }
  function money(row, value) {
    const element = cell(row, number(value), "number");
    if (value === null) element.classList.add("unavailable");
    return element;
  }
  function profit(row, value) {
    const element = money(row, value);
    if (value !== null) element.classList.add(value.gt(0) ? "positive" : value.lt(0) ? "negative" : "muted");
  }
  function exportCheckbox(typeId, key, quote, label) {
    const checkbox = node("input", null, { type: "checkbox", "aria-label": `Export ${label}` });
    checkbox.checked = selections[typeId] === key;
    checkbox.disabled = quote.unitCost === null && !checkbox.checked;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selections[typeId] = key;
      else delete selections[typeId];
      render();
    });
    return checkbox;
  }
  function sourceTable() {
    const target = byId("sources");
    const grid = table(["Material", "Tier", "Shared source", "Unit cost ISK", "Export source"]);
    for (const row of engine.materials.values()) {
      const material = row.material, quote = result.sources.get(material.type_id);
      const tr = node("tr");
      cell(tr, `${material.name} (${material.type_id})`, "name");
      cell(tr, `P${material.tier}`);
      const selector = node("select", null, { "aria-label": `Source for ${material.name}`, "data-source": material.type_id });
      for (const choice of engine.choicesFor(material.type_id)) selector.append(node("option", choice.label, { value: choice.value }));
      selector.value = state.choices[material.type_id] || quote.kind;
      selector.addEventListener("change", () => { state.choices[material.type_id] = selector.value; render(); });
      cell(tr, null).append(selector);
      const cost = money(tr, quote.unitCost);
      cost.title = quote.reason || quote.label;
      cell(tr, null).append(exportCheckbox(material.type_id, `source:${material.type_id}`, quote, `${material.name} selected source`));
      grid.body.append(tr);
    }
    target.replaceChildren(grid.element);
  }
  function visibleRows() {
    const query = byId("search").value.trim().toLowerCase();
    const start = byId("starting-tier").value;
    const positive = byId("profitable-only").checked;
    return result.rows.filter(row =>
      (!query || row.name.toLowerCase().includes(query) || String(row.typeId).includes(query)) &&
      (start === "" || String(row.startingTier) === start) &&
      (!positive || row.profit !== null && row.profit.gt(0)));
  }
  function tree(quote) {
    const list = node("ul", null, { class: "tree" });
    const stage = quote.stage || quote;
    if (stage.children) {
      list.append(node("li", `Per own recipe cycle: acquisition incl. upstream ${number(stage.acquisition)}; new import ${number(stage.imports)}; export ${number(stage.exports)} ISK.`));
      for (const input of stage.children) {
        const material = engine.materials.get(input.source.typeId).material;
        const item = node("li", `${input.quantity} x ${material.name}; ${input.source.label}; ${number(input.source.unitCost)} ISK/unit; ${input.source.boundary}; this-stage import ${number(input.importTax)} ISK.`);
        if (input.source.reason) item.append(node("p", input.source.reason, { class: "unavailable" }));
        if (input.source.children || input.source.stage) item.append(tree(input.source));
        list.append(item);
      }
    }
    return list;
  }
  function comparisons() {
    const target = byId("comparisons");
    target.replaceChildren();
    const groups = new Map(), cheapest = new Map();
    for (const row of result.rows) {
      if (row.cost !== null && (!cheapest.has(row.typeId) || row.cost.lt(cheapest.get(row.typeId)))) cheapest.set(row.typeId, row.cost);
    }
    for (const row of visibleRows()) {
      const key = `${row.startingTier}:${row.tier}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    }
    if (!groups.size) target.append(node("p", "No comparisons match these filters."));
    for (const rows of groups.values()) {
      const sort = byId("sort").value;
      rows.sort((a, b) => {
        if (sort === "name") return a.name.localeCompare(b.name, "en");
        const x = sort === "profit" ? a.profit : a.cost, y = sort === "profit" ? b.profit : b.cost;
        if (x === null || y === null) return x === y ? a.typeId - b.typeId : x === null ? 1 : -1;
        return (sort === "profit" ? y.cmp(x) : x.cmp(y)) || a.typeId - b.typeId;
      });
      target.append(node("h2", `From P${rows[0].startingTier} to P${rows[0].tier}`));
      const grid = table(["Product", "Unit cost ISK", "Sales ISK", "Unit profit ISK", "Factory cycles /hour", "Units/hour", "Profit/hour", "Profit/day", "Profit/30 days", "Details", "Export"]);
      for (const row of rows) {
        const tr = node("tr", null, { "data-route": row.key });
        if (selections[row.typeId] === row.key) tr.classList.add("chosen");
        cell(tr, `${row.name} (${row.typeId})`, "name");
        const cost = money(tr, row.cost);
        cost.title = row.root.reason || "Exported unit cost; excludes sales tax and transport.";
        if (row.cost !== null && row.cost.eq(cheapest.get(row.typeId))) cost.append(node("span", " [best]", { class: "positive" }));
        money(tr, row.sale); profit(tr, row.profit);
        const cycles = node("input", null, {
          type: "number", min: "0", step: "any",
          "aria-label": `Factory cycles for ${row.name} from P${row.startingTier}`, "data-cycles": row.key
        });
        cycles.value = state.cycles[row.key] ?? "1";
        cycles.addEventListener("change", () => { state.cycles[row.key] = cycles.value; render(); });
        cell(tr, null).append(cycles);
        money(tr, row.unitsPerHour); profit(tr, row.profitPerHour);
        profit(tr, row.profitPerDay); profit(tr, row.profitPer30Days);
        const details = node("details");
        details.append(node("summary", "Recipe / taxes"), tree(row.root));
        if (row.root.reason) details.append(node("p", row.root.reason, { class: "unavailable" }));
        cell(tr, null).append(details);
        cell(tr, null).append(exportCheckbox(row.typeId, row.key, row.root, `${row.name} from P${row.startingTier}`));
        grid.body.append(tr);
      }
      const scroll = node("div", null, { class: "table-scroll" });
      scroll.append(grid.element);
      target.append(scroll);
    }
  }
  function selectedQuote(id, key) {
    if (key === `source:${id}`) return result.sources.get(Number(id));
    return result.rows.find(row => row.key === key && row.typeId === Number(id))?.root;
  }
  function selectionSummary() {
    const entries = Object.entries(selections);
    const grid = table(["Material", "Selected quote", "Unit cost ISK", "Remove"]);
    let invalid = false;
    for (const [id, key] of entries) {
      const quote = selectedQuote(id, key), tr = node("tr");
      cell(tr, engine.materials.get(Number(id)).material.name, "name");
      cell(tr, quote?.label || "Unavailable", "name");
      money(tr, quote?.unitCost ?? null);
      if (!quote || quote.unitCost === null) invalid = true;
      const remove = node("button", "Remove");
      remove.addEventListener("click", () => { delete selections[id]; render(); });
      cell(tr, null).append(remove);
      grid.body.append(tr);
    }
    byId("selected-prices").replaceChildren(grid.element);
    byId("selection-status").textContent = `${entries.length} selected type(s).` +
      (invalid ? " A selected quote is unavailable; change or remove it before downloading." : "");
    byId("selection-status").className = invalid ? "error" : "";
    byId("download").disabled = invalid || entries.length === 0;
    byId("export-preview").value = invalid || entries.length === 0 ? "" :
      JSON.stringify(engine.exportPrices(result, selections), null, 2);
  }
  function references() {
    const target = byId("references");
    for (const [field, title] of [["buy", "Jita buy 5%"], ["sell", "Jita sell 5%"], ["history", "The Forge ten-day history"]]) {
      target.append(node("h2", title));
      if (field === "history") {
        const window = payload.inputs.history_window;
        target.append(node("p", window ? `Regional window: ${window.oldest_date} through ${window.newest_date}. Missing days contribute zero to the ten-calendar-day volume average.` : "No stored regional window."));
      }
      const grid = table(field === "history" ?
        ["Material", "Tier", "Price ISK", "Regional units/day", "Coverage", "Newest day", "Freshness", "Received"] :
        ["Material", "Tier", "Price ISK"]);
      for (const row of engine.materials.values()) {
        const tr = node("tr"), metrics = row.history_metrics;
        cell(tr, `${row.material.name} (${row.material.type_id})`, "name");
        cell(tr, `P${row.material.tier}`);
        const price = cell(tr, decimalText(row[field].unit_cost), "number");
        price.title = row[field].unavailable_reason || "Exact source input price.";
        if (field === "history") {
          cell(tr, decimalText(metrics?.average_daily_volume));
          cell(tr, metrics?.missing_days === null || !metrics ? "Unavailable" : `${10 - metrics.missing_days}/10`);
          cell(tr, metrics?.newest_date_used || "Unavailable");
          cell(tr, metrics?.freshness || "Missing");
          cell(tr, metrics?.received_at || "Unavailable");
        }
        grid.body.append(tr);
      }
      const scroll = node("div", null, { class: "table-scroll" });
      scroll.append(grid.element); target.append(scroll);
    }
  }
  function render() {
    try {
      result = engine.calculate(state);
      byId("error").hidden = true;
      byId("comparisons").hidden = byId("sources").hidden = false;
      sourceTable(); comparisons(); selectionSummary();
      byId("scenario-status").textContent = `${byId("preset").selectedOptions[0].textContent}; ${Object.keys(state.choices).length} manual source override(s). ${result.rows.length} route comparisons.`;
      byId("scenario-notices").replaceChildren(...result.notices.map(message => node("p", message)));
    } catch (error) {
      console.error(error);
      byId("error").textContent = `Calculations stopped: ${error.message} Correct the input to restore result values.`;
      byId("error").hidden = false;
      for (const value of document.querySelectorAll("#comparisons .number, #sources .number, #selected-prices .number")) value.textContent = "Unavailable";
      for (const details of document.querySelectorAll("#comparisons td details")) details.hidden = true;
      for (const checkbox of document.querySelectorAll("#comparisons input[type=checkbox], #sources input[type=checkbox]")) checkbox.disabled = true;
      byId("download").disabled = true;
      byId("export-preview").value = "";
      result = null;
    }
  }
  for (const id of ["market-basis", "valuation-basis"]) {
    for (const [value, label] of Object.entries(labels)) byId(id).append(node("option", label, { value }));
  }
  byId("market-basis").value = state.marketBasis;
  byId("valuation-basis").value = state.valuationBasis;
  byId("tax-rate").value = new Decimal(state.taxRate).mul(100).toFixed();
  byId("boundary").value = state.intermediateBoundary;
  for (const [id, key] of [["market-basis", "marketBasis"], ["valuation-basis", "valuationBasis"], ["boundary", "intermediateBoundary"]]) {
    byId(id).addEventListener("change", () => { state[key] = byId(id).value; render(); });
  }
  byId("tax-rate").addEventListener("change", () => {
    try { state.taxRate = new Decimal(byId("tax-rate").value).div(100).toFixed(); }
    catch (error) { console.error(error); state.taxRate = "NaN"; }
    render();
  });
  byId("preset").addEventListener("change", () => {
    if (Object.keys(state.choices).length && !confirm("Applying this preset replaces your manual source overrides. Continue?")) {
      byId("preset").value = state.preset; return;
    }
    state.preset = byId("preset").value; state.choices = {}; render();
  });
  for (const id of ["search", "starting-tier", "profitable-only", "sort"]) byId(id).addEventListener(id === "search" ? "input" : "change", render);
  byId("clear-selection").addEventListener("click", () => {
    for (const id of Object.keys(selections)) delete selections[id];
    render();
  });
  byId("add-profitable").addEventListener("click", () => {
    if (!result) return;
    const candidates = new Map();
    for (const row of visibleRows()) {
      if (row.profit === null || !row.profit.gt(0) || selections[row.typeId]) continue;
      if (!candidates.has(row.typeId) || row.cost.lt(candidates.get(row.typeId).cost)) candidates.set(row.typeId, row);
    }
    for (const row of candidates.values()) selections[row.typeId] = row.key;
    render();
  });
  byId("download").addEventListener("click", () => {
    if (!result) return;
    try {
      const profile = engine.exportPrices(result, selections);
      const url = URL.createObjectURL(new Blob([JSON.stringify(profile, null, 2) + "\n"], { type: "application/json" }));
      const anchor = node("a", null, { href: url, download: "pi-unit-prices.json" });
      document.body.append(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      console.error(error);
      byId("selection-status").textContent = error.message;
      byId("selection-status").className = "error";
    }
  });
  references();
  render();
})();
