const format = value =>
  new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    .format(value);
const unitValue = value => value === null ? "—" : `${format(value)} ISK`;
const collator = new Intl.Collator("en", { sensitivity: "base" });
const quote = (id, source) => {
  const value = piSnapshot[id].prices[source];
  return value == null ? null : Number(value);
};
const parseTax = value => value !== null && value.trim() !== "" &&
  Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= 100
  ? Number(value) / 100 : null;
const inputImportTax = (id, quantity, tax) => quantity * Number(piSnapshot[id].taxBase) * tax / 2;

function costStage(product, inputs, tax, exportOutput) {
  const acquisition = inputs.some(input => input.cost === null)
    ? null : inputs.reduce((total, input) => total + input.quantity * input.cost, 0);
  const importTax = tax === null ? null : inputs.reduce((total, input) =>
    total + (input.imported ? inputImportTax(input.id, input.quantity, tax) : 0), 0);
  const exportTax = tax === null ? null : exportOutput ? product.output * Number(product.taxBase) * tax : 0;
  return {
    acquisition, importTax, exportTax,
    unit: acquisition === null || tax === null ? null : (acquisition + importTax + exportTax) / product.output,
  };
}

function factoryCost(id, imports, tax, inputCost) {
  return costStage(piSnapshot[id], imports.map(([input, quantity]) => ({
    id: input, quantity, imported: true, cost: inputCost(input),
  })), tax, true);
}

function factoryImports(id, startingTier) {
  const imports = new Map();
  function collect(typeId, quantity) {
    const material = piSnapshot[typeId];
    if (material.tier <= startingTier) {
      imports.set(typeId, (imports.get(typeId) ?? 0) + quantity);
    } else {
      for (const [ingredient, amount] of material.inputs) {
        collect(ingredient, quantity * amount / material.output);
      }
    }
  }
  collect(id, piSnapshot[id].output);
  return [...imports].sort(([a], [b]) => collator.compare(piSnapshot[a].name, piSnapshot[b].name));
}
