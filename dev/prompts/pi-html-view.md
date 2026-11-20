# Planetary Interaction Operations View

This is a design plan for a PI operations view, used alongside but developed
separately from the CLI-generated **What PI to build** browser described in
[planetary_interaction.md](./planetary_interaction.md). The two tools work with
overlapping PI materials and operations, so calculation/catalog code may be
reused after its semantics are checked. Do not treat this view as a redesign,
replacement, or required extension of the existing browser.

The view is intended to help a player compare planned planet operations,
understand input and customs costs, estimate output at a chosen factory rate,
and carry calculated unit costs into downstream operations.

## Confirmed decisions

- Develop this as a separate view/application track.
- Start the visual exploration with two pages sharing a navigation shell:
  **Extraction** and **P1 Inputs**.
- Each operation has an editable **Completed cycles/hour** rate. On Extraction,
  default to `6` for P0-P1 and `3` for both P0-P1-P2 routes; other operations
  default to `1`. The user can change the rate to match their intended factory plan.
  Do not calculate or impose a fixed facility-capacity rate on their behalf.
- Rate-based output is `units per recipe cycle * completed cycles/hour`.
  Changing the rate changes time-based quantities and totals, not the
  operation's normalized unit cost.
- Use archived market data in the HTML mockups. They are design artifacts, not
  production output and must not imply that archived prices or calculations are
  live or validated.

## Separate product scope and possible code reuse

The existing browser answers scenario questions about unit costs, route choices,
sales valuations, and selective price export. This operations view has its own
navigation, page organization, and interaction needs, including per-operation
factory rates and loadout details.

Candidate reusable code is in the PI catalog, models, and cost calculations,
including:

- [PI costing](../../src/pfmsoft/eve_argus/pi/costing.py)
- [PI models](../../src/pfmsoft/eve_argus/pi/models.py)
- [PI browser collection](../../src/pfmsoft/eve_argus/reports/pi_browser.py)

Reuse is optional and should follow a behavior comparison. Keep this view's
presentation and page state independent; do not make mockups import or depend on
the production browser's scripts or templates.

## First mockup deliverables

The static pages live in [`dev/tmp/pi-view/`](../tmp/pi-view/):

- [Extraction](../tmp/pi-view/extraction.html) — P0-to-P1 and extraction-led
  routes, with P0/P1 source choices. This is the view reviewed most closely.
- [P1 Inputs](../tmp/pi-view/p1-inputs.html) — routes that use imported P1
  materials to produce P2, P3, or P4, with P1 source choices and one operation
  per catalog output.
- [P2 Inputs](../tmp/pi-view/p1-inputs.html?view=p2) — P2-starting routes
  for all P3 and P4 outputs, with direct P1 imports where the recipe requires them.
- [P3 Inputs](../tmp/pi-view/p1-inputs.html?view=p3) — all eight P4 outputs
  made from imported P3 and, where required, a direct P1 ingredient.
- [Market Prices](../tmp/pi-view/market.html) — saved Jita system and
  The Forge region order prices for P0–P4, including buy and sell 5% depth
  prices, order counts, and unit counts. Show the Summary Name on each row.
  The selector offers Jita system (default), The Forge region, or All; All
  keeps separate rows and metadata for each summary. No search box or pagination.
- [Market History](../tmp/pi-view/market.html?view=history) — saved
  The Forge history for P0–P4, including per-type windows, missing days,
  weighted prices, volume, order counts, and freshness. Show the region
  name on each row. Use a Region dropdown that defaults to All regions
  and lists the regions in the archive (currently The Forge only). Show
  all matching rows without pagination.
- The market views match report rows to the PI catalog by type ID and keep
  all report fields and metadata. Sort rows by market group name, then
  alphabetically by material name within the group. Put Market Path IDs and
  Market Path Names last. Display prices as ISK with two decimal places and
  comma separators. Group other numeric values with commas without rounding
  their fractional digits or reformatting identifiers. The pages open directly
  from disk with no network requests.

Use a shared left-side material/source pane and a central operation comparison
area as the first layout experiment. Keep the table readable: show the
decision-critical columns first and place detailed cost/tax/loadout fields in an
expandable operation detail area rather than forcing every metric into one
always-visible wide table.

Input and sale quote selections use the archive, and operation costs and
profit/loss recalculate when their inputs change. The prototype uses catalog
tax bases, half the configured rate for imports, and the full rate for final
exports. P1-starting operations import only P1, including P1 consumed by
locally made P2 and P3 intermediates. No intermediate crosses customs.
Navigation carries Extraction's pricing
assumptions by URL; opening another page directly uses the defaults.
These are prototype rules, not a validated production accounting model.
P1 Inputs and the market pages remain provisional; refine cross-page and
transition behavior during development. Market refresh, durable settings,
export, and clipboard actions are not implemented.

## Archived PI market snapshot

Use this fixed snapshot from the November 2, 2026 eve-argus dev reports
as market data for prototype scenarios and repeatable checks. These are
historical market observations, not current quotes. Both operation mockups
use the PI subset below. The market pages show only catalog P0–P4 rows,
including [The Forge regional order summary](../tmp/reports/price-summaries/price-summary-The_Forge-2026-11-02T13_28_47_803527803Z.json)
in addition to the Jita order and The Forge history reports.

- **Jita Buy 5% / Sell 5%** come from `buy_summary.five_price` and
  `sell_summary.five_price` in the [Jita system price summary](../tmp/reports/price-summaries/price-summary-Jita-2026-11-02T13_28_47_803527803Z.json)
  (system `30000142`). Orders were received at `2026-11-02T13:28:47.803527803Z`
  and expired at `2026-11-02T13:31:32Z`; the report was generated at
  `2026-11-02T15:05:25.936874944Z` and marked the snapshot stale. This is
  system-scoped, not a station-only quote.
- **The Forge Avg** is the volume-weighted `average_price` from the
  [The Forge 10-day history summary](../tmp/reports/history-summaries/history-summary-The_Forge-10d-latest-2026-11-02T19_13_25_639617683Z.json)
  (region `10000002`), generated at `2026-11-02T19:13:25.639617683Z`.
  The report uses a separate window for each type; the last column shows
  each row's `newest_date`, not the report generation date. The source
  report contains the per-type oldest date, missing days, and expiry.

Join by EVE type ID. All prices are ISK per unit. `—` means the source
did not provide a value; do not substitute zero or a different quote.

| Tier | Type ID | Material | Jita Buy 5% | Jita Sell 5% | The Forge Avg | Forge window end |
|---|---:|---|---:|---:|---:|---|
| P0 | 2268 | Aqueous Liquids | 1.92 | 2.79 | 2.36 | 2026-10-26 |
| P0 | 2305 | Autotrophs | 3.61 | 4.70 | 4.12 | 2026-10-26 |
| P0 | 2267 | Base Metals | 2.19 | 3.00 | 2.96 | 2026-10-26 |
| P0 | 2288 | Carbon Compounds | 1.00 | 1.61 | 1.42 | 2026-10-26 |
| P0 | 2287 | Complex Organisms | 4.42 | 5.97 | 4.79 | 2026-10-26 |
| P0 | 2307 | Felsic Magma | 5.50 | 14.89 | 7.36 | 2026-10-26 |
| P0 | 2272 | Heavy Metals | 2.76 | 4.35 | 4.16 | 2026-10-26 |
| P0 | 2309 | Ionic Solutions | 3.56 | 4.99 | 4.28 | 2026-10-26 |
| P0 | 2073 | Microorganisms | 2.02 | 2.39 | 2.15 | 2026-10-26 |
| P0 | 2310 | Noble Gas | 1.56 | 2.83 | 2.24 | 2026-10-26 |
| P0 | 2270 | Noble Metals | 4.10 | 4.93 | 4.42 | 2026-10-26 |
| P0 | 2306 | Non-CS Crystals | 4.10 | 5.49 | 4.32 | 2026-10-26 |
| P0 | 2286 | Planktic Colonies | 3.65 | 5.20 | 4.62 | 2026-10-26 |
| P0 | 2311 | Reactive Gas | 3.38 | 4.85 | 4.58 | 2026-10-26 |
| P0 | 2308 | Suspended Plasma | 3.02 | 3.53 | 3.19 | 2026-10-26 |
| P1 | 2393 | Bacteria | 395.00 | 419.40 | 405.01 | 2026-10-26 |
| P1 | 2396 | Biofuels | 356.90 | 388.50 | 359.01 | 2026-10-26 |
| P1 | 3779 | Biomass | 821.20 | 897.50 | 853.61 | 2026-11-02 |
| P1 | 2401 | Chiral Structures | 690.00 | 751.00 | 703.70 | 2026-11-02 |
| P1 | 2390 | Electrolytes | 511.00 | 546.90 | 527.66 | 2026-10-26 |
| P1 | 2397 | Industrial Fibers | 678.50 | 758.00 | 715.03 | 2026-10-26 |
| P1 | 2392 | Oxidizing Compound | 693.60 | 724.00 | 738.64 | 2026-10-26 |
| P1 | 3683 | Oxygen | 421.00 | 452.60 | 430.60 | 2026-11-02 |
| P1 | 2389 | Plasmoids | 546.20 | 650.00 | 553.21 | 2026-10-26 |
| P1 | 2399 | Precious Metals | 780.50 | 838.40 | 777.07 | 2026-10-26 |
| P1 | 2395 | Proteins | 820.10 | 894.00 | 855.04 | 2026-10-26 |
| P1 | 2398 | Reactive Metals | 400.10 | 431.40 | 407.74 | 2026-10-26 |
| P1 | 9828 | Silicon | 804.40 | 950.00 | 886.01 | 2026-10-26 |
| P1 | 2400 | Toxic Metals | 483.50 | 514.00 | 483.68 | 2026-10-26 |
| P1 | 3645 | Water | 447.70 | 515.00 | 471.63 | 2026-11-02 |
| P2 | 2329 | Biocells | 8961.00 | 10200.00 | 9710.63 | 2026-11-02 |
| P2 | 3828 | Construction Blocks | 9709.00 | 10290.00 | 10174.90 | 2026-11-02 |
| P2 | 9836 | Consumer Electronics | 9651.00 | 10580.00 | 10490.74 | 2026-11-02 |
| P2 | 9832 | Coolant | 10930.00 | 11460.00 | 11259.96 | 2026-11-02 |
| P2 | 44 | Enriched Uranium | 14000.00 | 14250.00 | 14264.92 | 2026-11-02 |
| P2 | 3693 | Fertilizer | 11240.00 | 12180.00 | 11011.93 | 2026-10-26 |
| P2 | 15317 | Genetically Enhanced Livestock | 11280.00 | 11700.00 | 11618.62 | 2026-10-26 |
| P2 | 3725 | Livestock | 12620.00 | 13690.00 | 10964.09 | 2026-10-26 |
| P2 | 3689 | Mechanical Parts | 9500.00 | 10360.00 | 10224.75 | 2026-11-02 |
| P2 | 2327 | Microfiber Shielding | 15870.00 | 17440.00 | 14941.48 | 2026-10-26 |
| P2 | 9842 | Miniature Electronics | 11590.00 | 12800.00 | 13062.70 | 2026-11-02 |
| P2 | 2463 | Nanites | 7302.00 | 7985.00 | 7711.50 | 2026-11-02 |
| P2 | 2317 | Oxides | 9540.00 | 10360.00 | 10025.91 | 2026-10-26 |
| P2 | 2321 | Polyaramids | 14560.00 | 17300.00 | 16344.38 | 2026-10-26 |
| P2 | 3695 | Polytextiles | 8328.00 | 10970.00 | 8039.00 | 2026-10-26 |
| P2 | 9830 | Rocket Fuel | 11980.00 | 12440.00 | 12092.95 | 2026-11-02 |
| P2 | 3697 | Silicate Glass | 13460.00 | 14370.00 | 14046.08 | 2026-10-26 |
| P2 | 9838 | Superconductors | 10500.00 | 11980.00 | 11644.46 | 2026-11-02 |
| P2 | 2312 | Supertensile Plastics | 12920.00 | 13670.00 | 13333.74 | 2026-11-02 |
| P2 | 3691 | Synthetic Oil | 7165.00 | 7824.00 | 7566.93 | 2026-10-26 |
| P2 | 2319 | Test Cultures | 9525.00 | 10160.00 | 9768.03 | 2026-11-02 |
| P2 | 9840 | Transmitter | 11600.00 | 12280.00 | 12577.16 | 2026-11-02 |
| P2 | 3775 | Viral Agent | 11220.00 | 12300.00 | 12174.43 | 2026-11-02 |
| P2 | 2328 | Water-Cooled CPU | 7350.00 | 7700.00 | 7178.68 | 2026-11-02 |
| P3 | 2358 | Biotech Research Reports | 104600.00 | 111400.00 | 102340.72 | 2026-10-26 |
| P3 | 2345 | Camera Drones | 79000.00 | 81940.00 | 79740.11 | 2026-11-02 |
| P3 | 2344 | Condensates | 60300.00 | 66900.00 | 64123.54 | 2026-10-26 |
| P3 | 2367 | Cryoprotectant Solution | 108000.00 | 117600.00 | 117250.83 | 2026-11-02 |
| P3 | 17392 | Data Chips | 97170.00 | 107500.00 | 100412.85 | 2026-11-02 |
| P3 | 2348 | Gel-Matrix Biopaste | 122700.00 | 134900.00 | 126474.69 | 2026-11-02 |
| P3 | 9834 | Guidance Systems | 81100.00 | 85750.00 | 83916.04 | 2026-11-02 |
| P3 | 2366 | Hazmat Detection Systems | 120000.00 | 149200.00 | 115144.77 | 2026-10-26 |
| P3 | 2361 | Hermetic Membranes | 100700.00 | 123700.00 | 113270.98 | 2026-11-02 |
| P3 | 17898 | High-Tech Transmitters | 97700.00 | — | 102188.33 | 2026-11-02 |
| P3 | 2360 | Industrial Explosives | 73600.00 | 89820.00 | 103235.28 | 2026-10-26 |
| P3 | 2354 | Neocoms | 75000.00 | 87770.00 | 82066.49 | 2026-11-02 |
| P3 | 2352 | Nuclear Reactors | 82160.00 | 87940.00 | 86810.87 | 2026-11-02 |
| P3 | 9846 | Planetary Vehicles | 114000.00 | 123000.00 | 117671.10 | 2026-10-26 |
| P3 | 9848 | Robotics | 83400.00 | 87180.00 | 85574.33 | 2026-11-02 |
| P3 | 2351 | Smartfab Units | 77010.00 | 86300.00 | 82287.67 | 2026-11-02 |
| P3 | 2349 | Supercomputers | 95070.00 | 114900.00 | 112979.29 | 2026-11-02 |
| P3 | 2346 | Synthetic Synapses | 83500.00 | 86760.00 | 86017.21 | 2026-11-02 |
| P3 | 12836 | Transcranial Microcontrollers | 70690.00 | 74280.00 | 74025.98 | 2026-11-02 |
| P3 | 17136 | Ukomi Superconductors | 71580.00 | 82930.00 | 78463.37 | 2026-11-02 |
| P3 | 28974 | Vaccines | 77000.00 | 81990.00 | 85620.37 | 2026-10-26 |
| P4 | 2867 | Broadcast Node | 2001000.00 | 2101000.00 | 2068005.02 | 2026-11-02 |
| P4 | 2868 | Integrity Response Drones | 2667000.00 | 2820000.00 | 2731882.83 | 2026-11-02 |
| P4 | 2869 | Nano-Factory | 1340000.00 | 1399000.00 | 1349133.05 | 2026-11-02 |
| P4 | 2870 | Organic Mortar Applicators | 991700.00 | 1120000.00 | 1082639.91 | 2026-11-02 |
| P4 | 2871 | Recursive Computing Module | 1530000.00 | 1543000.00 | 1543415.58 | 2026-11-02 |
| P4 | 2872 | Self-Harmonizing Power Core | 1818000.00 | 1973000.00 | 2018309.82 | 2026-11-02 |
| P4 | 2875 | Sterile Conduits | 1262000.00 | 1317000.00 | 1285478.63 | 2026-11-02 |
| P4 | 2876 | Wetware Mainframe | 2375000.00 | 2481000.00 | 2339472.48 | 2026-11-02 |

## Navigation roadmap

The intended navigation may eventually include:

- **Extraction** — extraction-led PI work, with limited factory work where
  applicable.
- **P1 Inputs**, **P2 Inputs**, and **P3 Inputs** — operations grouped by
  starting input tier.
- **Exported Costs** — selected unit costs available for downstream use.
- **Factory Planner** — possible PI building combinations by Control Center
  level.
- **Extraction Planner**
- **Market Prices**
- **Market History**
- **PI Stats**
- **Factory Layouts**

Extraction, P1 Inputs, P2 Inputs, P3 Inputs, Market Prices, and Market History
are active mockup views. Other entries are planned.

## Shared page elements

### Price and tax controls

- Provide one effective customs-tax input and one sales-valuation selector near
  the top of each operation page.
- Initial market price choices are `Jita Sell 5%`, `Jita Buy 5%`, and
  `The Forge Avg`. The latter represents the available Forge history summary;
  show its source window and freshness when real data is connected.
- Begin with Jita. Support for other hubs or user-selected regions/systems is a
  later decision, not a requirement for these mockups.
- Show every material used as an input to the current page's operations in the
  left pane, grouped by PI tier. Sort material names alphabetically within each
  tier and show each material's source selector and unit price.
- Give each tier a **Set all inputs** button that opens a source dropdown
  and Apply/Cancel actions. List only sources valid for every material in that
  tier. Apply updates that tier's selections and recalculates dependent values;
  Cancel leaves selections unchanged.
- Keep each material row compact: show only its name, source dropdown, and
  selected unit value. Size the dropdown text to match the material name and
  use reduced vertical padding. Put supplemental material/source details behind a
  clickable circled-`i` information button that opens a popup. Give the button
  an accessible name and make the popup dismissible.
- Use the full available screen width for the view. In the source pane, keep
  the material name, compact dropdown, selected value, and information button
  on one line. Reflow the pane for narrow screens rather than constraining the
  desktop layout to a narrow centered column.
- On wide screens, provide a draggable vertical divider to adjust the
  input-material pane's width relative to the operations view. The mockup starts
  at a 25/75 split and allows the source pane to range from 20% to 55%. Support
  pointer/touch dragging and keyboard arrow/Home/End adjustment. Hide the
  divider when the panes stack on narrow screens.
- Provide a Show/Hide input materials button in the operations header. When the
  pane is hidden, the operations view fills the workspace. Showing the pane
  again restores the previous split and material selections.
- For the Extraction page, list all P0 and P1 materials. For P1 Inputs, list
  only the P1 materials needed across its recipes. Keep the list complete when source quotes
  are unavailable; represent the missing quote explicitly rather than omitting
  its material.
- On Extraction, `Extracted P0` models
  zero acquisition cost for internal use, not zero real extraction cost.
  State this assumption near the controls.
- On P1 Inputs, offer the three market profiles and the current net unit cost
  from each Extraction operation that produces the exact input material.
  Label the source `Extraction · P0 → P1` and identify it by operation ID when wiring
  production calculations. Do not offer `Extracted` profiles or a generic
  calculated-cost option. A material without a matching output has only
  market choices. The mockup exposes calculated costs for all 15 P1 outputs.
  Extraction's P2 route costs are not imported by P1 Inputs.
- Default P0 inputs to `Extracted P0`, with 0 ISK/unit shown in the separate
  value field, and all other inputs to `Jita Sell 5%`. Show missing archived
  quotes as unavailable, without substituting a different price.
- Changes to a material's source may affect operations on other pages that
  consume that material. Make the dependency visible; exact scope and persistence
  of these selections remain open.

### Operation comparison and details

Each operation must have a stable identifier unique across the view pages.
These identifiers will distinguish calculated unit-cost outputs when reused as
downstream input prices.

The comparison should include, at minimum:

- Operation and output material.
- Units per recipe cycle.
- Compact, editable completed cycles/hour input with a route-specific default.
- Units made per hour.
- Materials cost and normalized materials cost per unit.
- Import/export taxes and normalized tax cost per unit.
- Net cost per unit and selected unit sales valuation.
- Profit margin immediately after Sale / unit: `(sale − net cost) / sale`,
  displayed as a percentage to two decimal places. Show `—` when cost or
  sale is unavailable or the sale price is nonpositive. Margin is independent
  of cycles/hour.
- Gross sales and profit/loss per hour, day, and 30 days.
- Input/output volume and a loadout summary when imported inputs apply.

Group operation rows by production route, with a compact one-line header
such as **P0 → P1** above each group. Keep column headings visible at the
top of the operations table while scrolling, with the current route header
directly below. The next route header takes over as its group reaches it. Keep route
labels visible when the table is scrolled sideways.

Show material sources, per-stage costs, and tax breakdowns in expandable
details. Place the disclosure arrow directly before the output name and make
the name and arrow a single keyboard-accessible control. Collapsed details
take up no separate line. The former separate, fixed "cycles per hour" column
is removed: the editable rate is the value the user supplies for each operation. Rates may be
fractional (for example `0.5`) if the user chooses. Initialize each operation
with its route's default and preserve the user's chosen rate while adjusting
other operation inputs.

Show hourly and 30-day profit/loss side by side in the main comparison table;
keep daily profit/loss in the expanded details. Daily and 30-day values are
estimates from continuous operation at the entered
rate, not verified factory capacity, mining supply, market liquidity, or sales
forecasts. Do not derive a factory plan from an operation's recipe or silently
change its entered rate.

The loadout detail should show imported material names and quantities for a
whole number of cycles fitting within one 10,000 m3 launchpad. A future
production interaction may offer a popup and copy-as-Markdown action; mockups
may show the details inline and must not imply that copy behavior is implemented.

## Initial view contents

### Extraction

Possible input tiers: P0 and P1.

Give each route a **Set cycles/hour** button with a single rate input beside
its label. Applying a nonnegative rate updates and recalculates only that
route's rows, which remain individually editable. Cancel makes no changes.

Operations:

- P0-P1 — one row per catalog P1 output, sorted alphabetically by output.
  Keep only the output name and disclosure arrow in the first cell. Show
  the route, matching P0 ingredient, and quantities together in the expanded
  recipe details, along with the operation ID. Give each row its own cycle
  rate. The mockup uses catalog recipe quantities and archived prices.
- P0-P1-P2 single — one row per P2 output whose two recipe inputs can both be
  produced from raw resources found on a single planet type, sorted
  alphabetically by output. Use the catalog's single-planet eligibility
  calculation. Show eligible planet types and recipe quantities in the
  expanded details. This is eligibility, not a guarantee of extraction yield
  or colony capacity. Routes that require imported P1 are not part of this group.
- P0-P1-P2 split — one row per catalog P2 output, all 24 sorted alphabetically.
  Add a compact `Local P1` dropdown immediately after the output name. List
  only that recipe's two P1 ingredients, default to the first in recipe
  order, and keep the selection independent per row. The selected ingredient
  is refined from locally extracted P0; the other is imported. Show both
  roles in expanded details and update them when the selection changes.
  Recalculate the split route cost using the price of the imported P1.
  Include the 21 outputs that
  can also be made on one planet so the routes can be compared. Identify the
  routes separately for pricing and default split operations to an editable
  3 cycles/hour.

### P1 Inputs

Imported input tier: P1 only.

Operations:

- P1-P2 — 24 P2 outputs.
- P1-P3 — 21 P3 outputs.
- P1-P4 — 8 P4 outputs.

Append the category letter from
[PI Stats](../../src/pfmsoft/eve_argus/pi/markdown_docs/pi-stats.md) after each
P3 and P4 operation name. Use S (Simple) and C (Complex) for P3, and L (Low),
M (Medium), and H (High) for P4. Leave P2 names unchanged.

Sort each group alphabetically by output. Each row has its own editable
cycles/hour rate, defaulting to `1`; there is no separate factory-rate selector.
Keep the column headings visible at the top of the operations table during
vertical scrolling, with the current route heading immediately below them.
Each P1 Inputs operation group has a **Set cycles/hour** button. P1-P2 takes
one rate for the group. P1-P3 takes separate Simple and Complex rates; P1-P4
takes separate Low, Medium, and High rates. Each rate input sits on the same
line as its label. Applying a nonnegative rate
updates only the corresponding rows and recalculates their estimates. Blank
category fields leave those rows unchanged. Other groups are unchanged and
each row remains editable.

For P1-P3 and P1-P4, expand the recipe through locally produced intermediates
to its P1 requirements. Scale each intermediate recipe by its output quantity
and sum repeated P1 ingredients, including any direct P1 inputs. Show the
direct recipe, the resulting P1 quantities, and the total P1 import tax per
finished recipe cycle. Use selected P1 prices for material cost; apply no
customs to local intermediates and charge export tax only on the finished output.

### P2 Inputs

Use the P1 Inputs layout and archived valuation controls. List all 21 P3
outputs under **P2 → P3** and all 8 P4 outputs under **P2 → P4**, sorted
alphabetically within each group. Keep category suffixes, sticky column and
route headings, editable per-row rates defaulting to `1`, and category-specific
**Set cycles/hour** dialogs.

- P3 uses its direct P2 recipe. For P4, expand locally made P3 intermediates
  into P2 requirements scaled by the intermediate output quantities. Sum
  repeated inputs per finished cycle.
- Also import the direct P1 ingredient for Nano-Factory, Organic Mortar
  Applicators, and Sterile Conduits. Show its quantity and import tax separately
  from P2 in the expanded details. Do not apply customs to locally made P3;
  charge export tax only on the finished P3 or P4 output.
- List the needed P2 and supplemental P1 materials in separate source groups,
  each with **Set all inputs**. Default to `Jita Sell 5%`. Offer the three market
  profiles plus matching Extraction unit costs: single and/or split routes
  for P2 and P0 → P1 for supplemental P1. Do not offer zero-cost extraction.
- Offer **P1 Inputs · P1 → P2** for each matching P2 material. Use the
  producing planet's P1 source selections and customs rate carried by
  mockup navigation, or the P1 Inputs defaults when opened directly. This
  net unit cost includes the producing planet's P1 import and P2 export
  taxes. Charge P2 import tax separately at the receiving planet's rate.

### P3 Inputs

Use the shared operations layout for one **P3 → P4** group of all eight
P4 outputs, sorted alphabetically. Keep sticky headings, category suffixes,
individual rates defaulting to `1`, and a **Set cycles/hour** dialog with
separate Low, Medium, and High rates.

- Use the direct P4 recipe. Import P3 plus the required direct P1 ingredient
  for Nano-Factory, Organic Mortar Applicators, and Sterile Conduits. Show
  P3 and P1 quantities and import taxes separately in expanded details.
  Charge export tax on the finished P4 only.
- List the needed P3 and supplemental P1 materials in separate source groups
  with **Set all inputs**. Default to `Jita Sell 5%`. For P3, offer the archived
  market profiles and matching **P1 Inputs · P1 → P3** and
  **P2 Inputs · P2 → P3** net unit costs. For supplemental P1, offer the same
  market profiles and the matching Extraction cost.
- Calculated sources include upstream customs and use the upstream source
  choices and tax rates carried by mockup navigation, or upstream defaults on
  direct open. The receiving planet charges its own import tax separately.

## Cost export

The intended feature is to export selected unit costs for use in other
calculations, with at most one selected value per material. Do not assume that
this export has the same schema or behavior as the existing browser's selective
JSON export until compatibility is explicitly decided. The JSON shape, whether
the exported number represents a unit cost or a sales quote, selection rules,
and downstream import behavior remain open.

## Decisions to resolve before production implementation

- Whether source selections are shared across pages, scoped per page, or
  overridable per operation, and how cascading changes are indicated.
- Exact price-source behavior for calculated operation outputs and extracted
  material sources.
- Customs-tax bases and boundaries for each route; verify against the PI
  calculation code and current game references rather than infer from the
  mockup.
- Whether sales tax, transport fees, or extraction cost should be modeled.
- The denominator and meaning of `% Return`; do not display a calculated
  percentage until defined.
- Whether selected costs export to JSON, its exact schema, and how another
  calculation consumes it.
- The production defaults and validation limits for the customs rate and
  per-operation cycles/hour rate.
- How stale, missing, or unknown-freshness market data is shown.
- Which roadmap views should follow the first two pages, and what decision each
  one supports.

## Mockup review and acceptance

The first iteration is ready for review when:

- Both pages open directly from disk, share navigation and styling, and link to
  each other.
- The desktop layout uses the available viewport width, with material source
  rows fitting name, dropdown, value, and information button on one line.
- Dragging or keyboard-adjusting the vertical divider changes the relative
  widths live and exposes its current percentage accessibly; narrow layouts
  stack the panes and hide the divider.
- The two active pages show their stated operation groups and relevant input
  tiers; future views are marked as planned.
- Scrolling through a long operation group keeps its route label visible
  without adding a route label to every operation row.
- Market values are labeled as archived, and no data is fetched from the
  network. The market views show only P0–P4 materials with all report fields.
- P1 Inputs offers Extraction unit costs only for matching materials, and
  selecting one displays the same unit cost shown on Extraction.
- Editable cycles/hour inputs initialize to `6` for Extraction P0-P1, `3` for
  both Extraction P0-P1-P2 routes, and `1` for other operations.
- Changing the local P1 on a split row swaps its local/imported assignments
  without affecting another row or its cycle rate.
- Changing a rate updates illustrative units/hour and time-based profit/loss
  consistently, while leaving its unit cost unchanged.
- Detailed tax, material, volume, and loadout information can be found without
  making the primary comparison table unmanageably wide.
- Layout remains usable on a narrow screen and has semantic headings, table
  headers, and labels for controls.

After review, record visual and behavior decisions here before promoting this
plan into [planetary_interaction.md](./planetary_interaction.md) or starting
production integration.
