# Multi-buy tool

I want to create a stand alone html file that can work with the clipboard to import and export data that will be used with the multibuy tool in eve online.

The end result should be able to:

- import and parse a text list of materials, including extra data is present
- multiply an imported set of materials to get the total quantity for x sets
- dif the quantities of materials on hand, vs materials required.
- display the manipulated data both as an html table, and a raw text field that can be copy pasted into the eve multibuy.

These import formats should be supported:

The output from an eve online inventory screen:

Its Fields are:
|Name|Quantity|Group|Category|Size|Slot|Volume|Meta Level|Tech Level|Estimated Price|

```text
Scourge Fury Cruise Missile	45,965	Advanced Cruise Missile	Charge			2,298.25 m3	5	2	20,772,502.80 ISK
Inferno Fury Cruise Missile	45,000	Advanced Cruise Missile	Charge			2,250 m3	5	2	23,153,850.00 ISK
Antimatter Charge L	8,900	Hybrid Charge	Charge	Large		222.50 m3		1	1,902,553.00 ISK
Nanite Repair Paste	300	Nanite Repair Paste	Charge			3 m3		None	7,778,799.00 ISK
Antimatter Charge L	100	Hybrid Charge	Charge	Large		2.50 m3		1	21,377.00 ISK
Tracking Speed Script	11	Tracking Script	Charge	Small		11 m3		1	159,547.74 ISK
Optimal Range Script	11	Tracking Script	Charge	Small		11 m3		1	152,061.58 ISK
Inertial Stabilizers II	3	Inertial Stabilizer	Module		Low	15 m3	5	2	917,745.33 ISK
Warp Core Stabilizer I	2	Warp Core Stabilizer	Module		Low	10 m3		1	35,804.96 ISK
Salvager I	2	Salvager	Module		High	10 m3		1	101,043.20 ISK
```

Various text formats

Fields:
|Name|Quantity|

```text
Bacteria	 2,400,000
 Biofuels 	 1,070,400
 Biomass 	 1,228,800
 Chiral Structures 	 -
 Electrolytes 	 1,200,000
 Industrial Fibers 	 -
 Oxidizing Compound 	 -
 Oxygen 	 2,144,215
 Plasmoids 	 1,070,400
 Precious Metals 	 1,070,400
 Proteins 	 -
 Reactive Metals 	 1,228,800
 Silicon 	 -
 Toxic Metals 	 -
 Water 	 2,198,202
```

Fields:
|Name|Quantity|

```text
Bacteria	0
Biofuels	0
Biomass	320
Chiral Structures	240
Electrolytes	240
Industrial Fibers	320
Oxidizing Compound	320
Oxygen	0
Plasmoids	0
Precious Metals	0
Proteins	320
Reactive Metals	240
Silicon	0
Toxic Metals	240
Water	480
```

Fields:
|Quantity|Name|

```text
0   Bacteria
0   Biofuels
320 Biomass
```

Fields:
|Quantity|Name|

```text
-   Bacteria
-   Biofuels
320 Biomass
```

Values parsed from the Eve Inventory screen should be retained for use in exported data.

## First milestone: parse and preview

Open [the standalone tool](../tools/multi-buy.html) directly in a browser. It uses
embedded CSS and JavaScript, with no server, external assets, storage, or JavaScript
testing dependencies.

- Paste input into the text box on the left and select **Parse**. The table on the
  right shows all ten inventory columns. On narrow screens, the panels stack.
- Import's top-right **Reset** clears the input text and parsing errors, then
  focuses the input. Parsed Data, cached metadata, and all lower-pane data remain
  unchanged.
- Drag the vertical divider to resize the panes on wide screens. The import pane
  can occupy 25 to 75 percent of the space available to the panes. Focus the
  divider and use Left/Right arrows (2 percent steps), Shift+arrows (10 percent),
  or Home/End (minimum/maximum). The divider is hidden when the panes stack;
  the selected proportions are retained until reload.
- Accept the examples above, including comma-separated quantities and `-` as zero.
  Short-form rows accept tabs or spaces and either column order. Recognized
  headers and blank lines are ignored.
- Combine duplicate, case-sensitive item names by summing quantities. Names are
  trimmed, but internal spaces are preserved. Rows retain first-occurrence order.
- Each successful parse replaces the displayed quantities, while inventory
  metadata stays cached by Name until the page closes or reloads. Later short-form
  inputs reuse that metadata; missing metadata produces empty cells.
- Volume and Estimated Price from inventory are stack totals. Divide each by its
  source quantity on import and cache exact per-unit rational values (BigInt
  numerator/denominator), without intermediate rounding. The last inventory row
  for a Name supplies the latest unit estimate; short-form imports do not replace
  it. Descriptive fields and source quantity remain cached, but original numeric
  stack totals are not used as metadata. Zero-quantity sources and empty numeric
  fields yield unknown unit values, replacing previous values for that Name.
  Parsed Data and every long export multiply cached unit values by their own
  quantities, rounding half up to two decimal places in m3 or ISK. Estimated
  Price remains an imported estimate, not a live quote. Missing unit values render
  and export as empty cells. Nonempty malformed volume or price rejects the
  entire import with line-numbered errors.
- Malformed or empty imports show actionable errors without changing the previous
  table or metadata cache. Invalid rows identify their original line numbers.
- Below the table, **Export Long** copies all ten inventory
  columns to the clipboard; **Export Short** copies Name and Quantity. Both
  produce tab-delimited text without headers, in displayed row order, retaining
  zero quantities and comma-grouped quantities. Long form preserves empty fields
  and descriptive metadata, recalculating volume and estimated price for each
  exported quantity.
  Buttons are disabled until the first successful parse. If clipboard access is
  unavailable or denied, an error and selected text box allow manual copying.

### Manual browser acceptance checks

No JavaScript testing framework or dependencies are required.

1. Parse each example above and inspect names, quantities, and empty metadata
   cells. Check that both dash formats produce zero quantities.
2. Parse the inventory example. Confirm that `Antimatter Charge L` has quantity
   `9,000`, with calculated `225.00 m3` and `1,923,930.00 ISK` using the latest
   stack's per-unit values.
3. Parse `Antimatter Charge L` followed by a tab and `200`. Confirm that the
   quantity changes, metadata remains available, and volume/price become
   `5.00 m3` and `42,754.00 ISK`.
4. Import a new inventory row for that Name with a changed Estimated Price.
   Confirm that the newest value is retained through subsequent short-form imports.
5. Include an invalid row after a valid inventory row. Confirm a line-numbered
   error and that neither the table nor cached metadata changes. Try empty input
   and malformed comma grouping as well.
6. Parse an item named `<img src=x onerror=alert(1)>` with a tab and quantity `1`.
   Confirm it displays literally without executing or creating an image.
7. Check the side-by-side layout on a wide screen, stacked panels on a narrow
   screen, horizontal table scrolling, and keyboard access to the controls.
8. Reload the page and confirm that all imported data and metadata are cleared.
9. After parsing, try both export buttons. Paste into a text editor and check
   that long form has ten tab-delimited fields per row (including empty fields),
   and short form has two. Confirm no headers, combined quantities, and row order.
   Reimport each export and confirm the table is unchanged. Before parsing, verify
   that both buttons are disabled.
10. Deny clipboard access and verify an explicit failure message and selectable
    export text, not a success message. Confirm that manual text matches the
    selected format, and a successful new parse clears that fallback.
11. Drag the pane divider in both directions and beyond its limits. Check that
    neither pane collapses and parsed data is preserved. Check keyboard resizing
    and that the divider disappears on narrow screens.

## Inventory, material sets, and Multi-buy

Below the horizontal divider are three side-by-side panes: **Inventory On Hand**,
**Material Set**, and **Multi-buy**. Their two draggable dividers resize adjacent
panes without resizing the third. Each pane retains at least 20 percent of the
available pane space. The same keyboard controls as the upper divider apply.
All three panes stack and the dividers disappear on narrow screens.

Inventory On Hand and Multi-buy display Name, Quantity, and Volume. Inventory
volume uses the on-hand quantity; Multi-buy volume uses the positive shortfall
quantity. Both multiply by cached unit volume with the same rounding rules as
Material Set. Items without a usable unit volume show an empty cell.

Material Set displays Name, followed by grouped **Per Set** and **Required**
headers, each with Quantity and Volume columns. Unit volume is cached source-stack
volume divided by its source quantity. Per-set and required volumes multiply that
unrounded ratio by their respective quantities, then round half up to two decimal
places in m3 using exact integer arithmetic. Missing volume or a zero source
quantity leaves both volume cells blank. Valid zero volume displays `0.00 m3`.
Malformed nonempty inventory volume rejects the import with a line-numbered error;
decimal volumes with optional comma grouping and `m3` or `m³` units are supported.

All three tables have total-volume footers; Material Set totals both Per Set and
Required volumes. Totals sum the displayed, two-decimal row volumes exactly.
Unknown volumes are excluded, and the total is explicitly labelled partial with
the number of unknown rows, even when all rows are unknown. Empty tables total
`0.00 m3`. Totals refresh after parsing metadata, sends, resets, and multiplier
changes. Clipboard exports remain item-only, without total rows.

Inventory On Hand and Material Set each provide **Export Long** and **Export
Short** buttons below their tables. Inventory exports on-hand quantities; Material
Set exports Required quantities (base times multiplier), not base quantities or
inventory-adjusted shortfalls. Both use the existing headerless TSV formats,
cached descriptive metadata and calculated stack volume/price for long form, and pane-specific manual-copy
fallbacks. Zero-quantity rows are retained. Empty lists disable their exports;
an invalid multiplier disables Material Set exports but not Inventory exports.
Changes to workflow data clear outdated export feedback and fallback text.

1. Parse inventory, then select **Send To Inventory**. An empty inventory receives
   the parsed quantities without confirmation. Otherwise, confirm before combining:
   matching names have their quantities added, existing-only items remain, and new
   names append in parsed order. Cancel leaves inventory and Multi-buy unchanged.
   Sending the same parsed list again adds its quantities again. Reset inventory
   first when replacement rather than addition is intended.
2. Parse a recipe or other grouping, then select **Send To Material Set**. An
   empty set receives the parsed quantities without confirmation. Otherwise,
   confirm before adding matching base quantities and appending new names.
   Existing-only materials remain. Cancel leaves the base set and Multi-buy
   unchanged. The multiplier and inventory are preserved; sending the same list
   again adds its base quantities again. Reset the set first to replace it.
3. Set **Number of sets** to a non-negative whole number. Required quantity is
   base quantity multiplied by this count. Multiplication never mutates the base.
4. Multi-buy lists positive shortfalls only: `max(required - on_hand, 0)`, in
   material-set order. Unlisted inventory counts as zero; excess inventory and
   inventory-only names do not appear in the shopping list. Zero sets means no
   purchases.
5. Export the shopping list using its own long/short clipboard buttons and manual
   fallback. Cached per-unit metadata remains unchanged; stack volume and price
   are recalculated for the exported quantity. Later parsing updates the cache but does not replace
   assigned quantity lists until the corresponding assignment button is selected.

An invalid set count produces a visible error, retains the last valid calculated
quantities, and disables Multi-buy exports until corrected. Reload clears all lists,
the multiplier, metadata, and pane proportions. No disk storage is used.

The top-right **Reset** button in Inventory On Hand clears only its assigned list
and recalculates Multi-buy without inventory. Material Set's **Reset** clears its
base list, restores the multiplier to one, clears validation errors, and empties
Multi-buy. Neither reset clears the other assigned list, parsed data, or metadata
cache. Both clear any outdated Multi-buy export feedback and manual-copy text.

### Workflow acceptance checks

- Assign `Biomass` quantity `240` as inventory and quantity `320` as a material
  set. Three sets must show required `960` and buy `720`. Return to one set:
  required `320`, buy `80`, base still `320`.
- Check zero sets, fully covered requirements, missing inventory, inventory-only
  items, duplicate imports, and invalid/empty/negative/fractional multipliers.
- Parse a different list without assigning it. Neither assigned list may change.
  Assign it to one pane and verify the other remains unchanged.
- Check long/short shopping exports against calculated buy quantities, including
  clipboard denial, cached metadata, and disabled export for no purchases.
- Drag each lower divider to its limits, use its keyboard controls, and confirm
  that the third pane and data stay unchanged. Check stacked narrow-screen layout.
- Reset inventory and confirm the material set is preserved and all required
  quantities become shortfalls. Reset the material set with an invalid multiplier:
  its rows and Multi-buy must clear, the multiplier returns to one, and exports
  disable. Confirm inventory, parsed data, and cached metadata remain available.
- Send to empty inventory without a confirmation dialog. Then send overlapping
  and new names: cancel first and confirm nothing changes, then accept and verify
  exact summed quantities, preserved existing-only items, appended new names, and
  recalculated shortfalls. A nonempty list of zero-quantity items still requires
  confirmation. Parsed quantities and the base material set must remain unchanged.
- Repeat the confirmation, cancellation, overlap, new-name, and zero-quantity
  checks for **Send To Material Set**. Verify that quantities combine before
  multiplication, the multiplier and inventory remain unchanged, and required
  quantities and Multi-buy shortfalls recalculate only after confirmation.
- Cache `2.50 m3` for a source quantity of `100`. Assign a base quantity of `320`
  and select three sets: per-set volume must be `8.00 m3`, required volume
  `24.00 m3`. Check grouped headers, missing/zero-source volumes, zero sets,
  half-up rounding, and that required volume uses unrounded unit volume rather
  than multiplying the rounded per-set display.
- Cache `21,377.00 ISK` for a source quantity of `100`: a short-form quantity of
  `200` must display/export `42,754.00 ISK`. With inventory `200`, base `320`,
  and three sets, Required exports `960`, `24.00 m3`, `205,219.20 ISK`; Multi-buy
  exports `760`, `19.00 m3`, `162,465.20 ISK`. Verify the most recent unit estimate
  wins, malformed prices leave the cache unchanged, and zero-source unit values
  remain unknown. Full exports round stack totals to two decimals; reimporting
  rounded totals can lose sub-cent/sub-hundredth precision, unlike the in-memory
  exact cache.
