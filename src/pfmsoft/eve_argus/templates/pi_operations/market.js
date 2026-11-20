"use strict";

const params = new URLSearchParams(location.search);
const historyView = params.get("view") === "history";
const scope = document.getElementById("market-scope");
const title = historyView ? "Market History" : "Market Prices";
const priceScope = params.get("scope");
const selection = priceScope === "all" ? "all" : priceScope === "forge" ? "forge-prices" : "jita";
const reportKeys = historyView ? ["forge-history"] : selection === "all" ? ["jita", "forge-prices"] : [selection];
const summaryNames = { jita: "Jita system", "forge-prices": "The Forge region" };
document.title = `${title} | Eve Argus`;
document.getElementById("market-title").textContent = title;
document.getElementById("market-caption").textContent = title;
document.querySelector(`[data-market-nav="${historyView ? "history" : "prices"}"]`).setAttribute("aria-current", "page");
if (historyView) {
  document.querySelectorAll("[data-prices-only]").forEach(element => element.remove());
} else {
  document.getElementById("region-label").remove();
  scope.value = selection;
}

for (const key of ["extraction", "p1-inputs", "p2-inputs"]) {
  if (!params.has(key)) continue;
  for (const link of document.querySelectorAll(".nav a")) {
    const url = new URL(link.href);
    url.searchParams.set(key, params.get(key));
    link.href = url.href;
  }
}

scope.addEventListener("change", () => {
  const url = new URL(location.href);
  if (scope.value === "forge-prices") url.searchParams.set("scope", "forge");
  else if (scope.value === "all") url.searchParams.set("scope", "all");
  else url.searchParams.delete("scope");
  location.href = url.href;
});

const status = document.getElementById("market-status");
showReports(reportKeys.map(key => marketReports[key]));

function showReports(reports) {
  const sources = reports.map(({ records, ...metadata }, index) => ({
    records, metadata, summaryName: summaryNames[reportKeys[index]],
  }));
  const archivedRecords = sources.flatMap(source => source.records);
  const collator = new Intl.Collator("en", { sensitivity: "base" });
  const records = sources.flatMap(({ records, metadata, summaryName }) =>
    records.filter(record => Object.hasOwn(piSnapshot, record.type_id)).map(record => ({
      ...record, region_name: metadata.region_name, region_id: metadata.region_id, summary_name: summaryName,
    }))
  ).sort((a, b) =>
      Number(!a.market_group_name) - Number(!b.market_group_name) ||
      collator.compare(a.market_group_name ?? "", b.market_group_name ?? "") ||
      collator.compare(a.type_name, b.type_name) ||
      a.type_id - b.type_id ||
      collator.compare(a.summary_name ?? "", b.summary_name ?? "")
  );
  const region = document.getElementById("market-region");
  if (historyView && sources[0].metadata.region_name) {
    const { region_name, region_id } = sources[0].metadata;
    region.add(new Option(region_name, String(region_id)));
  }
  const metadataList = document.getElementById("market-metadata");
  const heading = document.getElementById("market-columns");
  const body = document.getElementById("market-rows");
  const priceFields = new Set([
    "five_price", "lowest", "highest", "average",
    "highest_price", "average_price", "lowest_price",
  ]);
  const priceFormat = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  const display = (value, key) => {
    if (value == null) return "—";
    if (Array.isArray(value)) return value.join(" / ");
    const text = String(value);
    if (priceFields.has(key)) return `${priceFormat.format(value)} ISK`;
    if (key.endsWith("_id") || !/^-?\d+(?:\.\d+)?$/.test(text)) return text;
    const [whole, fraction] = text.split(".");
    const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return fraction === undefined ? grouped : `${grouped}.${fraction}`;
  };
  const append = (parent, tag, content) => {
    const element = document.createElement(tag);
    element.textContent = content;
    parent.append(element);
    return element;
  };
  const label = key => ({
    five_price: "5% depth price",
    five_orders: "5% depth orders",
    five_items: "5% depth units",
  })[key] ?? key.replaceAll("_", " ");

  for (const { metadata, summaryName } of sources) {
    if (sources.length > 1) append(metadataList, "h3", summaryName);
    const list = append(metadataList, "dl", "");
    for (const [key, value] of Object.entries(metadata)) {
      append(list, "dt", label(key));
      append(list, "dd", display(value, key));
    }
  }

  const columns = new Map();
  if (historyView) columns.set("region_name", ["Region Name", "region_name"]);
  else columns.set("summary_name", ["Summary Name", "summary_name"]);
  for (const record of archivedRecords) {
    for (const [key, value] of Object.entries(record)) {
      if (key === "buy_summary" || key === "sell_summary") {
        for (const field of [
          "five_price", "five_orders", "five_items", "lowest", "highest", "average",
          "total_items", "total_orders", "filtered_items", "filtered_orders",
        ]) {
          columns.set(`${key}.${field}`, [`${key.startsWith("buy") ? "Buy" : "Sell"} ${label(field)}`, key, field]);
        }
      } else {
        columns.set(key, [label(key), key]);
      }
    }
  }
  for (const key of ["market_path_ids", "market_path_names"]) {
    const column = columns.get(key);
    if (column) {
      columns.delete(key);
      columns.set(key, column);
    }
  }
  for (const [name] of columns.values()) append(heading, "th", name).scope = "col";

  const render = () => {
    const fragment = document.createDocumentFragment();
    for (const record of records) {
      if (region?.value && region.value !== String(record.region_id)) continue;
      const row = append(fragment, "tr", "");
      for (const [, key, field] of columns.values()) {
        append(row, "td", display(field ? record[key]?.[field] : record[key], field ?? key));
      }
    }
    body.replaceChildren(fragment);
  };
  region?.addEventListener("change", render);
  status.hidden = true;
  document.getElementById("market-controls").hidden = false;
  render();
}
