document.title = "Factory Planner | Eve Argus";

// CPU, powergrid, and ISK from the workbook's PI Buildings sheet.
const facilities = [
  [110, 550, 0], [400, 2600, 45000], [500, 700, 250000],
  [200, 800, 75000], [500, 700, 250000], [3600, 700, 900000],
  [1100, 400, 425000],
];
const centers = [
  [1675, 6000, 75000], [7057, 9000, 580000], [12136, 12000, 1510000],
  [17215, 15000, 2710000], [21315, 17000, 4210000], [25415, 19000, 6310000],
];
const formatBudget = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const displayBudget = value => value == null ? "—" : formatBudget.format(value);

for (const layout of document.querySelectorAll("[data-layout]")) {
  const rows = [...layout.querySelectorAll("[data-building]")];
  const radius = layout.querySelector('[name="radius"]');
  const distance = layout.querySelector('[name="distance"]');
  const center = layout.querySelector('[name="center"]');
  const counts = rows.map(row => row.querySelector("input"));
  const minimumRow = layout.querySelector('[data-link="minimum"]');
  const extraRow = layout.querySelector('[data-link="extra"]');
  const status = layout.querySelector('[role="status"]');
  const values = [...layout.querySelectorAll("[data-value]")];
  const numbers = [radius, distance, ...counts];
  const writeRow = (row, [cpu, grid, cost]) => {
    row.querySelector("[data-cpu]").textContent = displayBudget(cpu);
    row.querySelector("[data-grid]").textContent = displayBudget(grid);
    const costCell = row.querySelector("[data-cost]");
    if (costCell) costCell.textContent = displayBudget(cost);
  };
  const update = () => {
    const invalid = numbers.filter(input => !input.validity.valid ||
      !Number.isFinite(input.valueAsNumber) ||
      (input === radius && input.valueAsNumber <= 0) ||
      (counts.includes(input) && !Number.isSafeInteger(input.valueAsNumber)));
    for (const input of numbers) input.setAttribute("aria-invalid", String(invalid.includes(input)));
    const valid = invalid.length === 0;
    const minimum = valid ? radius.valueAsNumber * 0.012008576 : null;
    const linkCount = valid ? counts.slice(1).reduce((sum, input) => sum + input.valueAsNumber, 0) : null;
    const extraLength = distance.valueAsNumber;
    const extraCount = valid ? Number(extraLength > 0) : null;
    const minimumCpu = valid ? linkCount * (15 + 0.2 * minimum) : null;
    const minimumGrid = valid ? linkCount * (10 + 0.15 * minimum) : null;
    const extraCpu = valid ? (extraCount ? 15 + 0.2 * extraLength : 0) : null;
    const extraGrid = valid ? (extraCount ? 10 + 0.15 * extraLength : 0) : null;
    minimumRow.querySelector("[data-count]").textContent = displayBudget(linkCount);
    extraRow.querySelector("[data-count]").textContent = displayBudget(extraCount);
    writeRow(minimumRow, [minimumCpu, minimumGrid]);
    writeRow(extraRow, [extraCpu, extraGrid]);
    let cpuUsed = minimumCpu + extraCpu;
    let gridUsed = minimumGrid + extraGrid;
    const [cpuCapacity, gridCapacity, centerCost] = centers[Number(center.value)];
    let totalCost = centerCost;
    rows.forEach((row, index) => {
      const costs = facilities[index].map(value => value * counts[index].valueAsNumber);
      writeRow(row, valid ? costs : [null, null, null]);
      cpuUsed += costs[0];
      gridUsed += costs[1];
      totalCost += costs[2];
    });
    const cpuRemaining = cpuCapacity - cpuUsed;
    const gridRemaining = gridCapacity - gridUsed;
    const totals = {
      circumference: 2 * Math.PI * radius.valueAsNumber,
      minimum, cpuUsed, gridUsed, cpuCapacity, gridCapacity, centerCost,
      cpuRemaining, gridRemaining, totalCost,
    };
    const withinRange = valid && Object.values(totals).every(Number.isFinite);
    for (const cell of values) {
      const key = cell.dataset.value;
      cell.textContent = displayBudget(withinRange ? totals[key] : null);
      cell.classList.toggle("negative", withinRange &&
        (key === "cpuRemaining" || key === "gridRemaining") && totals[key] < 0);
    }
    const exceeded = [cpuRemaining < 0 ? "CPU" : "", gridRemaining < 0 ? "powergrid" : ""].filter(Boolean);
    status.textContent = !valid ? "Enter a positive radius, nonnegative extra distance, and whole nonnegative facility counts."
      : !withinRange ? "The budget is outside the supported numeric range."
      : exceeded.length ? `Over budget: ${exceeded.join(" and ")}.` : "Within CPU and powergrid budgets.";
  };
  layout.addEventListener("input", update);
  update();
}

carryScenario();
