const buyOverrideKey = "p4-buy-overrides";
const buyOverrides = new Map((params.get(buyOverrideKey) ?? "").split(",").filter(Boolean)
  .map(entry => entry.startsWith("build:") ? [entry.slice(6), false] : [entry, true]));
const buyOverrideId = (output, input) => `${output}-${input}`;

function compareP4Sources(id, producerTax, receiverTax) {
  const jitaSell = input => quote(input, "Jita Sell 5%");
  const imports = factoryImports(id, 2);
  const choices = new Map(imports.map(([input]) => {
    const isP2 = piSnapshot[input].tier === 2;
    const buy = jitaSell(input);
    const build = isP2 ? factoryCost(input, factoryImports(input, 1), producerTax, jitaSell).unit : null;
    const defaultBuy = build === null || (buy !== null && buy <= build);
    const override = isP2 ? buyOverrides.get(buyOverrideId(id, input)) : undefined;
    const useBuy = override ?? defaultBuy;
    const selected = producerTax === null && isP2 ? null : useBuy ? buy : build;
    return [input, { isP2, buy, build, selected, defaultBuy, useBuy,
      action: override !== undefined ? `${selected === null ? "Unavailable: " : ""}${useBuy ? "Buy" : "Build"} (override)`
      : selected === null ? "Unavailable"
      : !isP2 ? "Buy direct P1"
      : buy === null ? "Build (only priced option)"
      : build === null ? "Buy (only priced option)"
      : useBuy ? "Buy" : "Build" }];
  }));
  const total = basis => factoryCost(id, imports, receiverTax, input => {
    const item = choices.get(input);
    return basis === "build" && !item.isP2 ? item.buy : item[basis];
  }).unit;
  return { choices, mixed: total("selected"), buyAll: total("buy"), buildAll: total("build") };
}

const carriedBuyBuildTax = new URLSearchParams(params.get("buy-build-tax") ?? "");

function initializeBuyBuild() {
const producer = document.getElementById("p2-producer-tax");
const receiver = document.getElementById("p4-receiver-tax");
const saleSource = document.getElementById("p4-sale-source");
producer.value = carriedBuyBuildTax.get("producer") ?? producer.defaultValue;
receiver.value = carriedBuyBuildTax.get("receiver") ?? receiver.defaultValue;
const status = document.getElementById("buy-build-status");
const body = document.getElementById("buy-build-rows");
const columnCount = body.parentElement.tHead.rows[0].cells.length;
const units = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const differencePercent = new Intl.NumberFormat("en-US", {
  style: "percent", maximumFractionDigits: 2, signDisplay: "exceptZero",
});
const outputs = Object.entries(piSnapshot).filter(([, product]) => product.tier === 4)
  .sort(([, a], [, b]) => collator.compare(a.name, b.name));
const source = marketReports.jita;
const freshness = source.is_stale == null ? "freshness unknown" : source.is_stale ? "stale" : "current at generation";
document.getElementById("buy-build-source").textContent =
  `Jita system orders received ${source.received_at} (${freshness})`;

function append(parent, tag, text) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  parent.append(element);
  return element;
}

const rows = outputs.map(([id, product]) => {
  const row = append(body, "tr");
  append(row, "th", product.name).scope = "row";
  const cells = Array.from({ length: columnCount - 1 }, () => append(row, "td"));
  const detail = append(body, "tr");
  detail.className = "detail-row";
  const cell = append(detail, "td");
  cell.colSpan = columnCount;
  const disclosure = append(cell, "details");
  disclosure.className = "buy-build-detail";
  append(disclosure, "summary", `${product.name}: input breakdown`);
  const table = append(disclosure, "table");
  const heading = append(append(table, "thead"), "tr");
  for (const column of ["Input", "Quantity / P4 cycle", "Buy / unit", "Build / unit", "% Difference", "Sourcing", "Buy?"]) {
    append(heading, "th", column).scope = "col";
  }
  const detailBody = append(table, "tbody");
  const inputs = new Map(factoryImports(id, 2).map(([input, quantity]) => {
    const material = piSnapshot[input];
    const row = append(detailBody, "tr");
    append(row, "th", material.name).scope = "row";
    append(row, "td", units.format(quantity));
    const prices = Array.from({ length: 4 }, () => append(row, "td"));
    const control = append(row, "td");
    let checkbox;
    if (material.tier === 2) {
      const key = buyOverrideId(id, input);
      checkbox = append(control, "input");
      checkbox.type = "checkbox";
      checkbox.setAttribute("aria-label", `Buy ${material.name} for ${product.name}`);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked === checkbox.defaultChecked) buyOverrides.delete(key);
        else buyOverrides.set(key, checkbox.checked);
        params.set(buyOverrideKey, [...buyOverrides].map(([key, buy]) => buy ? key : `build:${key}`).join(","));
        carryScenario([buyOverrideKey]);
        updateBuyBuild();
      });
    } else {
      control.textContent = "—";
    }
    return [input, { prices, checkbox }];
  }));
  return { id, cells, inputs };
});

function profitAndMargin(sale, cost) {
  if (!Number.isFinite(sale) || !Number.isFinite(cost)) return ["—", "—"];
  const profit = sale - cost;
  const margin = sale > 0 ? `${format(100 * profit / sale)}%` : "—";
  return [unitValue(profit), margin];
}

function updateBuyBuild() {
  params.set("buy-build-tax", new URLSearchParams({ producer: producer.value, receiver: receiver.value }).toString());
  carryScenario(["buy-build-tax"]);
  const producerTax = parseTax(producer.value);
  const receiverTax = parseTax(receiver.value);
  producer.setAttribute("aria-invalid", String(producerTax === null));
  receiver.setAttribute("aria-invalid", String(receiverTax === null));
  status.hidden = producerTax !== null && receiverTax !== null;
  status.textContent = status.hidden ? "" : "Enter customs rates between 0% and 100%.";
  for (const { id, cells, inputs } of rows) {
    const { choices, mixed, buyAll, buildAll } = compareP4Sources(id, producerTax, receiverTax);
    const p2 = [...choices.values()].filter(item => item.isP2);
    const count = action => p2.filter(item => item.action.startsWith(action)).length;
    const savings = mixed !== null && buyAll !== null ? buyAll - mixed : null;
    const sale = quote(id, saleSource.value);
    const values = [producerTax === null ? "—" : count("Buy"), producerTax === null ? "—" : count("Build"),
      unitValue(mixed), unitValue(buyAll), unitValue(buildAll), unitValue(savings), unitValue(sale),
      ...[mixed, buyAll, buildAll].flatMap(cost => profitAndMargin(sale, cost))];
    cells.forEach((cell, index) => { cell.textContent = values[index]; });
    for (const [input, item] of choices) {
      const { prices: [buyCell, buildCell, differenceCell, actionCell], checkbox } = inputs.get(input);
      const { buy, build } = item;
      const difference = Number.isFinite(buy) && buy > 0 && Number.isFinite(build)
        ? differencePercent.format((buy - build) / buy) : "—";
      buyCell.textContent = unitValue(buy);
      buildCell.textContent = unitValue(build);
      differenceCell.textContent = difference;
      differenceCell.classList.toggle("positive", difference.startsWith("+"));
      differenceCell.classList.toggle("negative", difference.startsWith("-"));
      actionCell.textContent = item.action;
      if (checkbox) {
        checkbox.defaultChecked = item.defaultBuy;
        checkbox.checked = item.useBuy;
      }
    }
  }
}

producer.addEventListener("input", updateBuyBuild);
receiver.addEventListener("input", updateBuyBuild);
saleSource.addEventListener("change", updateBuyBuild);
updateBuyBuild();
}
