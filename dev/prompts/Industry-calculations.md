# Eve Online Industry Calculations

## Purpose and status

Develop an auditable EVE Online industry calculation reference and the separate
EVE Argus integration needed to use it. A detailed manufacturing unit cost is one
output, not the boundary of the design.

This is a living specification, not authorization to implement every candidate
feature. Work through unresolved mechanics and policy choices before committing
to APIs. Deliver implementation in phases.

The initial compilation in
[`industry_base_calculations.py`](../../src/pfmsoft/eve_argus/calculations/industry_base_calculations.py)
is an inventory of possible calculations, not an authoritative implementation.
Its formulas, comments, defaults, stubs, and references to earlier attempts must
be independently evaluated. Other historical prompts are suggestions only.

### Agreed direction

- Specify the broad industry domain; implement it in phases.
- Cover manufacturing, reactions, invention, copying, ME research, and TE research.
- Limit production modeling to blueprint and reaction jobs. Price other inputs
  externally; do not model mining, planetary industry, reprocessing, hauling
  routes, or resource extraction.
- Prioritize explainable materials/fees/modifiers/rounding, market-aware profit
  analysis, and invention expected outcomes and confidence targets.
- Keep game rules separate from valuation assumptions and Argus data access.
- Record uncertain mechanics explicitly. Do not silently substitute plausible
  formulas or claim current in-game accuracy without evidence.
- Start with ME and TE research, not manufacturing or invention.
- Implement the reusable formulas in a **new file**, provisionally
  `src/pfmsoft/eve_argus/calculations/industry_formulas.py`. Do not modify,
  rename, replace, or import formulas from the original
  [`industry_base_calculations.py`](../../src/pfmsoft/eve_argus/calculations/industry_base_calculations.py).
  Add new mechanics incrementally only after their evidence and tests are ready.
- Develop proof-of-concept scripts under
  [`dev/proof-scripts/`](../proof-scripts/), separate from production adapters.
  Read-only access to the development Argus databases is approved.
- Initial work was prompt development and research notes only. The user has now
  authorized the ME comparison proof below. Keep candidate mechanics in proof
  scripts; defer the new reference module until formulas are verified.

## Deliverables and architectural boundary

### Reusable industry calculation module

App-agnostic means EVE-specific but independent of Argus, not independent of EVE.

- Pure, deterministic calculations with explicit typed inputs and results.
- No ESI requests, SQL, filesystem access, app configuration, rendering, or
  dependence on Argus resource objects.
- Accept caller-supplied blueprint, character, facility, price, and rules data.
  Do not depend on the shape of an ESI response or a particular SDE database.
- Separate basic formulas from composed job/scenario calculations.
- Include eligibility and modifier applicability rules where verified, without
  conflating a hypothetical estimate with an installable job.
- Use documented, typed, slotted, keyword-only dataclasses where appropriate.
- Explain units, valid ranges, formula order, precision, and rounding boundaries.
- Provide worked examples, source references, and tests suitable for readers
  implementing the same rules in other applications.
- Include `Game mechanics current as of <date>` in the new module docstring,
  using the actual mechanics verification date, not just the file creation date.
  Identify provisional or unverified areas separately so the note does not imply
  that every rule has been validated against the live game.
- Cite source web addresses in relevant formula docstrings, alongside clear
  explanations of mechanics, intermediate values, and known limitations.
- Keep game-rule version/effective-date metadata distinct from price timestamps.
  Pass changeable rates explicitly; do not inherit unverified legacy defaults.

This logical boundary does not require a separate package or a large framework.
Choose final module names and packaging after the calculation contracts stabilize.

### Separate EVE Argus integration

- Read existing static and dynamic datasets and normalize them into core inputs.
- Resolve IDs, names, actual blueprint instances, character profiles, facilities,
  rules, and price snapshots.
- Apply explicit user valuation policies and scenario selections.
- Handle fetching, caching, freshness, permissions, and missing data.
- Return structured results usable by multiple report/CLI renderers.
- Retain provenance sufficient to reproduce an estimate from the same snapshots.

Existing repository surfaces to investigate, not assumed complete adapters:

- [`static/read.py`](../../src/pfmsoft/eve_argus/static/read.py):
  blueprints, types, groups, categories, activities, and solar systems.
- [`static/models.py`](../../src/pfmsoft/eve_argus/static/models.py):
  blueprint activity materials, products, skills, and related static records.
- [`dynamic/read.py`](../../src/pfmsoft/eve_argus/dynamic/read.py):
  adjusted prices, orders/summaries, cost indices, corporation blueprints/jobs.
- [`dynamic/order_summary.py`](../../src/pfmsoft/eve_argus/dynamic/order_summary.py):
  existing market-summary calculations.
- [`cli/fetch/industry_systems.py`](../../src/pfmsoft/eve_argus/cli/fetch/industry_systems.py):
  existing cost-index fetch workflow.

Verify actual fields, coverage, and freshness before promising an output.
Character skills, implants, facility configuration, and access may require new
adapters or explicit manual inputs; their availability is not established here.

## Domain classification

Do not make one enum stand for activity, product family, and eligibility.
These dimensions overlap and answer different questions.

### Activities and their calculation contracts

| Activity | Principal inputs | Principal results |
|---|---|---|
| Manufacturing | Recipe, runs, output quantity per run, ME/TE, applicable modifiers, installation inputs | Rounded materials, product quantity, duration, installation charges |
| Reactions | Reaction recipe, runs, outputs, applicable skills/facility modifiers, installation inputs | Consumed inputs, all products, duration, installation charges |
| Invention | Input BPC, selected output, skills, datacores, optional decryptor, attempt count, facility | Success probability, attempt costs/time, successful BPC attributes, outcome distribution |
| Copying | Original blueprint, copy count, licensed runs per copy, copy-time data, modifiers | Number and attributes of copies, total licensed runs, duration, charges |
| ME research | Original blueprint, initial/target ME levels, research-time data, modifiers | Incremental levels, duration, charges, downstream material savings |
| TE research | Original blueprint, initial/target TE levels, research-time data, modifiers | Incremental levels, duration, charges, downstream time savings |

Use unambiguous terminology: manufacturing runs, invention attempts, copy count,
licensed runs per copy, and research levels are not interchangeable.
Research display percentages and internal level indices need explicit mapping.

### Product families and special cases

The following is a coverage checklist, not a verified list of distinct formulas
or hard-coded rules. Derive classification from supported static data where
possible; document exceptions rather than inferring restrictions from names.

| Family/overlay | Questions that must be resolved |
|---|---|
| T1 ships, modules, ammunition, drones, charges, rigs, and components | Shared formulas; output batch sizes; product-specific skill and rig applicability |
| T2 products and intermediate components | Invention dependency, advanced skills/materials, BPC runs and ME/TE, alternative BPC acquisition |
| T3 strategic cruisers and subsystems | Current invention routes and relic inputs, output selection/randomness, BPC attributes, specialized inputs |
| Capital, supercapital, and capital components | Separate component production from final hull eligibility; hull-specific security, facility, and sovereignty restrictions |
| Structures, structure components, deployables, and related equipment | Product-specific service/facility requirements; do not assume ship production rules |
| Faction and other limited-source blueprints | BPC acquisition cost, limited runs, research/copy eligibility, exceptions to ordinary T1/T2 assumptions |
| Biochemical, composite, and hybrid reactions | Reaction family, applicable service/rig/skill rules, security restrictions, consumables, and multiple outputs |
| Other or unclassified recipes | Preserve recipe and classification status; never silently exclude or apply guessed special rules |

### Eligibility is a separate result

Evaluate constraints for a specific activity, product, character, blueprint, and
facility combination. Return eligible, ineligible with reasons, or unknown with
missing evidence. Unknown must never be treated as eligible.

Track separately:

- Required skills and levels; prerequisites versus skills that improve outcomes.
- Clone-state restrictions and any applicable charges.
- Blueprint original/copy requirements, remaining licensed runs, and availability.
- Supported activity and product category; NPC station versus player structure,
  hull type, installed service, and relevant fitting/rig configuration.
- System security class and any finer security threshold, sovereignty, or
  infrastructure requirement. Do not reduce all restrictions to high/low/null.
- Access and installation permissions, online services, character job limits,
  blueprint/job conflicts, and other operational availability when observable.
- Material availability and affordability, distinct from intrinsic eligibility.

Allow explicit hypothetical scenarios when access or live availability is unknown,
but label them as estimates rather than installable plans.

## Input contracts and policies

### Recipe and blueprint

- Blueprint type ID and activity; distinguish blueprint item ID from type ID.
- Base material quantities, base time, product quantities, and output probabilities.
- Relevant required skills, copy/research limits, and activity-specific metadata.
- BPO/BPC status, ME, TE, licensed runs, and selected output where applicable.
- Requested runs or product quantity; when converting quantity to runs, show
  rounding, actual output, and unavoidable surplus.
- For invention: input consumption, datacores, decryptor, output BPC attributes,
  attempt definition, and failure consumption rules.

### Character and facility

- Relevant individual skill levels, clone state, implants, and other supported
  effects, with activity and product applicability.
- Facility/system identity and classification, applicable structure and rig
  effects, tax rates, and activity-specific system cost index.
- Preserve individual modifier sources. An already-effective factor may be
  supported, but must be mutually exclusive with the sources it replaces.
- Do not assume ME/TE, skills, or rigs apply identically to every activity.
- Treat facility fuel/overhead allocation as an explicit economic assumption,
  separate from game-charged job fees.

### Prices and valuation

- Keep ESI adjusted prices used for installation valuation separate from
  executable market prices, blueprint purchase costs, and inventory valuation.
- Every market valuation needs type, side, location/scope, quantity, snapshot time,
  currency/unit, and policy. State whether taxes/fees are included.
- Candidate policies: immediate purchase from sell orders; immediate liquidation
  into eligible buy orders; patient buy/sell order assumptions; explicit quotes.
- Patient orders are scenarios, not guaranteed fills. Their fill time and future
  prices are not determined by the current order book.
- Prefer quantity-aware order-book valuation for executable estimates. Check
  location, buy-order range/minimum-volume rules, and usable volume.
- A 5% summary can be a named indicative policy, not proof that the required
  quantity can trade at that price.
- Show partial fill, unfilled quantity, thin markets, stale data, and unavailable
  prices. Missing price is not zero; an incomplete total is not a complete quote.
- Inventory is not free: distinguish opportunity value, acquisition cost, and
  additional cash expenditure if inventory support is selected.
- Define blueprint purchase/run allocation, invention costs, sales taxes,
  broker/relisting assumptions, and external costs without double counting.

### Numeric and error contracts

- Choose decimal/fraction/integer representations based on verified mechanics;
  document precision before choosing the public numeric API.
- Specify percentage conventions: a displayed percent, fractional reduction,
  and effective multiplier must not be accepted interchangeably.
- Reject invalid quantities, levels, probabilities, rates, and nonfinite numbers.
  Distinguish invalid inputs from valid but ineligible scenarios.
- Missing data must produce explicit diagnostics or the repository-standard
  exception, not zero-valued costs, fabricated defaults, or silent exclusions.
- Preserve calculable partial results with explicit completeness status.

## Calculation work packages

### Deterministic game calculations

1. Normalize demand into job runs, output quantities, and surplus.
2. Calculate per-job materials with verified modifier order, intermediate
   precision, minimum quantities, and rounding. Splitting a job can change
   consumption; do not round an aggregated production tree as one job.
3. Calculate activity duration, including individual skill effects, applicable
   facility bonuses, copy semantics, and incremental research levels.
4. Calculate installation valuation: EIV and any activity-specific valuation
   basis. Verify invention, copying, reactions, and research independently.
5. Calculate each installation charge from its own verified basis, including
   applicability, per-run/job scaling, modifiers, and rounding.
6. Resolve invention success probability and successful BPC runs/ME/TE from
   verified activity rules, skills, and decryptor effects.
7. Compose job results without losing intermediate terms or provenance.

Do not carry over the existing SCC/alpha defaults, research multiplier table,
research valuation formula, or Python `round()` behavior without verification.
Verify low-quantity manufacturing minimums and job-size rounding in particular.

### Economic and probabilistic calculations

- Material purchase valuation and quantity-weighted realized output valuation.
- Complete per-job cost decomposition and unit cost per actual produced unit.
- Blueprint and invention allocation with an explicit denominator and allocation
  policy; keep economic cost distinct from cash required now.
- Gross revenue, net proceeds, profit, markup, and profit margin with named
  denominators; define undefined results when denominators are zero.
- Break-even sale price/volume and target-margin price under the chosen fee
  model. Order-book depth may require solving a piecewise revenue function,
  not dividing by a single headline price.
- Invention expected successes for a fixed attempt budget; probability of at
  least one or at least a requested number of successes.
- Minimum fixed attempts to reach a chosen success-count confidence, with
  explicit handling of impossible targets and probability endpoints.
- Expected attempts/cost to reach a success target under a stop-on-success
  policy, kept separate from fixed-budget distributions and spending limits.
- Conditional cost per successful BPC and per licensed manufacturing run.
  Distinguish an expected long-run allocation from a finite-batch realized cost;
  batches with zero successes do not have a finite realized unit cost.
- Model a binomial process only when attempts are independent with the same
  probability. Alternative output distributions require their own model.
- Confidence targets concern specified invention outcomes, not market fills,
  profit certainty, or a guarantee of success.

## Output catalogue

### First-class outputs

1. **Auditable job estimate:** recipe, demand, runs, all inputs/products,
   individual modifiers and applicability, unrounded terms, rounding steps,
   durations, fee bases/components, totals, and completeness/eligibility.
2. **Economic estimate:** material and blueprint/invention allocation, installed
   cost, unit cost, quantity-aware revenue, market fees, profit, margin, markup,
   break-even, required cash, and unpriced/unfilled quantities.
3. **Invention analysis:** probability inputs, resulting BPC attributes, per-attempt
   costs/time, expected outcomes, finite-budget distributions, confidence-target
   attempt counts, and zero-success risk.
4. **Explanation and provenance:** rule/source version, price/index snapshots,
   assumptions, omitted costs, uncertainty, warnings, and evidence status.

### Useful later outputs, not yet implementation commitments

- Scenario comparisons for facilities, characters, blueprint ME/TE, decryptors,
  job sizes, and market policies; compare equivalent demand and assumptions.
- Material totals and shopping lists, optional inventory shortfalls, remaining
  BPC runs, output surplus, and cargo volumes where type data supports them.
- Blueprint/reaction production trees and explicit buy/build decisions for
  intermediate inputs. Apply rounding at each actual job, detect cycles, and
  avoid allocating shared/intermediate costs twice.
- Duration, slot-hours, units per slot-hour, and profit per slot-hour. Elapsed
  completion time requires a scheduling assumption; summing job durations
  does not establish a parallel production schedule.
- ME/TE research incremental savings, payback in runs or time, and sensitivity
  to expected future production. TE value depends on whether time is a bottleneck.
- Sensitivity to material prices, sale prices, indices, and utilization;
  cost contribution rankings and bottleneck identification.
- Multiple-product revenue and cost allocation. Report the chosen allocation
  policy; do not invent a unique unit cost for co-products.

The reusable layer returns structured data; Argus may later render explanations,
tables, JSON/CSV, or other reports. Choose initial CLI/report formats separately.

## Evidence and validation

Maintain a rule register as mechanics are researched. For each rule record:

- Activity and scope, formula and named variables, units, and valid domain.
- Modifier applicability/order, rounding stages, minima/maxima, and exceptions.
- Exact source URL, relevant passage/data field, retrieval date, and applicable
  game version/date if known.
- Evidence status: documented, corroborated, in-game verified, or unresolved.
- Worked examples with recorded inputs and expected results.

Prefer current CCP documentation and published game/static data for what they
actually establish. ESI schemas establish response contracts, not necessarily
the complete calculation formula. Use maintained community references and
existing calculators as corroboration, not automatic authority. Resolve conflicts
explicitly and collect in-game examples where published evidence is insufficient.

Write tests before implementing each new function. Cover:

- Verified reference jobs across every supported activity and special category.
- Single versus multiple runs, output batches, job splitting, and tiny material
  requirements at rounding boundaries.
- No bonuses, combined bonuses, inapplicable bonuses, and prevention of duplicate
  application; research start/target boundaries and copy limits.
- Fee component bases and precision, including activity-specific exceptions.
- Invention probability 0/1, zero successes, confidence boundaries, and minimality
  of returned attempt counts. Do not use flaky random trials as the oracle.
- Missing/stale prices, absent adjusted prices, insufficient depth, order-range
  restrictions, partial fills, and zero-denominator economic outputs.
- Eligible, ineligible, and unknown configurations; all external dependencies
  mocked in integration tests.

Compare core results to recorded evidence, not merely the legacy implementation.
An unresolved rule must remain visibly unsupported or provisional.

## First implementation slice: ME and TE research

### Goal and artifact layout

For one selected blueprint and one explicit scenario, calculate each research
step from unresearched to maximum ordinary research:

- ME: ten transitions, `0 -> 1 -> ... -> 10` displayed percent.
- TE: ten transitions, `0 -> 2 -> ... -> 20` displayed percent.
- Both activities use internal step indices `0..10`. TE does not have twenty
  research steps; display percent is twice its step index.
- Produce four files: `me_research.csv`, `me_research.json`,
  `te_research.csv`, and `te_research.json`. These are two logical datasets,
  each exported in both formats.
- Use a blueprint/scenario-specific output directory to avoid overwriting
  other runs. Proposed generated-output root:
  `dev/proof-scripts/proof-output/industry-research/`.
- Proposed proof-script location: `dev/proof-scripts/industry-research/`.
  Proof scripts orchestrate inputs and exports, not a second implementation of
  the core formulas.

The primary comparison table represents ten **alternative zero-to-target jobs**
with frozen scenario inputs: `0 -> 1` through `0 -> 10` internal steps.
Calculate and round each installation independently; do not sum alternative rows.
Retain separately installed one-step jobs and their cumulative sums as a
secondary comparison, clearly distinguished from a single multilevel job.
One blueprint cannot run ME and TE jobs concurrently; these files describe
independent progressions, not a combined schedule.

Changing indices, prices, facility settings, or character bonuses during real
research can change actual costs/times. Cumulative totals are scenario estimates,
not predictions of future installation charges.

### Inputs to resolve

- Blueprint type ID/name, BPO eligibility, and separate `research_material.time`
  and `research_time.time` values from the static blueprint activity data.
  Do not assume equality when the supplied recipe data differs.
- Manufacturing recipe base quantities and each material's ESI adjusted price,
  used to compute unmodified manufacturing EIV. Do not use market sell prices,
  researched materials, or reprocessing composition.
- Separate ME and TE system cost indices for the selected system and snapshot.
  Use the supplied indices, not a reconstructed activity-share formula.
- Research level for ME and Metallurgy level for TE (verified in-game), plus
  Advanced Industry level for both. Check
  activity-specific required skills separately.
- Applicable time modifiers from the facility hull, research rigs, security
  scaling, and any relevant implants. Preserve the source of each factor.
- Separate installation-cost bonuses from time bonuses. A structure's duration
  reduction does not imply the same reduction in installation charges.
- Facility tax, SCC surcharge, applicable clone charge, and their verified
  research valuation bases. A zero facility tax does not imply zero other fees.
- Research activity materials, if present, must be investigated and shown.
  Keep installation fee and any externally priced consumables separate.
- Rules evidence date, static data version, adjusted-price/index snapshots,
  manually supplied settings, and explicit unknowns.

### Source notes and candidate mechanics

Sources below were consulted on **2026-10-27**. This is a research date, not a
claim that all mechanics have been verified current through that date.

| Source | What it establishes or suggests | Evidence limits / next action |
|---|---|---|
| [EVE University: Research](https://wiki.eveuniversity.org/Research) | BPO-only research; ten ME and TE steps; +1% ME and +2% TE per step; cumulative rank-one durations; research valuation; skill effects | Community documentation. Its facility-tax description conflicts with later CCP changes; do not adopt the entire page as current authority. |
| [CCP: Industry & 3rd Party Developers](https://www.eveonline.com/news/view/industry-3rd-party-developers) | Original adjusted-price valuation and exact per-step research multiplier fractions | Historical Crius-era design, including obsolete APIs and taxes. Fractions corroborate the duration table but still require present-day reference jobs. |
| [CCP: Viridian expansion notes, Tax Reforms](https://www.eveonline.com/news/view/viridian-expansion-notes) | Taxes moved from SCI-adjusted valuation to the underlying valuation; separate index/bonus, facility, SCC, and clone components | Primary source for the 2023 change. Confirm the research-specific valuation basis and subsequent rates; original SCC rate is not a current default. |
| [EVE University: Manufacturing, Total job cost](https://wiki.eveuniversity.org/Manufacturing#Total_job_cost) | Documents the additive fee structure, 0.25% NPC facility and alpha rates, and 4% SCC; links subsequent fee changes | Manufacturing context. Its 4% SCC must not override the user-confirmed 2% ME/TE research rate below; verify applicability separately for other activities. |
| [CCP: Version 21.05, 2023-07-06.1](https://www.eveonline.com/news/view/patch-notes-version-21-05) | Explicitly includes ME/TE research in the SCC increase from 0.25% to 0.75% | Historical rate, not a default. Shows why the original Viridian rate is insufficient. |
| [EVE University: Upwell structures, Engineering complexes](https://wiki.eveuniversity.org/Upwell_structures#Engineering_complexes) | Separate science job duration and installation-fee bonuses; additional research rigs | Verify individual hull/rig attributes and applicability against current static data and in-game configuration. |

Follow-up primary-source leads linked by the Manufacturing page:

- [CCP: Version 21.05 release notes, second page](https://www.eveonline.com/news/view/patch-notes-version-21-05-2):
  reported September 2023 SCC increase and cost-index changes.
- [CCP: Version 21.06 release notes](https://www.eveonline.com/news/view/patch-notes-version-21-06):
  reported 2024-02-01 SCC increase to 4%. The relevant subsection still needs
  direct inspection; the retrieved introductory excerpt did not establish it.
  This historical lead does not establish the current ME/TE research rate.

#### Current activity-specific surcharge rates

The user confirmed the following current rates on **2026-10-27**:

| Charge | Rate | Fractional input | Applicability |
|---|---|---|---|
| SCC surcharge | 2% | `0.02` | ME and TE research |
| SCC surcharge | 4% | `0.04` | Manufacturing |
| Alpha clone tax | 0.25% | `0.0025` | ME and TE research installed by an Alpha clone; zero for an Omega clone |

Use these as the current activity-specific scenario rates, with provenance recorded as
user-confirmed rather than independently verified from an online source.
They are separate from facility tax and from the `0.02` research valuation
multiplier, despite SCC currently having the same numeric value.
Keep rates explicit in formula inputs and exports so future changes do not
require changing the underlying formula. Do not extend the 2% SCC rate to other
industry activities without evidence. Manufacturing retains its separate 4% SCC
rate; do not use a single global SCC default for all industry activities.

#### Research progression and time

The Research page's rank-one duration table is **cumulative time to a level**,
not the duration of each incremental step. CCP's historical step multipliers
are exactly the differences between adjacent cumulative entries divided by 105:

| Target step | ME target % | TE target % | Cumulative rank-one seconds | Incremental rank-one seconds |
|---|---|---|---|---|
| 1 | 1 | 2 | 105 | 105 |
| 2 | 2 | 4 | 250 | 145 |
| 3 | 3 | 6 | 595 | 345 |
| 4 | 4 | 8 | 1,414 | 819 |
| 5 | 5 | 10 | 3,360 | 1,946 |
| 6 | 6 | 12 | 8,000 | 4,640 |
| 7 | 7 | 14 | 19,000 | 11,000 |
| 8 | 8 | 16 | 45,255 | 26,255 |
| 9 | 9 | 18 | 107,700 | 62,445 |
| 10 | 10 | 20 | 256,000 | 148,300 |

Let `D[n]` be the cumulative table entry, with `D[0] = 0`, and
`m[n] = (D[n] - D[n-1]) / 105`. Candidate unmodified step duration:

`base_activity_time_seconds * m[n]`

Verify that each static activity's `time` is the unmodified first-step duration
before using this mapping. Prefer explicit activity time over inferring rank
from product category. Do not replace the table with an approximate exponential.

Published skill reductions were noted as 5% per Metallurgy level for ME, 5% per
Research level for TE, and 3% per Advanced Industry level for both. That mapping
is reversed. The client lists Research + Advanced Industry as ME research bonus
skills and Metallurgy + Advanced Industry as TE research bonus skills, and the
ME duration was verified in-game with Metallurgy 5 trained but not applied.
Verified composition is multiplicative:
`(1 - 0.05 * activity_skill_level) * (1 - 0.03 * advanced_industry_level)`, where
`activity_skill_level` is Research for ME and Metallurgy for TE. Facility, rig,
and implant factors are still unverified, as is final/intermediate rounding.
The blueprint's existing ME or TE percentage is not itself a research-time bonus.

#### Research valuation and fees

The two research sources support a candidate per-step research valuation:

`research_valuation[n] = manufacturing_EIV * 0.02 * m[n]`

Here `manufacturing_EIV` is the sum of unmodified manufacturing material quantity
times adjusted price. This research valuation is distinct from manufacturing
EIV and from skill-modified elapsed research time.

The published candidate valuation has no blueprint-rank factor: longer base
research time must not automatically multiply the fee valuation. Do not feed
the character/facility-modified duration into a process-time-value formula.
Confirm these distinctions with recorded in-game jobs.

The post-Viridian candidate fee structure is:

`research_valuation * (activity_SCI * applicable_cost_factor
                      + facility_tax_rate + SCC_rate + applicable_clone_rate)`

Keep the four components visible. Verify that the research valuation is indeed
the common basis for each charge, whether any components have exceptions, and
where rounding occurs. In particular:

- The Research wiki page says facility tax is a percentage of index-adjusted
  job cost; CCP's later tax reform explicitly changes that approach.
- The old formula file uses rounded process-time value and per-component
  Python rounding; neither is evidence of current in-game rounding.
- Use the user-confirmed SCC and Alpha rates above for ME/TE scenarios. Their
  valuation bases and rounding still require verification, as do NPC and
  player-set facility taxes. Do not substitute historical rates or hard-code
  rates into the underlying formula.

#### Output contract

Each dataset has ten ordered rows, with these field groups:

- Identity: blueprint type ID/name, scenario ID, activity, target step index,
  starting/target display percentage.
- Time: unmodified step seconds, effective time factors, step duration seconds,
  cumulative duration seconds.
- Cost basis: manufacturing EIV, research multiplier, research valuation,
  activity SCI, installation-cost factor, and individual tax/surcharge rates.
- Charges: index-based installation component, facility tax, SCC, clone charge,
  step installation total, and cumulative installation total in ISK.
- Additional activity materials/costs and combined economic totals when relevant,
  without labeling installation fees alone as an all-inclusive research cost.
- Evidence/completeness status and diagnostics; rules date and source snapshot
  identifiers. Unknown charges must not be serialized as zero or complete totals.

JSON should carry shared scenario metadata, citations, units, rounding policy,
and an ordered `steps` array. CSV should repeat essential scenario/traceability
fields on each row and use stable flat columns; do not emit Python object reprs.
Define serialization of multiple modifier/material entries before freezing the
CSV schema. Represent exact decimal money/rates as decimal strings in JSON and
decimal text in CSV; use integers for finalized seconds and step indices.
Finalize precision and column names after verifying game rounding.

For incremental outputs, cumulative values sum separately rounded one-step job
results. Primary `0 -> n` outputs calculate each multilevel installation as one
job; do not assert identical totals across different job boundaries.
No elapsed time for player delays or delivery/reinstallation is assumed.

### Proof workflow and acceptance

1. Inspect relevant static/dynamic data read-only, preferably through existing
   readers on SQLite connections opened with URI `mode=ro`. No migrations,
   updates, automatic fetch/store, or app bootstrap that can write to these DBs.
2. Select a simple BPO with complete adjusted prices and both research activities.
   Record the exact database/snapshot inputs and manually supplied scenario.
3. Capture in-game ME and TE quotes, including at least a later-level job,
   one multi-level job for comparison, and a facility with known modifiers.
   User-supplied quotes/screenshots are acceptable; do not fabricate observations.
4. Resolve valuation, modifier, and rounding discrepancies before adding a formula
   to the new reference module. Keep unresolved hypotheses in this prompt.
5. Add red/green tests, documented formulas with source URLs, and proof scripts
   that export the four files using those formulas.
6. Verify exactly ten rows per activity, ME endpoints 1/10 and TE endpoints 2/20,
   correct starting percentages, ordering, and agreement between CSV and JSON.
   Check cumulative sums, units, precision, missing-data behavior, and distinction
   between independently installed steps and a multilevel job.
7. Test a second blueprint with different base research time, zero/max skill
   levels, a changed index/tax, and facility time versus cost bonuses separately.
   Confirm the original formula file remains unchanged.

### First comparison run: Antimatter Charge S, Osmeden, Alpha

The user selected ME-only comparison for Antimatter Charge S Blueprint in an NPC
station in Osmeden, using an Alpha clone. Generated on 2026-10-27 using
[`compare_me_research.py`](../proof-scripts/industry-research/compare_me_research.py).
This is a comparison of hypotheses, not evidence that any matches in-game fees.

- Blueprint type ID `1137`; system ID `30003831`; static build `3607705`.
- Base ME research time: `105` seconds.
- Manufacturing materials/adjusted prices: 204 Tritanium at 3.14 ISK,
  17 Pyerite at 13.85 ISK, and 1 Nocxium at 581.95 ISK.
- Manufacturing EIV: `1457.96` ISK.
- Adjusted-price response `41`, received `2026-10-27T19:33:05.12643423Z`.
- Cost-index response `42`, received `2026-10-27T19:33:19.485097162Z`;
  stored ME index `0.0525` (5.25%).
- SCC `0.02`, Alpha `0.0025`; assumed NPC facility tax `0.0025` and
  installation-cost factor `1`. No character-adjusted durations: skill levels
  and implants were not supplied.

The initial comparison exports contained thirty rows: ten independent one-step jobs for
each of three PTV candidates:

1. `EIV * 0.02 * level_multiplier`.
2. `EIV * 0.02 * unmodified_step_seconds / blueprint_base_research_seconds`.
3. `EIV * 0.02 * unmodified_step_seconds / 105`.

All three agree for this rank-one blueprint. A different-rank blueprint is needed
to distinguish the fixed-105 and blueprint-normalized hypotheses. The first two
are algebraically equivalent under the assumed time progression.

Exports also show raw fee components, rounding each component versus rounding
the aggregate, whole-ISK and cents policies, and ceiling PTV before applying
charges. None is selected as authoritative. Example `0 -> 1`: PTV `29.1592` ISK,
raw total `2.259838` ISK, component-cents total `2.25`, aggregate-cents total
`2.26`, or `2.34` when PTV is first ceiled and components rounded to cents.

Outputs are in
`dev/proof-scripts/proof-output/industry-research/antimatter-charge-s-osmeden-alpha-2026-10-27/`
as `me_research.csv` and `me_research.json`. JSON includes recipe and snapshot
provenance. No TE files were requested for this comparison.

Comparison limitations: the database stores SCI to four decimal places; live
quotes may differ due to that quantization or later index/price updates.
Record the in-game starting/target ME, fee component tooltip values, displayed
total, facility tax, and quote timestamp. Actual duration is also useful if
accompanied by the character's skill/implant information. Do not compare a
multilevel installation to the sum of separately rounded one-step jobs as if
their rounding boundaries were identical.

#### Zero-to-target comparison update

The user reports on 2026-10-27 that the PTV values match the game data checked so
far, but the client quotes from zero to the selected level, not individual steps.
This is qualitative corroboration, not a recorded fixture with exact observations
or a way to distinguish the coincident rank-one PTV candidates.

The primary CSV/JSON now compare `0 -> 1` through `0 -> 10` as alternative single
installations. PTV, duration, and all fee/rounding candidates are calculated for
the whole requested interval. Original incremental comparisons remain under
`incremental/` in the same output directory. In primary files, cumulative
component-cents cost equals the row's job total, not a sum of alternative quotes.

#### Reported in-game ME 0 -> 10 comparison

On 2026-10-27 the user reported these displayed values for the same comparison:

- PTV: `71086` ISK, displayed/reported as an integer.
- `5510` ISK, described as "total taxes".
- `1778` ISK, described as "taxes".

The user subsequently clarified the game's UI labels:

- **Gross Job Cost**: the index-based charge after applicable bonuses.
- **Total Taxes**: the combined facility tax, SCC surcharge, and Alpha tax.
- **Total Job Cost**: Gross Job Cost plus Total Taxes.

The reported `5510` ISK is Total Job Cost and `1778` ISK is Total Taxes,
leaving `3732` ISK Gross Job Cost. Use these labels in comparison outputs.

For now, model bonuses as discounts against `PTV * SCI`:

`gross_job_cost = PTV * SCI * (1 - effective_cost_discount)`

Equivalently, the existing `installation_cost_factor` is
`1 - effective_cost_discount`. Do not subtract a raw structure percentage
directly from SCI or apply the cost discount to taxes.
The user identifies a Structure Role Bonus for player-built facilities as one
known bonus category. Other bonus categories and their composition remain to
be investigated; this is a working model, not verification of every modifier.
The current NPC comparison assumes no cost discount.

The proof gives unrounded PTV `71092.906666...` ISK, about `6.91` ISK or `0.0097%`
higher than the reported integer. Its whole-ISK, per-component half-up rounding
candidate gives total `5510` ISK and facility/SCC/Alpha charges summing to
`1778` ISK. This agreement supports that candidate for estimates but does not
establish the game's exact rounding algorithm. The source of the small PTV
difference is unresolved; do not assume it is solely display rounding or adjust
formula constants to force agreement.

The user accepts close estimates; exact arithmetic parity with the client is
desirable but not required. No general numeric tolerance has been agreed.
Retain documented precision, provisional rounding labels, and these observations
as comparison evidence rather than asserting exact correctness across blueprints.

### Second comparison run: Large Auxiliary Nano Pump I, Osmeden, Alpha

This blueprint (type `25897`) has a base ME step time of `1575` seconds, 15x the
rank-one `105` seconds, so it discriminates between PTV candidates. Manufacturing
EIV from the dev snapshot was `2,874,145.02` ISK.

On 2026-10-27 the user confirmed the in-game PTV matches the level-multiplier
(blueprint-time-normalized) candidate, e.g. `140,148,786` ISK for ME 0 -> 10.
The fixed-105 candidate (15x larger) is rejected. Base research time therefore
changes duration but not PTV; PTV is
`EIV * 0.02 * (D[target] - D[start]) / 105` using rank-one cumulative seconds.

The in-game ME SCI had moved to `6.38%` while the dev snapshot still held
`5.25%` (live data lags the cached snapshot). Recomputed at `6.38%`, ME 0 -> 10
gives Gross Job Cost `8,941,493`, Total Taxes `3,503,720`, and Total Job Cost
`12,445,213` ISK. Fee comparisons must use the SCI shown in-game at quote time.

For ME 0 -> 5, the user reported PTV and Total Taxes (`45,987`) as matching, but
Gross Job Cost `117,321` and Total Job Cost `163,308`, versus `117,357` /
`163,344` ISK at exactly `6.38%`. The implied SCI is about `0.0637804`
(`117321 / 1839452.81`), consistent with the client displaying a rounded value of a
more precise index. The user accepts this as close enough. Use more precise SCI
values when available; displayed two-decimal percentages limit Gross Job Cost
accuracy to about +/-0.005% of PTV.

#### Duration and ME/TE cost parity

The user states ME and TE research job costs are identical for the same level
range; the same PTV and fee model applies to both, with only the activity SCI
(and therefore index value) potentially differing.

Alpha clones currently receive no research time bonus. The user reported the
unbonused in-game duration for Large Auxiliary Nano Pump I ME 0 -> 10 as
`44d 10h 40m`. The model gives
`1575 * 256000 / 105 = 3,840,000 s = 44d 10h 40m 0s`, an exact match. This
verifies `duration = base_step_seconds * D[target] / 105` for an unbonused
Alpha in an NPC station. Skill, implant, and structure time modifiers remain
unverified.

On 2026-10-27 an Omega character with Research 5 and Advanced Industry 5, in an
NPC station in Sheroo (displayed SCI `5.56%`), reported Large Auxiliary Nano Pump I
0 -> 10 as `28d 8h` with a displayed total skill bonus of `-36.3%`. Skill
modifiers compose multiplicatively:
`(1 - 0.05*5) * (1 - 0.03*5) = 0.75 * 0.85 = 0.6375` (`-36.25%`, displayed as
`-36.3%`), giving `3,840,000 * 0.6375 = 2,448,000 s = 28d 8h 0m`, an exact
match. Additive composition (`-40%`, `25d 14h 24m`) is rejected. This was an
**ME** research job with Metallurgy 5 also trained, so Research (5%/level), not
Metallurgy, reduces ME research time. The client lists Metallurgy + Advanced
Industry as TE research bonus skills. Static `research_time` for this blueprint is
also `1575` s, so the model predicted TE 0 -> 20% (ten steps) at `28d 8h` with
Metallurgy 5 + Advanced Industry 5, identical to ME. On 2026-10-27 the user
confirmed the in-game TE and ME research times match, verifying the TE duration
formula and the Metallurgy -> TE mapping.

On 2026-10-27 the same character quoted TE 0 -> 20% for Large Auxiliary Nano Pump
I in a player-owned structure with a listed time role bonus of `-20%` and a
character skill bonus of `-36.3%`. In-game duration was `22d 16h`. The model
`3,840,000 * 0.6375 * (1 - 0.20) = 1,958,400 s = 22d 16h 0m` matches exactly.
The structure time role bonus therefore multiplies with the skill factor;
additive composition (`-56.25%`, `19d 10h 40m`) is rejected. Rig, security-band,
and implant time factors remain unverified.

The user clarified the same structure lists a separate `-4%` structure cost bonus,
shown within the Gross Job Cost subtotal; the `-20%` role bonus applies only to
time. This is consistent with the working model
`gross_job_cost = PTV * SCI * (1 - 0.04)`, with taxes not discounted. The fee
values for this quote have not yet been compared numerically, so the cost
discount remains provisional. Model time and cost structure bonuses as separate
inputs.

Reported fees for that quote (Sheroo, TE SCI displayed `5.98%`, facility tax
`0.25%`, SCC `2%`, Omega so no Alpha tax), PTV `140,148,785.74` ISK:

- Gross Job Cost `8,044,842` ISK. Model `PTV * 0.0598 * 0.96 = 8,045,661`
  (+819, +0.010%). Implied SCI `0.0597939`, which rounds to the displayed
  `5.98%`, so the residual is consistent with hidden SCI precision. Without the
  discount the model gives `8,380,897`, so the `-4%` structure cost bonus applying
  to `PTV * SCI` is supported.
- Total Taxes `3,153,347` ISK. Model raw `PTV * 0.0225 = 3,153,347.68`, so the
  undiscounted taxes-on-PTV model is supported. The client value matches
  truncating the aggregate; per-component half-up gives `3,153,348` and
  per-component floor `3,153,346`. Compare this with the Antimatter case, where
  per-component half-up matched. The game's rounding rule remains unresolved;
  treat ±1-2 ISK differences as rounding.

Implant and research-rig data are not currently available for in-game
comparison. Per the user's expectation, model implant and rig (including any
security-band scaling) time and cost modifiers as additional independent
multiplicative factors, like the verified skill and structure factors. Label this
as an assumption in code and docs until verified.
Implant and structure time modifiers remain unverified.

### Reference module: `industry_formulas.py`

On 2026-10-27 the verified ME/TE research mechanics above were implemented in
`src/pfmsoft/eve_argus/calculations/industry_formulas.py`, which is app-agnostic,
pure, and dependency-free. It provides the following:

- Research tables and current rates as documented constants.
- `research_level_multiplier`, `material_efficiency_percent`,
  `time_efficiency_percent`, `estimated_item_value`,
  `research_process_time_value`, `research_skill_time_factor`,
  `research_duration_seconds`, `bonus_to_factor`, `job_cost`, and
  `round_isk_half_up`.
- A `JobCost` dataclass with in-game labels and a provisional
  `to_whole_isk()` that rounds each charge half up.

Tests in `tests/pfmsoft/eve_argus/calculations/test_industry_formulas.py` use
the recorded in-game quotes as expected values. The legacy
`industry_base_calculations.py` file remains unchanged. Next: CSV/JSON ME and TE
exports in eve-argus integration code, built on this module.

## Phased delivery and decision gates

1. **Specification and evidence:** refine this document, settle initial output
   contracts and family coverage, research rules, and collect reference examples.
   Start with the ME/TE slice above and its four proof exports.
2. **Research foundation, then broader deterministic calculations:** implement
   the verified ME/TE mechanics in the new module first. Extend materials,
   outputs, duration, valuation,
   charges, and eligibility for agreed activity/family slices, with traceable tests.
   Clearly enumerate supported versus unsupported combinations.
3. **Invention:** implement verified probability/BPC rules, expected-cost and
   confidence calculations, and explicit manufacturing-cost linkage.
4. **Argus economic scenarios:** wire snapshot adapters, price policies, depth-aware
   valuation, fee assumptions, and initial structured/report outputs. Verify data
   coverage before promising live character/facility resolution.
5. **Optional composition:** select production trees, comparisons, inventory,
   research payback, or throughput features based on demonstrated usefulness.

Each phase must leave a usable, documented, tested supported subset. Do not
present an incomplete broad API with success-shaped stubs.

## Next discussion topics

- Which blueprint, system, skills, and facility should anchor the first ME/TE
  proof? What in-game quotes can establish fee and duration rounding?
- Which research rigs and implants should the first slice explicitly support?
- Should purchase/sale defaults mean immediate execution, patient orders, or
  side-by-side scenarios? What location and freshness policies are acceptable?
- How should bought BPCs, owned BPOs, research expense, and invented BPCs be
  valued and amortized?
- Should the first invention analysis emphasize a fixed attempt budget,
  stop-on-success planning, or both? Which confidence targets should examples use?
- What observed character/facility data is available, and what should users
  supply manually? How should unverified configuration be presented?
- Which output should Argus expose first: a single-job explanation, a
  product-profitability table, or an invention-to-manufacturing comparison?
