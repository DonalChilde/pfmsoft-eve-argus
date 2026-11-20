"use strict";

const materialsByTier = {
  P0: [
    "Aqueous Liquids", "Autotrophs", "Base Metals", "Carbon Compounds",
    "Complex Organisms", "Felsic Magma", "Heavy Metals", "Ionic Solutions",
    "Microorganisms", "Noble Gas", "Noble Metals", "Non-CS Crystals",
    "Planktic Colonies", "Reactive Gas", "Suspended Plasma",
  ],
  P1: [
    "Bacteria", "Biofuels", "Biomass", "Chiral Structures", "Electrolytes",
    "Industrial Fibers", "Oxidizing Compound", "Oxygen", "Plasmoids",
    "Precious Metals", "Proteins", "Reactive Metals", "Silicon", "Toxic Metals",
    "Water",
  ],
  P2: [
    "Biocells", "Construction Blocks", "Consumer Electronics", "Coolant",
    "Enriched Uranium", "Fertilizer", "Genetically Enhanced Livestock",
    "Livestock", "Mechanical Parts", "Microfiber Shielding",
    "Miniature Electronics", "Nanites", "Oxides", "Polyaramids", "Polytextiles",
    "Rocket Fuel", "Silicate Glass", "Superconductors", "Supertensile Plastics",
    "Synthetic Oil", "Test Cultures", "Transmitter", "Viral Agent",
    "Water-Cooled CPU",
  ],
  P3: [
    "Biotech Research Reports", "Camera Drones", "Condensates",
    "Cryoprotectant Solution", "Data Chips", "Gel-Matrix Biopaste",
    "Guidance Systems", "Hazmat Detection Systems", "Hermetic Membranes",
    "High-Tech Transmitters", "Industrial Explosives", "Neocoms",
    "Nuclear Reactors", "Planetary Vehicles", "Robotics", "Smartfab Units",
    "Supercomputers", "Synthetic Synapses", "Transcranial Microcontrollers",
    "Ukomi Superconductors", "Vaccines",
  ],
};

const extractionP1Recipes = [
  [2393, "Bacteria", "Microorganisms"],
  [2396, "Biofuels", "Carbon Compounds"],
  [3779, "Biomass", "Planktic Colonies"],
  [2401, "Chiral Structures", "Non-CS Crystals"],
  [2390, "Electrolytes", "Ionic Solutions"],
  [2397, "Industrial Fibers", "Autotrophs"],
  [2392, "Oxidizing Compound", "Reactive Gas"],
  [3683, "Oxygen", "Noble Gas"],
  [2389, "Plasmoids", "Suspended Plasma"],
  [2399, "Precious Metals", "Noble Metals"],
  [2395, "Proteins", "Complex Organisms"],
  [2398, "Reactive Metals", "Base Metals"],
  [9828, "Silicon", "Felsic Magma"],
  [2400, "Toxic Metals", "Heavy Metals"],
  [3645, "Water", "Aqueous Liquids"],
];
const extractionP2SingleRecipes = [
  [2329, "Biocells", [2396, 2399], "Barren"],
  [3828, "Construction Blocks", [2398, 2400], "Lava, Plasma"],
  [9836, "Consumer Electronics", [2400, 2401], "Lava, Plasma"],
  [9832, "Coolant", [2390, 3645], "Gas, Storm"],
  [44, "Enriched Uranium", [2399, 2400], "Plasma"],
  [3693, "Fertilizer", [2393, 2395], "Oceanic, Temperate"],
  [15317, "Genetically Enhanced Livestock", [2395, 3779], "Oceanic"],
  [3725, "Livestock", [2395, 2396], "Oceanic, Temperate"],
  [3689, "Mechanical Parts", [2398, 2399], "Barren, Plasma"],
  [9842, "Miniature Electronics", [2401, 9828], "Lava"],
  [2463, "Nanites", [2393, 2398], "Barren"],
  [2317, "Oxides", [2392, 3683], "Gas"],
  [3695, "Polytextiles", [2396, 2397], "Temperate"],
  [9830, "Rocket Fuel", [2389, 2390], "Storm"],
  [9838, "Superconductors", [2389, 3645], "Storm"],
  [2312, "Supertensile Plastics", [3683, 3779], "Ice"],
  [3691, "Synthetic Oil", [2390, 3683], "Gas, Storm"],
  [2319, "Test Cultures", [2393, 3645], "Barren, Ice, Oceanic, Temperate"],
  [9840, "Transmitter", [2389, 2401], "Lava, Plasma"],
  [3775, "Viral Agent", [2393, 3779], "Ice, Oceanic"],
  [2328, "Water-Cooled CPU", [2398, 3645], "Barren, Gas, Storm"],
];
const extractionP2SplitRecipes = [
  ...extractionP2SingleRecipes,
  [2327, "Microfiber Shielding", [2397, 9828]],
  [2321, "Polyaramids", [2392, 2397]],
  [3697, "Silicate Glass", [2392, 9828]],
].sort((a, b) => collator.compare(a[1], b[1]));
const extractionRoutes = {
  p1: { tier: "P1", label: "P0 → P1", recipes: extractionP1Recipes },
  "p2-single": {
    tier: "P2", label: "P0 → P1 → P2 single",
    recipes: extractionP2SingleRecipes, defaultRate: 3,
  },
  "p2-split": {
    tier: "P2", label: "P0 → P1 → P2 split",
    recipes: extractionP2SplitRecipes, defaultRate: 3,
  },
};

const marketChoices = ["Jita Buy 5%", "Jita Sell 5%", "The Forge Avg"];
const freshness = stale => stale == null ? "freshness unknown" : stale ? "stale" : "current at generation";
const orderSource = `Jita system orders received ${marketReports.jita.received_at} (${freshness(marketReports.jita.is_stale)})`;
const sourceDescriptions = {
  "Jita Buy 5%": `Buy-side 5% depth price. ${orderSource}.`,
  "Jita Sell 5%": `Sell-side 5% depth price. ${orderSource}.`,
};
const materialsByName = new Map(Object.entries(piSnapshot).map(([id, material]) => [material.name, Number(id)]));
const materialSelectors = new Map();
const taxInput = document.getElementById("tax-rate");
const saleSource = document.getElementById("sale-source");
const extractionPage = document.getElementById("extraction-p1-operations") !== null;
const pageParams = new URLSearchParams(location.search);
const carriedExtraction = new URLSearchParams(pageParams.get("extraction") ?? "");
const carriedFactory = {
  1: new URLSearchParams(pageParams.get("p1-inputs") ?? ""),
  2: new URLSearchParams(pageParams.get("p2-inputs") ?? ""),
  3: new URLSearchParams(pageParams.get("p3-inputs") ?? ""),
};
const localAssignments = new Map();
const operationsTableWrap = document.querySelector(".operations-table-wrap");
const factoryRecipe = document.getElementById("factory-recipe");
const factoryView = pageParams.get("view");
const factoryInputTier = !factoryRecipe ? 1 : factoryView === "p3" ? 3 : factoryView === "p2" ? 2 : 1;
const factorySources = [
  { label: "P1 Inputs · P1 → P2", inputTier: 1, outputTier: 2 },
  { label: "P1 Inputs · P1 → P3", inputTier: 1, outputTier: 3 },
  { label: "P2 Inputs · P2 → P3", inputTier: 2, outputTier: 3 },
];

function extractionCost(route, id) {
  const product = piSnapshot[id];
  const tax = parseTax(extractionPage ? taxInput.value : carriedExtraction.get("tax") ?? "6");
  return calculate(route, id, true);

  function calculate(key, typeId, exportOutput) {
    const material = piSnapshot[typeId];
    const inputs = material.inputs.map(([inputId, quantity]) => {
      const source = extractionPage
        ? materialSelectors.get(inputId).value
        : carriedExtraction.get(`source-${inputId}`) ?? (key === "p1" ? "Extracted P0" : "Jita Sell 5%");
      const local = key === "p2-split"
        ? Number(extractionPage ? localAssignments.get(typeId).value : carriedExtraction.get(`local-${typeId}`) ?? product.inputs[0][0])
        : null;
      if (key === "p1") {
        return { id: inputId, quantity, cost: source === "Extracted P0" ? 0 : quote(inputId, source), imported: source !== "Extracted P0" };
      }
      const isLocal = key === "p2-single" || inputId === local;
      return {
        id: inputId, quantity, imported: !isLocal,
        cost: isLocal ? calculate("p1", inputId, false).unit : quote(inputId, source),
      };
    });
    return costStage(material, inputs, tax, exportOutput);
  }
}

function selectedCost(id) {
  return sourceCost(id, materialSelectors.get(id).value, factoryInputTier);
}

function sourceCost(id, source, receivingTier) {
  const product = piSnapshot[id];
  const extraction = Object.entries(extractionRoutes).find(([, route]) =>
    source === `Extraction · ${route.label}` && route.recipes.some(([typeId]) => typeId === Number(id)));
  if (extraction) return extractionCost(extraction[0], id).unit;
  const factory = factorySources.find(route =>
    route.label === source && route.outputTier === product.tier && route.outputTier <= receivingTier);
  if (factory) {
    return carriedFactoryCost(id, factory.inputTier);
  }
  return source === "Extracted P0" && product.tier === 0 ? 0 : quote(id, source);
}

function carriedFactoryCost(id, startingTier) {
  const state = carriedFactory[startingTier];
  return factoryCost(id, factoryImports(id, startingTier), parseTax(state.get("tax") ?? "6"), input =>
    sourceCost(input, state.get(`source-${input}`) ?? "Jita Sell 5%", startingTier)).unit;
}

function initializeOperations() {
document.querySelector("[data-order-source]").textContent = orderSource;
document.title = `${document.querySelector("h1").textContent} | Eve Argus`;
let factoryViewMaterials;
if (factoryInputTier > 1) {
  const tier = `P${factoryInputTier}`;
  const p3Page = factoryInputTier === 3;
  document.title = `${tier} Inputs | Eve Argus`;
  document.querySelector(".nav [aria-current]").removeAttribute("aria-current");
  document.querySelector(`.nav a[data-factory-tier="${tier}"]`).setAttribute("aria-current", "page");
  document.querySelector(".eyebrow").textContent = `Factory operations · starting tier ${tier}`;
  document.querySelector("h1").textContent = `${tier} Inputs`;
  document.querySelector(".description").textContent =
    `Compare routes that use imported ${tier} materials to produce ${p3Page ? "P4" : "P3 or P4"} outputs.`;
  const note = document.querySelector(".sample-note");
  note.replaceChildren(note.querySelector("strong"),
    `${p3Page ? "" : " P3 intermediates for P4 are made on-planet without customs charges."}` +
    ` Three low-category P4 recipes also import a direct P1 ingredient. Import tax applies to ${tier} and any required P1; export tax applies only to the finished output.`);
  document.getElementById("operations-title").textContent = `${tier}-starting operations`;
  document.querySelector(".source-panel .panel-heading p").textContent =
    p3Page ? "Choose a market source or a matching upstream cost from Extraction, P1 Inputs, or P2 Inputs."
      : "Choose a market source, a matching Extraction cost, or the net cost to make and export P2 from P1 Inputs.";
  document.querySelector(".source-panel .footnote").textContent =
    "Calculated sources use the upstream settings carried here by mockup navigation, or upstream defaults when opened directly.";
  operationsTableWrap.setAttribute("aria-label", `${tier}-starting operations table`);
  for (const group of document.querySelectorAll("[data-factory-output-tier]")) {
    if (Number(group.dataset.factoryOutputTier) <= factoryInputTier) group.remove();
    else group.querySelector(".operation-group span").textContent = `${tier} → P${group.dataset.factoryOutputTier}`;
  }
  document.querySelector("[data-source-tiers]").dataset.sourceTiers = `${tier} P1`;
  factoryViewMaterials = new Set(Object.keys(piSnapshot)
    .filter(id => piSnapshot[id].tier > factoryInputTier)
    .flatMap(id => factoryImports(id, factoryInputTier).map(([input]) => Number(input))));
}

const setInputsDialog = document.getElementById("set-inputs-dialog");
const bulkInputSource = document.getElementById("bulk-input-source");
const bulkBuildBuy = document.getElementById("bulk-build-buy");
const bulkMarket = document.getElementById("bulk-build-buy-market");
const bulkThreshold = document.getElementById("bulk-build-buy-threshold");
const bulkBuildBuyMode = "build-buy";
const p1ToP2Source = factorySources.find(route => route.inputTier === 1 && route.outputTier === 2).label;
const updateBulkBuildBuy = () => {
  if (!bulkBuildBuy) return;
  bulkBuildBuy.hidden = bulkBuildBuy.disabled = bulkInputSource.value !== bulkBuildBuyMode;
};
bulkInputSource.addEventListener("change", updateBulkBuildBuy);
let bulkTargets = [];
setInputsDialog.querySelector("form").addEventListener("submit", event => {
  if (event.submitter?.value !== "apply") return;
  if (bulkInputSource.value === bulkBuildBuyMode) {
    const market = bulkMarket.value;
    const threshold = bulkThreshold.valueAsNumber;
    for (const select of bulkTargets) {
      const id = Number(select.closest(".material").dataset.typeId);
      const buy = quote(id, market);
      const build = sourceCost(id, p1ToP2Source, factoryInputTier);
      const useBuild = build !== null && (buy === null ||
        (build < buy && (buy - build) * 100 >= buy * threshold));
      select.value = useBuild ? p1ToP2Source : market;
    }
  } else {
    for (const select of bulkTargets) select.value = bulkInputSource.value;
  }
  updatePrices();
});

for (const list of document.querySelectorAll("[data-source-tiers]")) {
  const tiers = list.dataset.sourceTiers.split(/\s+/);
  const useExtractionCosts = list.hasAttribute("data-use-extraction-costs");
  for (const [index, tier] of tiers.entries()) {
    const materials = (materialsByTier[tier] ?? [])
      .filter(name => !factoryViewMaterials || factoryViewMaterials.has(materialsByName.get(name)))
      .sort((a, b) => collator.compare(a, b));
    const group = document.createElement("section");
    group.className = "material-group";
    const heading = document.createElement("div");
    heading.className = "tier-label";
    heading.id = `source-tier-${tier.toLowerCase()}-${index}`;
    heading.textContent = `${tier} INPUTS · ${materials.length} MATERIALS`;
    group.setAttribute("aria-labelledby", heading.id);
    const header = document.createElement("div");
    header.className = "material-group-heading";
    const setAll = document.createElement("button");
    setAll.type = "button";
    setAll.textContent = "Set all inputs";
    setAll.setAttribute("aria-label", `Set all inputs for ${tier}`);
    setAll.setAttribute("aria-haspopup", "dialog");
    setAll.addEventListener("click", () => {
      bulkTargets = [...group.querySelectorAll(".material select")];
      const common = [...bulkTargets[0].options].filter(option =>
        bulkTargets.every(select => [...select.options].some(candidate => candidate.value === option.value))
      );
      bulkInputSource.replaceChildren(...common.map(option => new Option(option.textContent, option.value)));
      if (factoryRecipe && factoryInputTier === 2 && tier === "P2" && common.some(option => option.value === p1ToP2Source)) {
        bulkInputSource.add(new Option("Build/Buy · market vs. P1 → P2", bulkBuildBuyMode));
      }
      const current = bulkTargets[0].value;
      if (common.some(option => option.value === current) && bulkTargets.every(select => select.value === current)) {
        bulkInputSource.value = current;
      }
      updateBulkBuildBuy();
      setInputsDialog.querySelector("h2").textContent = `Set all inputs for ${tier}`;
      setInputsDialog.showModal();
    });
    header.append(heading, setAll);
    group.append(header);

    for (const name of materials) {
      const row = document.createElement("div");
      row.className = "material";
      row.dataset.tier = tier;
      const materialName = document.createElement("div");
      materialName.className = "material-name";
      materialName.textContent = name;
      const infoButton = document.createElement("button");
      infoButton.className = "info-button";
      infoButton.type = "button";
      infoButton.textContent = "i";
      infoButton.dataset.materialInfo = "";
      infoButton.title = `More information about ${name}`;
      infoButton.setAttribute("aria-label", `More information about ${name}`);

      const select = document.createElement("select");
      select.setAttribute("aria-label", `${name} input source`);
      const id = materialsByName.get(name);
      materialSelectors.set(id, select);
      row.dataset.typeId = id;
      const extracted = "Extracted P0";
      const defaultSource = tier === "P0" ? extracted : "Jita Sell 5%";
      const choices = [...marketChoices];
      if (!useExtractionCosts && tier === "P0") choices.push(extracted);
      for (const choice of choices) {
        const option = document.createElement("option");
        option.textContent = choice;
        option.defaultSelected = choice === defaultSource;
        select.append(option);
      }
      if (useExtractionCosts) {
        for (const [key, route] of Object.entries(extractionRoutes)) {
          if (route.tier !== tier || !route.recipes.some(([, product]) => product === name)) continue;
          const option = document.createElement("option");
          option.textContent = `Extraction · ${route.label}`;
          option.dataset.extractionRoute = key;
          select.append(option);
        }
        for (const route of factorySources) {
          if (route.outputTier <= factoryInputTier && tier === `P${route.outputTier}`) {
            const option = new Option(route.label);
            option.dataset.factorySource = "";
            select.append(option);
          }
        }
        if (extractionPage) {
          const carried = carriedExtraction.get(`source-${id}`);
          if ([...select.options].some(option => option.value === carried)) select.value = carried;
        }
        if (factoryRecipe && carriedFactory[factoryInputTier]) {
          const carried = carriedFactory[factoryInputTier].get(`source-${id}`);
          if ([...select.options].some(option => option.value === carried)) select.value = carried;
        }
      }

      const price = document.createElement("div");
      price.className = "price";
      const updatePrice = () => {
        const cost = selectedCost(id);
        const value = cost === null ? null : cost === 0 ? "0" : format(cost);
        price.textContent = `${value ?? "—"} ISK/u`;
        price.setAttribute("aria-label", value === null
          ? `${name} selected unit value unavailable`
          : `${name} selected unit value: ${value} ISK per unit`);
      };
      document.addEventListener("pi-prices-change", updatePrice);
      row.append(materialName, select, price, infoButton);
      group.append(row);
    }
    list.append(group);
  }
}

const workspace = document.querySelector(".workspace");
const paneResizer = workspace?.querySelector(".pane-resizer");
const sourcePanel = workspace?.querySelector(".source-panel");
const sourceToggle = workspace?.querySelector(".source-toggle");
if (sourcePanel && sourceToggle && paneResizer) {
  sourceToggle.addEventListener("click", () => {
    const hide = !sourcePanel.hidden;
    sourcePanel.hidden = hide;
    paneResizer.hidden = hide;
    sourceToggle.setAttribute("aria-expanded", String(!hide));
    sourceToggle.textContent = hide ? "Show input materials" : "Hide input materials";
  });
  sourceToggle.hidden = false;
}

if (workspace && paneResizer) {
  const minimumShare = 20;
  const maximumShare = 55;
  let share = Number(paneResizer.getAttribute("aria-valuenow"));

  const setShare = value => {
    share = Math.max(minimumShare, Math.min(maximumShare, value));
    const gap = 12;
    const resizerWidth = 12;
    const usableWidth = workspace.clientWidth - gap * 2 - resizerWidth;
    const sourceWidth = usableWidth * share / 100;
    const operationsWidth = usableWidth - sourceWidth;
    workspace.style.setProperty("--source-pane-width", `${sourceWidth}px`);
    workspace.style.setProperty("--operations-pane-width", `${operationsWidth}px`);
    paneResizer.setAttribute("aria-valuenow", String(Math.round(share)));
    paneResizer.setAttribute("aria-valuetext", `${Math.round(share)}% input materials pane`);
  };

  const setShareFromPointer = event => {
    const bounds = workspace.getBoundingClientRect();
    const usableWidth = workspace.clientWidth - 36;
    const sourceWidth = event.clientX - bounds.left - 18;
    setShare(sourceWidth / usableWidth * 100);
  };

  paneResizer.addEventListener("pointerdown", event => {
    if (window.matchMedia("(max-width: 1100px)").matches || event.button !== 0) return;
    event.preventDefault();
    paneResizer.setPointerCapture(event.pointerId);
    document.body.classList.add("is-resizing");
    setShareFromPointer(event);
  });
  paneResizer.addEventListener("pointermove", event => {
    if (paneResizer.hasPointerCapture(event.pointerId)) setShareFromPointer(event);
  });
  const endResize = event => {
    if (paneResizer.hasPointerCapture(event.pointerId)) {
      paneResizer.releasePointerCapture(event.pointerId);
      document.body.classList.remove("is-resizing");
    }
  };
  paneResizer.addEventListener("pointerup", endResize);
  paneResizer.addEventListener("pointercancel", endResize);
  paneResizer.addEventListener("keydown", event => {
    let nextShare = share;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") nextShare -= 1;
    else if (event.key === "ArrowRight" || event.key === "ArrowUp") nextShare += 1;
    else if (event.key === "Home") nextShare = minimumShare;
    else if (event.key === "End") nextShare = maximumShare;
    else return;
    event.preventDefault();
    setShare(nextShare);
  });
  window.addEventListener("resize", () => setShare(share));
  setShare(share);
}

const materialInfoDialog = document.getElementById("material-info-dialog");
if (materialInfoDialog instanceof HTMLDialogElement) {
  const title = materialInfoDialog.querySelector("#material-info-title");
  const tier = materialInfoDialog.querySelector("#material-info-tier");
  const source = materialInfoDialog.querySelector("#material-info-source");
  const value = materialInfoDialog.querySelector("#material-info-value");
  const description = materialInfoDialog.querySelector("#material-info-description");

  document.addEventListener("click", event => {
    const button = event.target.closest("[data-material-info]");
    if (!button) return;
    const row = button.closest(".material");
    const select = row.querySelector("select");
    const selectedSource = select.value;
    const history = piSnapshot[row.dataset.typeId].history;
    title.textContent = row.querySelector(".material-name").textContent;
    tier.textContent = row.dataset.tier;
    source.textContent = selectedSource;
    value.textContent = row.querySelector(".price").textContent;
    description.textContent =
      select.selectedOptions[0].hasAttribute("data-factory-source")
        ? "Net unit cost including import and export taxes on the producing planet. This page charges import tax separately on the receiving planet."
        : select.selectedOptions[0].hasAttribute("data-extraction-route")
        ? "Calculated net unit cost from Extraction; uses its defaults or the settings carried here by mockup navigation."
        : selectedSource.startsWith("Extracted")
        ? "Zero modeled cost for internal use when available; this does not mean extraction has no real cost."
        : selectedSource === "The Forge Avg"
        ? history.oldest && history.newest
          ? `Volume-weighted regional average: ${history.oldest} to ${history.newest} (${freshness(history.stale)}).`
          : "No stored regional history window for this material."
        : sourceDescriptions[selectedSource];
    materialInfoDialog.showModal();
  });

  materialInfoDialog.querySelectorAll("[data-close-dialog]").forEach(button => {
    button.addEventListener("click", () => materialInfoDialog.close());
  });
}

const extractionP1Operations = document.getElementById("extraction-p1-operations");
if (extractionP1Operations) {
  const recipeTemplate = document.getElementById("extraction-p1-recipe");
  for (const [typeId, product, input] of extractionP1Recipes) {
    const rows = recipeTemplate.content.cloneNode(true);
    Object.assign(rows.querySelector("[data-operation]").dataset, { typeId, extractionRoute: "p1" });
    rows.querySelector(".operation-name").textContent = product;
    rows.querySelector(".operation-id").textContent = `extract-p0-p1-${typeId}`;
    rows.querySelector(".cycle-rate").setAttribute("aria-label", `Completed cycles per hour for ${product}`);
    rows.querySelector(".recipe-quantities").textContent = `P0 → P1: 3,000 ${input} → 20 ${product}`;
    extractionP1Operations.append(rows);
  }
}

const p2RecipeTemplate = document.getElementById("extraction-p2-recipe");
if (p2RecipeTemplate) {
  const p1Names = new Map(extractionP1Recipes);
  for (const key of ["p2-single", "p2-split"]) {
    const route = extractionRoutes[key];
    const group = document.getElementById(`extraction-${key}-operations`);
    const isSingle = key === "p2-single";
    for (const [typeId, product, inputIds, planets] of route.recipes) {
      const rows = p2RecipeTemplate.content.cloneNode(true);
      Object.assign(rows.querySelector("[data-operation]").dataset, { typeId, extractionRoute: key });
      rows.querySelector(".operation-name").textContent = product;
      rows.querySelector(".operation-id").textContent = `extract-p0-p1-${key}-${typeId}`;
      const rate = rows.querySelector(".cycle-rate");
      rate.defaultValue = String(route.defaultRate);
      rate.setAttribute("aria-label", `Completed cycles per hour for ${product}${isSingle ? "" : " (split)"}`);
      const ingredients = inputIds.map(id => p1Names.get(id));
      rows.querySelector(".recipe-quantities").textContent =
        `${ingredients.map(name => `40 ${name}`).join(" + ")} → 5 ${product}`;
      rows.querySelector(".single-planet-details").hidden = !isSingle;
      rows.querySelector(".split-planet-details").hidden = isSingle;
      if (isSingle) {
        rows.querySelector(".eligible-planets").textContent = planets;
        rows.querySelector(".local-input").remove();
      } else {
        const select = rows.querySelector(".local-input-select");
        const local = rows.querySelector(".local-ingredient");
        const imported = rows.querySelector(".imported-ingredient");
        select.setAttribute("aria-label", `Local P1 for ${product}`);
        for (const [index, name] of ingredients.entries()) {
          const option = document.createElement("option");
          option.textContent = name;
          option.value = inputIds[index];
          select.append(option);
        }
        const updateIngredients = () => {
          local.textContent = piSnapshot[select.value].name;
          imported.textContent = piSnapshot[inputIds.find(id => id !== Number(select.value))].name;
        };
        const carried = carriedExtraction.get(`local-${typeId}`);
        if (inputIds.includes(Number(carried))) select.value = carried;
        localAssignments.set(typeId, select);
        select.addEventListener("change", updateIngredients);
        updateIngredients();
      }
      group.append(rows);
    }
  }
}

function outputCategory(product) {
  const ingredients = product.inputs.map(([id]) => piSnapshot[id]);
  if (product.tier === 3 && ingredients.every(input => input.tier === 2)) {
    if (ingredients.length === 2) return "S";
    if (ingredients.length === 3) return "C";
  }
  if (product.tier === 4 && ingredients.length === 3) {
    const simple = ingredients.filter(input => outputCategory(input) === "S").length;
    if (simple === 2 && ingredients.some(input => input.tier === 1)) return "L";
    if (simple === 3) return "M";
    if (ingredients.every(input => outputCategory(input) === "C")) return "H";
  }
  return null;
}

if (factoryRecipe) {
  const defaultRates = {
    1: { 2: 24, 3: { S: 5, C: 3 }, 4: { L: 1, M: 0.5, H: 0.5 } },
    2: { 3: 24, 4: 4 },
  }[factoryInputTier] ?? {};
  if (factoryInputTier === 1) {
    document.querySelector(".comparison-head p").textContent =
      `Rates are editable per operation. Defaults (cycles/hour): P1 → P2: ${defaultRates[2]}; P1 → P3: Simple ${defaultRates[3].S}, Complex ${defaultRates[3].C}; P1 → P4: Low ${defaultRates[4].L}, Medium ${defaultRates[4].M}, High ${defaultRates[4].H}.`;
  } else if (factoryInputTier === 2) {
    document.querySelector(".comparison-head p").textContent =
      `Rates are editable per operation. Defaults: ${defaultRates[3]} cycles/hour for P2 → P3 and ${defaultRates[4]} for P2 → P4.`;
  }
  const counts = [];
  for (const group of document.querySelectorAll("[data-factory-output-tier]")) {
    const tier = Number(group.dataset.factoryOutputTier);
    const routeRate = defaultRates[tier];
    const products = Object.entries(piSnapshot)
      .filter(([, product]) => product.tier === tier)
      .sort(([, a], [, b]) => collator.compare(a.name, b.name));
    for (const [typeId, product] of products) {
      const rows = factoryRecipe.content.cloneNode(true);
      rows.querySelector("[data-operation]").dataset.typeId = typeId;
      const rate = rows.querySelector(".cycle-rate");
      rate.defaultValue = String((typeof routeRate === "number" ? routeRate : routeRate?.[outputCategory(product)]) ?? 1);
      rate.setAttribute("aria-label", `Completed cycles per hour for ${product.name}`);
      rows.querySelector(".operation-id").textContent = `p${factoryInputTier}-p${tier}-${typeId}`;
      rows.querySelector(".recipe-quantities").textContent = product.inputs.map(([input, quantity]) =>
        `${quantity} ${piSnapshot[input].name}`).join(" + ") + ` → ${product.output} ${product.name}`;
      group.append(rows);
    }
    counts.push(`${products.length} P${tier}`);
  }
  document.getElementById("factory-output-count").textContent = counts.join(" · ") + " outputs";
}

if (operationsTableWrap) {
  const columnHeader = operationsTableWrap.querySelector(":scope > table > thead");
  new ResizeObserver(() => {
    operationsTableWrap.style.setProperty("--column-header-height", `${columnHeader.getBoundingClientRect().height}px`);
  }).observe(columnHeader);
}

const setRatesDialog = document.getElementById("set-rates-dialog");
if (setRatesDialog) {
  const fields = document.getElementById("bulk-cycle-rates");
  const categoriesByTier = {
    3: [["S", "Simple"], ["C", "Complex"]],
    4: [["L", "Low"], ["M", "Medium"], ["H", "High"]],
  };
  let rateChanges = [];
  for (const group of operationsTableWrap.querySelectorAll(":scope > table > tbody")) {
    const heading = group.querySelector(".operation-group th span");
    const route = heading.textContent;
    const categories = categoriesByTier[group.dataset.factoryOutputTier];
    const rows = [...group.querySelectorAll("[data-operation]")];
    const button = document.createElement("button");
    button.type = "button";
    button.className = "set-section-rate";
    button.textContent = "Set cycles/hour";
    button.setAttribute("aria-label", `Set cycles/hour for ${route}`);
    button.setAttribute("aria-haspopup", "dialog");
    button.addEventListener("click", () => {
      fields.replaceChildren();
      rateChanges = (categories ?? [[null, null]]).map(([code, name], index) => {
        const rates = rows.filter(row => !code || outputCategory(piSnapshot[row.dataset.typeId]) === code)
          .map(row => row.querySelector(".cycle-rate"));
        const label = document.createElement("label");
        label.textContent = name ? `${name} (${code}) cycles/hour` : "Completed cycles/hour";
        const input = document.createElement("input");
        input.type = "number";
        input.min = "0";
        input.step = "any";
        input.required = !categories;
        input.autofocus = index === 0;
        const current = rates[0]?.value ?? "";
        const mixed = rates.some(rate => rate.value !== current);
        input.value = mixed ? "" : current;
        if (mixed) input.placeholder = "Mixed rates";
        label.append(input);
        fields.append(label);
        return { input, rates };
      });
      setRatesDialog.querySelector("h2").textContent = `Set cycles/hour for ${route}`;
      document.getElementById("set-rates-help").textContent = categories
        ? "Apply rates by category. Leave a field blank to keep that category unchanged."
        : "Apply this rate to every operation in this section.";
      setRatesDialog.showModal();
    });
    heading.append(button);
  }
  setRatesDialog.querySelector("form").addEventListener("submit", event => {
    if (event.submitter?.value !== "apply") return;
    for (const { input, rates } of rateChanges) {
      if (input.value === "") continue;
      for (const rate of rates) {
        rate.value = input.value;
        rate.dispatchEvent(new Event("input"));
      }
    }
  });
}

if (extractionPage && carriedExtraction.has("tax")) taxInput.value = carriedExtraction.get("tax");
const factoryState = factoryRecipe ? carriedFactory[factoryInputTier] : null;
if (factoryState?.has("tax")) taxInput.value = factoryState.get("tax");
const carryPrices = () => {
  const states = {
    extraction: pageParams.get("extraction"),
    "p1-inputs": pageParams.get("p1-inputs"),
    "p2-inputs": pageParams.get("p2-inputs"),
    "p3-inputs": pageParams.get("p3-inputs"),
    "buy-build-tax": pageParams.get("buy-build-tax"),
    "p4-buy-overrides": pageParams.get("p4-buy-overrides"),
  };
  if (extractionPage || factoryState) {
    const state = new URLSearchParams({ tax: taxInput.value });
    for (const [id, select] of materialSelectors) {
      if (!select.selectedOptions[0].defaultSelected)
        state.set(`source-${id}`, select.value);
    }
    for (const [id, select] of localAssignments) {
      if (select.selectedIndex !== 0) state.set(`local-${id}`, select.value);
    }
    states[extractionPage ? "extraction" : `p${factoryInputTier}-inputs`] = state.toString();
  }
  for (const link of document.querySelectorAll(".nav a:not([aria-current])")) {
    const url = new URL(link.href);
    for (const [key, state] of Object.entries(states)) {
      if (state !== null) url.searchParams.set(key, state);
    }
    link.href = url.href;
  }
};

for (const row of document.querySelectorAll("[data-operation]")) {
  const rate = row.querySelector(".cycle-rate");
  const units = row.querySelector(".units-hour");
  const margin = row.querySelector(".profit-margin");
  const profit = row.querySelector(".profit-hour");
  const details = row.nextElementSibling;
  const disclosure = row.querySelector(".operation-name");
  const operationId = row.querySelector(".operation-id") ?? details.querySelector(".operation-id");
  details.id = `details-${operationId.textContent}`;
  disclosure.setAttribute("aria-controls", details.id);
  disclosure.addEventListener("click", () => {
    details.hidden = !details.hidden;
    disclosure.setAttribute("aria-expanded", String(!details.hidden));
  });
  const daily = details?.querySelector(".profit-day");
  const monthly = row.querySelector(".profit-30days");
  const status = row.querySelector(".rate-status");
  const id = Number(row.dataset.typeId);
  const product = piSnapshot[id];
  const route = row.dataset.extractionRoute;
  const outputPerCycle = product.output;
  const category = outputCategory(product);
  disclosure.textContent = category ? `${product.name} (${category})` : product.name;
  row.cells[1].textContent = outputPerCycle;
  const costCard = details.querySelector(".cycle-costs") ?? details.querySelector(".detail-card");
  const imports = route ? null : factoryImports(id, factoryInputTier);
  const supplemental = factoryInputTier > 1 && imports
    ? imports.filter(([input]) => piSnapshot[input].tier === 1) : [];
  if (imports) {
    const line = details.querySelector(".imported-materials");
    const describeImports = (tier, materials) => {
      const quantities = document.createElement("strong");
      quantities.textContent = materials.map(([input, quantity]) =>
        `${format(quantity)} ${piSnapshot[input].name}`).join("; ");
      return [`Imported P${tier} per output cycle: `, quantities];
    };
    line.replaceChildren(...describeImports(factoryInputTier,
      imports.filter(([input]) => piSnapshot[input].tier === factoryInputTier)));
    if (supplemental.length) {
      const extra = document.createElement("p");
      extra.append(...describeImports(1, supplemental));
      line.after(extra);
    }
  }
  for (const key of ["acquisition", "importTax", ...(supplemental.length ? ["supplementalTax"] : []), "exportTax"]) {
    const line = document.createElement("p");
    line.dataset.cost = key;
    costCard.append(line);
  }

  const update = () => {
    const tax = parseTax(taxInput.value);
    const costs = route ? extractionCost(route, id) : factoryCost(id, imports, tax, selectedCost);
    const supplementalTax = tax === null ? null : supplemental.reduce((total, [input, quantity]) =>
      total + inputImportTax(input, quantity, tax), 0);
    const sale = quote(id, saleSource.value);
    row.cells[4].textContent = unitValue(costs.unit);
    row.cells[5].textContent = unitValue(sale);
    const profitPerUnit = costs.unit === null || sale === null ? null : sale - costs.unit;
    const marginPercent = profitPerUnit !== null && sale > 0 ? 100 * profitPerUnit / sale : null;
    margin.textContent = marginPercent === null ? "—" : `${format(marginPercent)}%`;
    margin.classList.toggle("positive", marginPercent !== null && marginPercent > 0);
    margin.classList.toggle("negative", marginPercent !== null && marginPercent < 0);
    const costLabels = {
      acquisition: route ? "Materials and upstream costs" : supplemental.length
        ? `Imported P${factoryInputTier} and P1 material cost` : `Imported P${factoryInputTier} material cost`,
      importTax: route ? "Final-stage import tax" : `Total P${factoryInputTier} import tax`,
      supplementalTax: "Total P1 import tax",
      exportTax: "Final-stage export tax",
    };
    for (const [key, label] of Object.entries(costLabels)) {
      const field = details.querySelector(`[data-cost="${key}"]`);
      const amount = key === "supplementalTax" ? supplementalTax
        : key === "importTax" && costs.importTax !== null ? costs.importTax - supplementalTax : costs[key];
      if (field) field.textContent = `${label}: ${unitValue(amount)} per cycle`;
    }
    const cyclesPerHour = Number(rate.value);
    const valid =
      rate.value.trim() !== "" &&
      Number.isFinite(cyclesPerHour) &&
      cyclesPerHour >= 0;
    rate.setAttribute("aria-invalid", String(!valid));
    status.textContent = valid ? "" : "Enter a finite rate of 0 or more.";
    units.textContent = valid ? format(outputPerCycle * cyclesPerHour) : "—";
    for (const target of [profit, daily, monthly]) {
      target.textContent = "—";
      target.classList.remove("positive", "negative");
    }
    if (!valid) return;
    if (profitPerUnit === null) return;
    const profitPerHour = outputPerCycle * cyclesPerHour * profitPerUnit;
    profit.textContent = `${profitPerHour < 0 ? "−" : "+"}${format(Math.abs(profitPerHour))} ISK`;
    daily.textContent = `${profitPerHour < 0 ? "−" : "+"}${format(Math.abs(profitPerHour * 24))} ISK`;
    monthly.textContent = `${profitPerHour < 0 ? "−" : "+"}${format(Math.abs(profitPerHour * 24 * 30))} ISK`;

    for (const target of [profit, daily, monthly].filter(Boolean)) {
      target.classList.toggle("positive", profitPerHour >= 0);
      target.classList.toggle("negative", profitPerHour < 0);
    }
  };

  rate.addEventListener("input", update);
  document.addEventListener("pi-prices-change", update);
}

const updatePrices = () => {
  const validTax = parseTax(taxInput.value) !== null;
  taxInput.setAttribute("aria-invalid", String(!validTax));
  document.getElementById("tax-status").textContent = validTax ? "" : "Enter a customs tax between 0% and 100%.";
  document.dispatchEvent(new Event("pi-prices-change"));
  carryPrices();
};
document.addEventListener("change", event => {
  if (event.target.matches("select") && event.target !== bulkInputSource) updatePrices();
});
taxInput.addEventListener("input", updatePrices);
updatePrices();
}
