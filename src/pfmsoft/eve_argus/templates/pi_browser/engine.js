(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory;
  else root.PIEngine = factory(root.Decimal);
})(globalThis, function (Decimal) {
  "use strict";
  const D = Decimal.clone({ precision: 28, rounding: Decimal.ROUND_HALF_EVEN });
  const bases = ["jita-buy-5", "jita-sell-5", "the-forge-history-10d"];
  const fields = ["buy", "sell", "history"];

  function nonnegative(text, label) {
    let value;
    try { value = new D(text); }
    catch (error) { throw new Error(`${label} must be a decimal number: ${error.message}`); }
    if (!value.isFinite() || value.isNegative()) {
      throw new Error(`${label} must be finite and nonnegative.`);
    }
    return value;
  }

  function create(payload) {
    const materials = new Map(payload.inputs.materials.map(row => [row.material.type_id, row]));
    const mining = new Set(payload.mining_type_ids);
    const ordered = [...materials.values()].sort((a, b) =>
      a.material.tier - b.material.tier || a.material.type_id - b.material.type_id);
    function initialState() {
      return {
        taxRate: payload.tax_rate, marketBasis: bases[1], valuationBasis: bases[1],
        intermediateBoundary: payload.intermediate_boundary, preset: "market",
        choices: {}, cycles: {}
      };
    }
    function choicesFor(typeId) {
      const tier = materials.get(typeId).material.tier;
      const choices = [{ value: "market", label: "Market input basis" }];
      if (mining.has(typeId)) choices.push({ value: "mined", label: `Freely mined with P${tier} result (exported)` });
      for (let start = 0; start < tier; start++) {
        if (start !== 0 || tier === 1) choices.push({ value: `from-${start}`, label: `Manufacture from P${start} (exported)` });
      }
      return choices;
    }
    function calculate(state) {
      const rate = nonnegative(state.taxRate, "Customs tax rate");
      if (rate.gt(1)) throw new Error("Customs tax rate must be at most 100%.");
      if (!bases.includes(state.marketBasis) || !bases.includes(state.valuationBasis)) throw new Error("Unknown market-price basis.");
      if (!["on-planet", "off-planet"].includes(state.intermediateBoundary)) throw new Error("Invalid intermediate boundary.");
      if (!["market", "profitable-p2"].includes(state.preset)) throw new Error("Unknown scenario preset.");
      for (const [id, choice] of Object.entries(state.choices)) {
        if (!materials.has(Number(id)) || !choicesFor(Number(id)).some(c => c.value === choice)) {
          throw new Error(`Invalid source selection for material ${id}.`);
        }
      }
      const sources = new Map(), productions = new Map(), notices = [];
      const purchase = row => market(row, state.marketBasis);
      function market(row, basis) {
        const quote = row[fields[bases.indexOf(basis)]];
        return {
          typeId: row.material.type_id,
          unitCost: quote.unit_cost === null ? null : nonnegative(quote.unit_cost, "Market price"),
          boundary: "off-planet", kind: "market", label: quote.label,
          reason: quote.unavailable_reason
        };
      }
      function source(typeId) {
        if (sources.has(typeId)) return sources.get(typeId);
        const row = materials.get(typeId), material = row.material;
        let choice = state.choices[typeId], selected;
        if (!choice && state.preset === "profitable-p2" && material.tier === 2) {
          const made = route(typeId, 1, true), sale = market(row, state.valuationBasis);
          if (made.unitCost === null || sale.unitCost === null) {
            notices.push(`Profitability unavailable for ${material.name}; using its market purchase quote.`);
          }
          choice = made.unitCost !== null && sale.unitCost !== null && sale.unitCost.gt(made.unitCost) ? "from-1" : "market";
        }
        choice = choice || "market";
        if (choice === "market") selected = purchase(row);
        else if (choice === "mined") selected = {
          typeId, unitCost: new D(material.taxable_base).mul(rate),
          boundary: "off-planet", kind: "mined", label: `Freely mined P${material.tier} result (exported)`, reason: null
        };
        else {
          const made = route(typeId, Number(choice.slice(5)), true);
          selected = {
            typeId, unitCost: made.unitCost, boundary: "off-planet", kind: choice,
            label: `Manufactured from P${choice.slice(5)} (exported)`,
            reason: made.reason, stage: made
          };
        }
        sources.set(typeId, selected);
        return selected;
      }
      function route(typeId, start, exported) {
        const key = `${typeId}:${start}:${exported}`;
        if (productions.has(key)) return productions.get(key);
        const material = materials.get(typeId).material;
        let acquisition = new D(0), imports = new D(0);
        const children = [], missing = [];
        for (const item of material.inputs) {
          const ingredient = materials.get(item.type_id).material;
          const child = ingredient.tier <= start ? source(item.type_id) :
            route(item.type_id, start, state.intermediateBoundary === "off-planet");
          const charge = child.boundary === "off-planet" ?
            new D(item.quantity).mul(ingredient.taxable_base).mul(rate).div(2) : new D(0);
          if (child.unitCost === null) missing.push(`${ingredient.name}: ${child.reason}`);
          else acquisition = acquisition.add(new D(item.quantity).mul(child.unitCost));
          imports = imports.add(charge);
          children.push({ quantity: item.quantity, importTax: charge, source: child });
        }
        const exports = exported ? new D(material.output_quantity).mul(material.taxable_base).mul(rate) : new D(0);
        const total = missing.length ? null : acquisition.add(imports).add(exports);
        const result = {
          typeId, boundary: exported ? "off-planet" : "on-planet",
          label: `${material.name} from P${start}`, kind: `from-${start}`,
          unitCost: total === null ? null : total.div(material.output_quantity),
          acquisition: missing.length ? null : acquisition, imports, exports,
          total, children, reason: missing.length ? missing.join("; ") : null
        };
        productions.set(key, result);
        return result;
      }
      for (const row of ordered) source(row.material.type_id);
      const rows = [];
      for (let start = 0; start < 4; start++) {
        for (const row of ordered) {
          const material = row.material;
          if (material.tier <= start || (start === 0 && material.tier !== 1)) continue;
          const key = `from-${start}:${material.type_id}`;
          const root = route(material.type_id, start, true);
          const sale = market(row, state.valuationBasis);
          const profit = root.unitCost === null || sale.unitCost === null ? null : sale.unitCost.sub(root.unitCost);
          const cycles = nonnegative(state.cycles[key] ?? "1", "Factory cycles");
          const units = cycles.mul(material.output_quantity);
          const hourly = profit === null ? null : profit.mul(units);
          rows.push({
            key, typeId: material.type_id, name: material.name, startingTier: start,
            tier: material.tier, root, cost: root.unitCost, sale: sale.unitCost, profit,
            cycles, unitsPerHour: units, profitPerHour: hourly,
            profitPerDay: hourly === null ? null : hourly.mul(24),
            profitPer30Days: hourly === null ? null : hourly.mul(24).mul(30)
          });
        }
      }
      return { rows, sources, notices, state: { ...state } };
    }
    function exportPrices(result, selections) {
      const prices = {};
      for (const [id, key] of Object.entries(selections)) {
        const typeId = Number(id);
        const quote = key === `source:${id}` ? result.sources.get(typeId) :
          result.rows.find(row => row.key === key && row.typeId === typeId)?.root;
        if (!quote || quote.unitCost === null) throw new Error(`Selected price for type ${id} is unavailable; change or remove that selection.`);
        prices[id] = quote.unitCost.toFixed();
      }
      return {
        prices,
        description: "Selected EVE Argus PI off-planet unit costs in ISK; sales tax and transport excluded.",
        assumptions: {
          tax_rate: result.state.taxRate, market_basis: result.state.marketBasis,
          valuation_basis: result.state.valuationBasis,
          intermediate_boundary: result.state.intermediateBoundary,
          preset: result.state.preset, source_overrides: { ...result.state.choices },
          selected_quotes: { ...selections }
        },
        source: {
          generated_at: payload.inputs.generated_at, hub: payload.inputs.hub,
          orders: payload.inputs.response, history_window: payload.inputs.history_window
        }
      };
    }
    return { materials, initialState, choicesFor, calculate, exportPrices };
  }
  return { create };
});
