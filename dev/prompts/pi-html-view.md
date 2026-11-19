# Planetary Interaction html view

This prompt is used in conjunction with dev/prompts/planetary_interaction.md, and relates to the design of the html view for planetary interaction. After review, it can be rolled into the dev/prompts/planetary_interaction.md plan.

dev/tmp/pi-view directory and sub directories can be used for mock ups.

There should be a top nav bar allowing navigation to the different PI views, to include:

- Extraction - A view for extraction (mining) focused PI activities. Extraction planets can also include some limited factory work.
- P1-P4 - A view for factory planets turning P1 materials into higher level products.
- P2-P4 - A view for factory planets turning P2 materials into higher leevel products.
- P3-P4 - A view for factory planets turning P3 materials into higher level products.
- Exported costs - A view showing the exported unit costs of selected products. More details below.
- Factory Planner - an interactive display of the possible PI building combinations at different Control Center levels.
- Extraction Planner
- Market Prices
- Market History
- PI Stats
- Factory Layouts

## Views

### Common Elements for Extraction and factory views

#### Common Price profiles:

- `Jita Sell 5%`
- `Jita Buy 5%`
- `The Forge Avg`.
- `Extracted P0` - a zero cost input representing materials produced on one planet for internal consumption. Extraction costs are real, but not modeled.
- `Extracted P1` - a zero cost input representing materials produced on one planet for internal consumption. Extraction costs are real, but not modeled.
- `Extracted P2` - a zero cost input representing materials produced on one planet for internal consumption. Extraction costs are real, but not modeled. Not possible for all combinations.
- `Extracted P3` - a zero cost input representing materials produced on one planet for internal consumption. Extraction costs are real, but not modeled. Not possible for all combinations.

On the left side of the view, there should be a pane that displays the possible inputs for the view, grouped by PI type eg. P0, P1, and some P2 for the extraction view. Name | dropdown box to select source | Price. Maybe in a table with an invisble grid for layout? Suggest what would work best.

At the top of the view there should be an input box for tax rate, and a drop down box to pick the sales price source.

Note that a change of input cost on one view may cascade changes through the rest of the views.

We will start with buying and selling from one market hub, Jita, So the available sales prices for comparison should be `Jita Sell 5%`, `Jita Buy 5%`, and `The Forge Avg`.

The main pane of the view should be a table with columns for:
| Operation | Output | Cycles | Units per Cycle | Cycles per hour | Units Made | Materials Cost | Materials Cost per Unit | Taxes In | Taxes Out | Taxes Per unit | Net Cost per Unit | Unit Sales Price | Gross Sales | % Return | Profit / Loss per hour | Profit/Loss per day | Profit/Loss per 30 days | m3 in | m3 out |
| --------- | ------ | ------ | --------------- | --------------- | ---------- | -------------- | ----------------------- | -------- | --------- | -------------- | ----------------- | ---------------- | ----------- | -------- | ---------------------- | ------------------- | ----------------------- | ----- | ------ |

where:

- Operation is P0-P1, P1-P3, P0-P1-P2, etc. Operation should be unique across all views, as it will also be the identifier for a group of unit costs used later.
- Cycles is a user editable field representing the number of cycles per hour of the final output to model. This number can be used to model different factory configurations.
- Cycles per hour will almost always be 1, and is not user editable. it is .5 for certain P1-P4 configurations where it is not possible to support enough factories on one planet to build one unit per hour.

The individual operations for each view will define a set of product prices that can be used in higher level calculations, eg the P0-P1 unit cost from the extraction view can be used as the P1 input cost for P1-P4.

#### Export costs/prices

The unit cost of zero or more materials can be exported for use in other calculations. One value per material supported.

### Extraction

#### Possible Inputs

- P0
- P1
- P2

#### Operations

- P0-P1
- P0-P1-P2 - For producing P2 using P1 extracted on the same planet. Depending on the Import Material price selected, this can model P2 source one one planet, or split prduction with one P1 imported.
- P0-P1-P3
