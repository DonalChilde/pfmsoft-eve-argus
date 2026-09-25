# Reprocessing deal finder

NOTE: The initial efforts will be to generate scripts in the dev/proof-scripts/reprocessing directory. once a final path has been determined, the code will be moved into eve-argus proper. dev/proof-scripts/proof-output/reprocessing can be used for output.

In Eve Online it is possible to reprocess ships and equipment and regain a portion of the materials used to create the item.

There is only one skill that affects reprocessing non-ore/gas/ice items, and the maximum percentage of materials regained is 55%, rounded down.

Eve-argus has access to enough information to make reports on the precrocessed value of items, and the market values of both the item, and its reprocessed materials.

Note, portion size determines the number of items required to reprocess one unit, eg a frigates portion size is one, and a typical ammo portion size is 100. 100 units of that ammo would be required in order to reprocess it.

The materials contained in items are defined in type_materials. Not all items in this table might be published, or available in the market.

It is assumed that the type_materials entry represents a portion size of items, eg. 100 ammo, but this needs to be verified in game.

Goals:

- Find ways to make reprocessing profitable
- make a markdown document that details the reprocessed materials available from an item, the market price buy/sell at various hubs of the item and its constituent materials, grouped by market path. I envision a table of the various data for each item.
- in another document
  - Find deals on reprocessed goods, where either the buy. sell, or both price of the items is less thatn the value of the reprocessed materials.
  - Find deals or improved deals that generate profit buy moveing those reprocessable goods between market hubs.

Document types and tools available:

- markdown
- html
- spreadsheets that can import csv for further processing.

## Working plan

This document is the controlling plan for the reprocessing prototype. Keep the
prototype entirely in `dev/proof-scripts/reprocessing/`. Generated reports and
intermediate output belong in `dev/proof-scripts/proof-output/reprocessing/`.

Do not modify `src/` or `tests/` during the prototype without explicit approval.
Production integration and comprehensive automated tests will be added later,
when the proven approach is migrated into eve-argus proper.

### Initial scope

- Include input items whose types are published and have a `market_group_id`.
- Include recovered materials only when their types are also published and have
  a `market_group_id`.
- If an eligible item has one or more recovered materials that are not
  published or do not have a `market_group_id`, log the condition and retain
  the material quantity in the reference output.
- Treat this as an unusual condition because a published parent item is usually
  the success gate.
- Analyze all five configured market hubs: Jita, Amarr, Dodixie, Hek, and Rens.
- Use existing 5% market-depth buy and sell summaries where available. It is possible that there is no pricing for an item, as it depends on player orders.
- Retain all eligible rows in the output and rank positive opportunities.
- Use a configurable minimum margin, initially `0%`.
- Produce both Markdown and CSV reports.

### Expected data sources

These are the expected sources to verify before implementation and again during
migration.

- static data is loaded via src/pfmsoft/eve_argus/static/db/query_helpers.py
  - use of query helpers is preferred for database access.
  - in production, all sql queries should live in query_helpers
  - during prototyping note sql queries not available in query_helpers, for later inclusion.
- upstream pricing data comes from ESI regional market orders.
- prototype pricing data is loaded via
  `src/pfmsoft/eve_argus/market/orders/db/query_helpers.py`.
  - persisted 5% pricing summaries are available in the database by hub system,
    rather than only by region or station.
  - if persisted summaries are unavailable, the fallback is to transform raw
    regional orders and calculate the summaries using the existing transform.

#### Static type data

- **Authoritative source:** the static database `types` data loaded from the
  EVE static data set.
- **Required fields:** type ID, type name, `published`, `market_group_id`, and
  `portion_size`.
- **Expected access path:** existing static database query helpers or the
  corresponding read-only models already used by eve-argus.
- **Used for:** selecting input items and materials, displaying names,
  applying the published and market-group filters, showing portion size, and
  grouping output by market path.
- **Migration check:** confirm the prototype does not reconstruct type data
  from report text or maintain a second copy of these fields.

#### Type material data

- **Authoritative source:** `type_materials` and its component records in the
  static database.
- **Required fields:** input type ID, material type ID, and component quantity.
- **Expected access path:** the existing type-material query/model layer, or a
  read-only equivalent in the proof script.
- **Used for:** determining the materials in one input portion and calculating
  recovered quantities after applying the assumed yield.
- **Related source:** randomized-material tables should be read far enough to
  flag affected inputs, but their quantities must not be treated as ordinary
  fixed components until their in-game behavior is verified.
- **Migration check:** reconcile at least one prototype composition against the
  static database rows and preserve any excluded or unclassified materials in
  the report status.

#### Market Path

- market path information is available in the Argus static database's
  `market_groups` data.
- use the market group's `str_path` for report grouping and retain its
  `int_path` when a stable identifier is needed.

#### Market hub definitions

- **Authoritative source:** the existing configured market hub definitions.
- **Required fields:** hub name, region ID, system ID, and station ID where
  needed to identify the market request.
- **Expected access path:** the existing market-hub model/configuration, not a
  duplicated list maintained only by the prototype.
- **Used for:** selecting Jita, Amarr, Dodixie, Hek, and Rens and labeling
  every price and deal row with its hub.
- **Migration check:** compare the prototype's hub IDs and names with the
  configured definitions before moving the logic into eve-argus.

#### Market orders and price summaries

- **Upstream source:** ESI regional market orders.
- **Prototype access path:** persisted market orders and pricing summaries are
  available through
  `src/pfmsoft/eve_argus/market/orders/db/query_helpers.py`.
- **Required fields:** type ID, buy/sell side, 5% price, 5% item volume, 5%
  order count, and snapshot metadata where available.
- **Fallback calculation:** raw regional orders can be transformed and passed
  through the existing 5% order-summary transformation.
- These values are loaded from the ESI, out of context for this operation.
- Summary pricing is precaculated, and available in the database.

- **Migration check:** preserve the distinction between missing orders, thin
  orders, and a genuine zero-valued price; never convert missing data to zero.

#### Verified prototype findings

The first static-data inspection ran successfully against the configured
databases and produced `static_inventory.json` in the proof-output directory.
The current snapshot contained:

- 26,992 published types.
- 19,432 published types with a `market_group_id`.
- 7,760 eligible types with fixed material records.
- 10 randomized material definitions.
- 6 fixed material components whose types are outside the eligible published
  and market-grouped set.
- All five configured hubs currently have persisted order summaries in the
  market-orders database.
- In-game verification confirms that `type_materials` quantities represent the
  recovered materials for the item's `portion_size`, including items with a
  portion size greater than one.
- In-game verification confirms that the prototype's reprocessing quantity
  math and rounding match the observed results.

Types without material records include terminal materials and other inputs that
are not themselves reprocessable. They are not automatically errors. Fixed
components outside the eligible set are retained in the reference output but
excluded from priced reprocessed-value totals, and the affected item is marked
incomplete.

The full prototype run generated 7,760 input sections, 38,800 value CSV rows,
and 388,000 deal CSV rows. The deal output is currently a gross comparison and
should not be treated as an actionable ranking without market-depth quality
flags. For example, 29,505 of 34,678 Jita summary rows currently have two or
fewer orders at the 5% depth.

Next refinement: propagate 5% order counts and item quantities into the report
data, mark sparse sides as thin, and decide whether thin rows should remain in
the ranked report or only in the comparison CSV. Do not silently discard them
until that policy is decided.

The persisted `order_summaries` table includes an `ID` column before the summary
fields. The shared `get_order_summaries()` helper was corrected to select the
modeled columns explicitly instead of relying on `SELECT *`. The prototype now
uses that shared helper, and the correction is covered by the focused market
summary and hub-fetch test runs.

#### Report metadata

Every generated report should identify the data snapshot or fetch time, assumed
yield, order-depth setting, hub set, and provisional assumptions. This makes a
later comparison between proof output and migrated eve-argus output possible.

### Calculation rules

- Use a configurable assumed reprocessing yield, defaulting to `55%`.
- Apply the yield to the materials returned from one input portion and round
  material quantities down according to the in-game rules.
- Treat `portion_size` as the number of input items required for one
  reprocessing portion, pending in-game verification.
- Calculate both deal directions at each hub:
  - sell the input item and buy the recovered materials;
  - buy the input item and sell the recovered materials.
- Show the input quantity, recovered quantities, prices, gross values, margins,
  and missing-market data for every report row.
- Missing or thin market data must remain missing; it must not be treated as a
  zero price or zero value.

### Cross-hub comparisons

Compare the five hubs to identify improved sourcing and output prices. During
the prototype, report these as gross price differences only. Do not subtract
hauling, route, broker, station-tax, or travel costs until a transport-cost
model has been designed and approved.

### Planned reports

1. **Reprocessing value report**

A Markdown report grouped by market path and input item, with hub prices as
columns. For each eligible input,
show its portion size, assumed yield, recovered materials, material
quantities, input market prices, recovered-material market prices, and gross
reprocessed values.

2. **Reprocessing deals report**

   A Markdown report highlighting positive gross-margin opportunities while
   retaining the complete comparison data. Include both deal directions and
   identify whether an opportunity is local to one hub or improved by sourcing
   and selling across different hubs. The ranked opportunities table is the
   primary output. Add exception notes only when an opportunity has cross-hub,
   missing-data, unusual-portion, randomized-material, or other provisional
   conditions that need explanation.

3. **Spreadsheet data export**

  A CSV suitable for further analysis. The value-report export uses one row
  per input item and hub, with input prices, reprocessed values, and missing
  material data. The later deals export will add one row per input item,
  source hub, output hub, and deal direction.

### Report mockups

The following examples are illustrative only. The names, quantities, prices,
and margins are placeholders that show the intended report shape; they are not
market data or expected results.

#### Mockup: reprocessing value report

```markdown
# Reprocessing Value Report

Generated: 2026-09-24 | Assumed yield: 55% | Order depth: 5%
Status: PROVISIONAL - portion-size semantics require in-game verification

## Market path: Ships > Frigates

### Tristan

Input type ID: 587 | Portion size: 1

#### Reference prices by hub

This table is the primary reference view. It includes the input item and each
recovered material, with the available buy and sell prices at every hub.

| Role     | Item      | Quantity per portion |  Jita Buy |  Jita Sell | Amarr Buy | Amarr Sell | Dodixie Buy | Dodixie Sell |   Hek Buy |   Hek Sell |  Rens Buy |  Rens Sell | Market status |
| -------- | --------- | -------------------: | --------: | ---------: | --------: | ---------: | ----------: | -----------: | --------: | ---------: | --------: | ---------: | ------------- |
| Input    | Tristan   |                    1 | 95,000.00 | 101,000.00 | 97,500.00 | 103,000.00 |   96,000.00 |   102,000.00 | 98,000.00 | 104,000.00 | 98,500.00 | 105,000.00 | complete      |
| material | Tritanium |               12,100 |      4.25 |       4.31 |      4.20 |       4.29 |        4.18 |         4.27 |      4.16 |       4.25 |      4.19 |       4.28 | complete      |
| material | Pyerite   |                3,600 |      8.10 |       8.35 |      8.05 |       8.30 |        8.00 |         8.25 |      7.95 |       8.20 |      8.00 |       8.24 | complete      |
| material | Mexallon  |                1,100 |     52.00 |      53.20 |     51.50 |      52.90 |       51.00 |        52.70 |     50.80 |      52.40 |     51.20 |      52.80 | complete      |

#### Reprocessed value by hub

This table explains the value of the recovered materials using the prices from
the reference table. Buy value uses hub buy prices; sell value uses hub sell
prices.

| Input item | Hub     | Portion size | Input buy price | Input sell price | Reprocessed buy value | Reprocessed sell value | Missing data |
| ---------- | ------- | -----------: | --------------: | ---------------: | --------------------: | ---------------------: | ------------ |
| Tristan    | Jita    |            1 |       95,000.00 |       101,000.00 |            137,785.00 |             140,731.00 | none         |
| Tristan    | Amarr   |            1 |       97,500.00 |       103,000.00 |            136,000.00 |             139,900.00 | none         |
| Tristan    | Dodixie |            1 |       96,000.00 |       102,000.00 |            135,100.00 |             138,700.00 | none         |
| Tristan    | Hek     |            1 |       98,000.00 |       104,000.00 |            133,900.00 |             137,600.00 | none         |
| Tristan    | Rens    |            1 |       98,500.00 |       105,000.00 |            135,500.00 |             139,200.00 | none         |
```

The value report should repeat this two-table structure for each input item and
market path. The reference table should preserve empty cells for unavailable
prices and record a status or note for missing, thin, unpublished, or ungrouped
recovered materials rather than silently dropping them.

#### Mockup: reprocessing deals report

```markdown
# Reprocessing Deals Report

Generated: 2026-09-24 | Minimum gross margin: 0%
Status: PROVISIONAL - excludes hauling, taxes, broker fees, and route costs

## Ranked opportunities

| Rank | Input item     | Source hub | Output hub | Deal direction             | Input cost | Output value | Gross profit | Margin | Data quality |
| ---: | -------------- | ---------- | ---------- | -------------------------- | ---------: | -----------: | -----------: | -----: | ------------ |
|    1 | Tristan        | Jita       | Jita       | buy input / sell materials |  95,000.00 |   140,731.00 |    45,731.00 | 48.14% | complete     |
|    2 | Example Module | Amarr      | Jita       | buy input / sell materials | 210,000.00 |   244,000.00 |    34,000.00 | 16.19% | complete     |

## Exception notes

Routine opportunities do not receive a duplicate detail section. This section
is emitted only for rows that require explanation.

### Example Module

| Field             | Value                                                      |
| ----------------- | ---------------------------------------------------------- |
| Reason for note   | Cross-hub opportunity with incomplete Hek material pricing |
| Source hub        | Amarr                                                      |
| Output hub        | Jita                                                       |
| Affected material | Mexallon                                                   |
| Missing data      | Hek sell price                                             |
| Impact            | Hek is excluded as an output hub for this row              |
| Transport cost    | not modeled                                                |
| Caveats           | assumed 55% yield; portion size not yet verified           |
```

The deals report should include both `sell input / buy materials` and
`buy input / sell materials` rows. A cross-hub row should identify the source
and output hubs separately and describe its result as a gross opportunity until
transport costs exist. Do not repeat the ranked row's prices, profit, and margin
in an exception note unless the note explains a data-quality or calculation
condition that changes how the row should be interpreted.

#### Mockup: spreadsheet CSV export

The CSV should be machine-readable without requiring Markdown parsing. Numeric
fields should remain numeric, and missing prices should be empty rather than
zero.

```csv
input_type_id,input_name,market_path,portion_size,yield_percent,source_hub,output_hub,deal_direction,input_price,input_price_side,recovered_value,recovered_value_side,gross_profit,margin_percent,market_status,assumption_status
587,Tristan,Ships > Frigates,1,55,Jita,Jita,buy_input_sell_materials,95000.00,buy,140731.00,sell,45731.00,48.1389,complete,provisional_portion_size
587,Tristan,Ships > Frigates,1,55,Jita,Jita,sell_input_buy_materials,101000.00,sell,137785.00,buy,36785.00,36.4208,complete,provisional_portion_size
```

The export should have one row per input item, source hub, output hub, and deal
direction. Material-level detail may be emitted in a second normalized CSV if
putting all recovered materials into one row would make the primary export
ambiguous.

### Verification gates

- **Complete:** Verify that `type_materials` quantities represent one
  `portion_size` of input items, including a non-1 portion-size item, and that
  the reprocessing math and rounding match in-game results.
- Confirm the joins and filters for published types, market groups, type names,
  portion sizes, and material components.
- Flag randomized material definitions for separate review; do not silently
  treat them as ordinary fixed reprocessing output.
- Manually reconcile at least one generated row against the component
  quantities, assumed yield, market prices, and margin calculation.
- Label generated profitability as provisional until portion-size semantics and
  any other material game-mechanics assumptions have been verified.

### Implementation phases

1. **Complete:** Create a small data inspection script under
   `dev/proof-scripts/reprocessing/` to establish eligible type and material
   counts and expose excluded records.
2. **In progress:** Create the prototype calculations and five-hub market
   comparison scripts in the same directory.
3. **Complete for the value report:** Generate the Markdown and normalized CSV
  value-report artifacts under `dev/proof-scripts/proof-output/reprocessing/`.
4. Review a small known sample and refine the report shape, filters, and
   assumptions in this document.
5. **Complete for the prototype:** Implement the ranked deals report and its
  deal-direction CSV export. The report ranks positive gross opportunities,
  evaluates both deal directions across local and cross-hub pairs, and keeps
  incomplete rows in the CSV with missing-data flags.
6. Refine market-depth quality flags and review the full-run outliers.
7. Decide whether the prototype is ready for migration into eve-argus proper.

### Deferred work

- Moving code into `src/pfmsoft/eve_argus/`.
- Adding production tests under `tests/`.
- Modeling hauling, route, broker, station-tax, or travel costs.
- Modeling character skills or facility-specific yield modifiers.
- Establishing the correct treatment of randomized materials.
- Expanding the analysis into blueprint manufacturing economics.
