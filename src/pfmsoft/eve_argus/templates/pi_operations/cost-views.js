function calculatedCostRows() {
  const rows = [];
  for (const [key, route] of Object.entries(extractionRoutes)) {
    const prefix = key === "p1" ? "extract-p0-p1" : `extract-p0-p1-${key}`;
    for (const [id] of route.recipes) {
      rows.push({ id, operation: `${prefix}-${id}`, label: `Extraction · ${route.label}`, cost: extractionCost(key, id).unit });
    }
  }
  const producer = parseTax(carriedBuyBuildTax.get("producer") ?? "6");
  const receiver = parseTax(carriedBuyBuildTax.get("receiver") ?? "6");
  for (const [key, material] of Object.entries(piSnapshot)) {
    const id = Number(key);
    for (let tier = 1; tier < material.tier; tier++) {
      rows.push({ id, operation: `p${tier}-p${material.tier}-${id}`,
        label: `P${tier} Inputs · P${tier} → P${material.tier}`, cost: carriedFactoryCost(id, tier) });
    }
    if (material.tier === 4) {
      const costs = compareP4Sources(id, producer, receiver);
      for (const [basis, label] of [["mixed", "Best available"], ["buyAll", "Buy all P2"], ["buildAll", "Build all P2"]]) {
        rows.push({ id, operation: `p4-buy-build-${basis}-${id}`, label: `P4 Buy/Build · ${label}`, cost: costs[basis] });
      }
    }
  }
  return rows.sort((a, b) => a.id === b.id ? collator.compare(a.label, b.label)
    : piSnapshot[a.id].tier - piSnapshot[b.id].tier || collator.compare(piSnapshot[a.id].name, piSnapshot[b.id].name));
}

const storageKey = `eve-argus:pi-costs:v1:${location.pathname}`;
const savedView = viewId === "exported-costs-view";
const costBody = document.getElementById("cost-rows");
const costStatus = document.getElementById("cost-status");
const downloadCosts = document.getElementById("download-costs");
const clearCosts = document.getElementById("clear-costs");
const selected = new Map();
let saved;

function costCell(row, value, heading = false) {
  const cell = document.createElement(heading ? "th" : "td");
  if (heading) cell.scope = "row";
  cell.textContent = value;
  row.append(cell);
  return cell;
}

function exportProfile(entries) {
  const ordered = Object.fromEntries([...entries].sort(([a], [b]) => Number(a) - Number(b)));
  return {
    prices: Object.fromEntries(Object.entries(ordered).map(([id, entry]) => [id, entry.unit_cost])),
    description: "Selected EVE Argus PI off-planet unit costs in ISK; sales tax and transport excluded.",
    operations: ordered,
  };
}

try {
  const raw = sessionStorage.getItem(storageKey);
  saved = new Map(Object.entries(raw === null ? {} : JSON.parse(raw)));
} catch (error) {
  costStatus.textContent = `Unable to read browser-session exports: ${error.message}`;
}

function storeCosts(entries) {
  try {
    sessionStorage.setItem(storageKey, JSON.stringify(Object.fromEntries(entries)));
    saved = entries;
    return true;
  } catch (error) {
    costStatus.textContent = `Unable to save browser-session exports: ${error.message}`;
    return false;
  }
}

function showSavedCosts() {
  costBody.replaceChildren();
  downloadCosts.disabled = clearCosts.disabled = !saved?.size;
  if (!saved) return;
  costStatus.textContent = saved.size ? `${saved.size} saved material costs.` : "No costs have been exported in this tab.";
  const ordered = [...saved.values()].sort((a, b) => a.tier - b.tier || collator.compare(a.type_name, b.type_name));
  for (const entry of ordered) {
    const row = costBody.insertRow();
    costCell(row, entry.type_name, true);
    costCell(row, `P${entry.tier}`);
    costCell(row, entry.operation_label);
    costCell(row, unitValue(Number(entry.unit_cost)));
    costCell(row, entry.exported_at);
  }
}

if (savedView) {
  showSavedCosts();
  downloadCosts.addEventListener("click", () => {
    if (!saved?.size) return;
    const blob = new Blob([JSON.stringify(exportProfile(saved), null, 2) + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "pi-unit-costs.json";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    costStatus.textContent = `${saved.size} saved material costs. JSON download requested.`;
  });
  clearCosts.addEventListener("click", () => {
    if (storeCosts(new Map())) showSavedCosts();
  });
} else {
  const exportSelected = document.getElementById("export-selected-costs");
  const clearSelected = document.getElementById("clear-selected-costs");
  const updateSelection = () => {
    exportSelected.disabled = clearSelected.disabled = selected.size === 0;
    costStatus.textContent = `${selected.size} material costs selected.`;
  };
  clearSelected.addEventListener("click", () => {
    for (const checkbox of costBody.querySelectorAll('input[type="checkbox"]:checked')) {
      checkbox.checked = false;
    }
    selected.clear();
    updateSelection();
  });
  exportSelected.addEventListener("click", () => {
    if (!saved || !selected.size) return;
    const next = new Map(saved);
    const exportedAt = new Date().toISOString();
    for (const [id, row] of selected) {
      next.set(String(id), {
        type_name: piSnapshot[id].name,
        tier: piSnapshot[id].tier,
        unit_cost: row.cost.toFixed(8).replace(/\.?0+$/, ""),
        operation_id: row.operation,
        operation_label: row.label,
        exported_at: exportedAt,
        market_orders_received_at: marketReports.jita.received_at,
      });
    }
    if (storeCosts(next)) {
      costStatus.textContent = `${selected.size} material costs saved to Exported Costs.`;
    }
  });
  const market = document.getElementById("cost-market-source");
  const operationFilter = document.getElementById("cost-operation-filter");
  const checkboxes = new Map();
  const rows = calculatedCostRows().map(entry => {
    const { id, label, cost } = entry;
    const row = costBody.insertRow();
    costCell(row, piSnapshot[id].name, true);
    costCell(row, `P${piSnapshot[id].tier}`);
    costCell(row, label);
    costCell(row, unitValue(cost));
    const marketCell = costCell(row, "");
    const marginCell = costCell(row, "");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.disabled = !saved || !Number.isFinite(cost);
    checkbox.setAttribute("aria-label", `Select ${piSnapshot[id].name} from ${label}`);
    costCell(row, "").append(checkbox);
    if (!checkboxes.has(id)) checkboxes.set(id, []);
    checkboxes.get(id).push(checkbox);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        for (const other of checkboxes.get(id)) other.checked = other === checkbox;
        selected.set(id, entry);
      } else {
        selected.delete(id);
      }
      updateSelection();
    });
    return { id, label, cost, row, marketCell, marginCell };
  });
  const operationLabels = [...new Set(rows.map(({ label }) => label))];
  for (const label of operationLabels.sort(collator.compare)) {
    operationFilter.add(new Option(label));
  }
  const filterRows = () => {
    const operation = operationFilter.value;
    for (const { label, row } of rows) {
      row.hidden = operation !== "" && label !== operation;
    }
  };
  operationFilter.addEventListener("change", filterRows);
  filterRows();
  const updateMarket = () => {
    for (const { id, cost, marketCell, marginCell } of rows) {
      const price = quote(id, market.value);
      const margin = price > 0 && cost !== null ? 100 * (price - cost) / price : null;
      marketCell.textContent = unitValue(price);
      marginCell.textContent = margin === null ? "—" : `${format(margin)}%`;
      marginCell.classList.toggle("positive", margin > 0);
      marginCell.classList.toggle("negative", margin < 0);
    }
  };
  market.addEventListener("change", updateMarket);
  updateMarket();
  if (saved) costStatus.textContent = `${rows.length} calculated costs. ${saved.size} materials already exported.`;
}
