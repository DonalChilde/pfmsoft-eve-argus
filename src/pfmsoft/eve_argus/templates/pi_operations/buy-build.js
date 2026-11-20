function compareP4Sources(id, producerTax, receiverTax) {
  const jitaSell = input => quote(input, "Jita Sell 5%");
  const imports = factoryImports(id, 2);
  const choices = new Map(imports.map(([input, quantity]) => {
    const isP2 = piSnapshot[input].tier === 2;
    const buy = jitaSell(input);
    const build = isP2 ? factoryCost(input, factoryImports(input, 1), producerTax, jitaSell).unit : null;
    const useBuild = build !== null && (buy === null || build < buy);
    const selected = producerTax === null && isP2 ? null : useBuild ? build : buy;
    return [input, { quantity, isP2, buy, build, selected, action: selected === null ? "Unavailable"
      : !isP2 ? "Buy direct P1"
      : buy === null ? "Build (only priced option)"
      : build === null ? "Buy (only priced option)"
      : useBuild ? "Build" : "Buy" }];
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
producer.value = carriedBuyBuildTax.get("producer") ?? producer.defaultValue;
receiver.value = carriedBuyBuildTax.get("receiver") ?? receiver.defaultValue;
const status = document.getElementById("buy-build-status");
const body = document.getElementById("buy-build-rows");
const units = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
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
  const cells = Array.from({ length: 6 }, () => append(row, "td"));
  const detail = append(body, "tr");
  detail.className = "detail-row";
  const cell = append(detail, "td");
  cell.colSpan = 7;
  const disclosure = append(cell, "details");
  disclosure.className = "buy-build-detail";
  append(disclosure, "summary", `${product.name}: input breakdown`);
  const table = append(disclosure, "table");
  const heading = append(append(table, "thead"), "tr");
  for (const column of ["Input", "Quantity / P4 cycle", "Buy / unit", "Build / unit", "Recommendation"]) {
    append(heading, "th", column).scope = "col";
  }
  return { id, cells, detailBody: append(table, "tbody") };
});

function updateBuyBuild() {
  params.set("buy-build-tax", new URLSearchParams({ producer: producer.value, receiver: receiver.value }).toString());
  carryScenario(["buy-build-tax"]);
  const producerTax = parseTax(producer.value);
  const receiverTax = parseTax(receiver.value);
  producer.setAttribute("aria-invalid", String(producerTax === null));
  receiver.setAttribute("aria-invalid", String(receiverTax === null));
  status.hidden = producerTax !== null && receiverTax !== null;
  status.textContent = status.hidden ? "" : "Enter customs rates between 0% and 100%.";
  for (const { id, cells, detailBody } of rows) {
    const { choices, mixed, buyAll, buildAll } = compareP4Sources(id, producerTax, receiverTax);
    const p2 = [...choices.values()].filter(item => item.isP2);
    const count = action => p2.filter(item => item.action.startsWith(action)).length;
    const savings = mixed !== null && buyAll !== null ? Math.max(0, buyAll - mixed) : null;
    const values = [producerTax === null ? "—" : count("Buy"), producerTax === null ? "—" : count("Build"),
      unitValue(mixed), unitValue(buyAll), unitValue(buildAll), unitValue(savings)];
    cells.forEach((cell, index) => { cell.textContent = values[index]; });
    detailBody.replaceChildren();
    for (const [input, item] of choices) {
      const row = append(detailBody, "tr");
      append(row, "th", piSnapshot[input].name).scope = "row";
      for (const value of [units.format(item.quantity), unitValue(item.buy), unitValue(item.build), item.action]) {
        append(row, "td", value);
      }
    }
  }
}

producer.addEventListener("input", updateBuyBuild);
receiver.addEventListener("input", updateBuyBuild);
updateBuyBuild();
}
