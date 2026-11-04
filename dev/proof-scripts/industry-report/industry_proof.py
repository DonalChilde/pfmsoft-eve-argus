"""Isolated BPC-only production planning and Decimal report economics.

NPC Osmeden, Omega, skills 5, no implants or decryptors. Source-backed mechanics
are imported from the project; composition and economic policy stay in this proof.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from pfmsoft.eve_argus.calculations import industry_formulas as formulas
from pfmsoft.eve_argus.models.market_hubs import MARKET_HUBS

D = Decimal
ZERO = D(0)
DEFAULT_SALES_TAX_RATE = D("0.036")
DEFAULT_BROKER_FEE_RATE = D("0.01")
Strategy = Literal["buy-all-inputs", "make-all-inputs"]


@dataclass(slots=True, kw_only=True, frozen=True)
class Item:
    """Product or material identity; family comes from static classification."""

    type_id: int
    name: str
    portion_size: int = 1
    family: Literal["ordinary", "t2", "t2-ship-rig", "unsupported"] = "ordinary"
    market_path: str | None = None
    volume: Decimal | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class Material:
    """Unmodified static recipe quantity."""

    type_id: int
    quantity: int


@dataclass(slots=True, kw_only=True, frozen=True)
class Blueprint:
    """Single-output manufacturing recipe with optional source invention route."""

    blueprint_id: int
    product_id: int
    output: int
    max_runs: int
    materials: tuple[Material, ...]
    manufacturing_seconds: int
    copying_seconds: int | None
    science_skills: int = 0
    copying_materials: tuple[Material, ...] = ()


@dataclass(slots=True, kw_only=True, frozen=True)
class Invention:
    """Source BPO route to one successful invented BPC."""

    source_blueprint_id: int
    target_blueprint_id: int
    base_probability: Decimal
    licensed_runs: int
    seconds: int
    materials: tuple[Material, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class Original:
    """One real BPO instance; preserve its ME/TE pair."""

    blueprint_id: int
    item_id: int
    me: int
    te: int


@dataclass(slots=True, kw_only=True, frozen=True)
class Source:
    """Source receipt/freshness, without implying cross-source alignment."""

    label: str
    reference: str
    received_at: str
    expires_at: str | None = None
    argus_expires_at: str | None = None

    def freshness(self, *, now: datetime) -> str:
        """Prefer Argus expiry and preserve unknown expiry."""
        expiry = self.argus_expires_at or self.expires_at
        if expiry is None:
            return "unknown"
        instant = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError(f"Expiry lacks timezone: {self.label}")
        return "stale" if instant <= now else "fresh"


@dataclass(slots=True, kw_only=True, frozen=True)
class Market:
    """Station order prices/depth plus regional history; missing values stay None."""

    station_id: int
    type_id: int
    buy: Decimal | None = None
    sell: Decimal | None = None
    buy_depth: int | None = None
    sell_depth: int | None = None
    history_price: Decimal | None = None
    daily_sales: Decimal | None = None
    history_start: str | None = None
    history_end: str | None = None
    days_present: int = 0


@dataclass(slots=True, kw_only=True)
class Inputs:
    """Normalized explicit inputs shared by synthetic and read-only adapters."""

    items: dict[int, Item]
    blueprints: dict[int, Blueprint]
    inventions: tuple[Invention, ...]
    originals: tuple[Original, ...]
    reaction_products: set[int]
    adjusted_prices: dict[int, Decimal]
    input_prices: dict[int, Decimal]
    indices: dict[str, Decimal]
    markets: dict[tuple[int, int], Market]
    sources: list[Source]
    scope: str
    warnings: list[str] = field(default_factory=list[str])


@dataclass(slots=True, kw_only=True, frozen=True)
class Charges:
    """Unrounded monetary components, each applied to activity PTV."""

    eiv: Decimal | None
    ptv: Decimal | None
    index: Decimal | None
    facility: Decimal | None
    scc: Decimal | None

    @property
    def total(self) -> Decimal | None:
        """Do not present a partial fee as a complete charge."""
        return known_sum((self.index, self.facility, self.scc))


@dataclass(slots=True, kw_only=True, frozen=True)
class Job:
    """Copy, invention, or manufacturing step with input blueprint references."""

    job_id: str
    activity: str
    blueprint_id: int
    runs: int
    me: int
    te: int
    duration: Decimal
    charges: Charges
    dependencies: tuple[str, ...] = ()
    original_item_id: int | None = None
    licensed_runs: int | None = None
    remaining_runs: int = 0
    inputs: tuple[Material, ...] = ()

    @property
    def total_fee(self) -> Decimal | None:
        """Installation fee only; input values are counted in the shopping list."""
        return self.charges.total


@dataclass(slots=True, kw_only=True)
class Node:
    """Aggregated manufacturing demand; surplus has no residual-value credit."""

    type_id: int
    blueprint_id: int
    required: int
    produced: int
    me: int
    te: int
    materials: tuple[Material, ...]
    job_ids: tuple[str, ...]
    cost: Decimal | None = None
    probability: Decimal | None = None
    attempts_per_bpc: int = 0
    bpcs: int = 0
    preparation_cost: Decimal | None = None


@dataclass(slots=True, kw_only=True, frozen=True)
class Purchase:
    """External input, valued only at Jita station sell 5%."""

    type_id: int
    quantity: int
    unit_price: Decimal | None
    reason: str

    @property
    def cost(self) -> Decimal | None:
        """Unknown prices invalidate the total rather than becoming free."""
        return None if self.unit_price is None else self.unit_price * self.quantity


@dataclass(slots=True, kw_only=True, frozen=True)
class Outcome:
    """One station sale-price basis, with a fixed production cost."""

    station_id: int
    basis: str
    price: Decimal | None
    depth: int | None
    gross: Decimal | None
    fees: Decimal | None
    sales_tax: Decimal | None
    broker_fee: Decimal | None
    net_per_unit: Decimal | None
    profit_per_unit: Decimal | None
    total_profit: Decimal | None
    return_pct: Decimal | None
    status: str


@dataclass(slots=True, kw_only=True)
class Plan:
    """One product/strategy reference batch, retained even if incomplete."""

    type_id: int
    strategy: Strategy
    reference_runs: int
    produced: int = 0
    nodes: list[Node] = field(default_factory=list[Node])
    jobs: list[Job] = field(default_factory=list[Job])
    shopping: list[Purchase] = field(default_factory=list[Purchase])
    warnings: list[str] = field(default_factory=list[str])
    outcomes: list[Outcome] = field(default_factory=list[Outcome])
    total: Decimal | None = None
    unit_cost: Decimal | None = None

    @property
    def status(self) -> str:
        """Only complete production costs qualify for profit calculations."""
        return "complete" if self.total is not None else "incomplete"

    @property
    def anchor(self) -> str:
        """Stable cross-format and CSV detail link."""
        return f"production-{self.type_id}-{self.strategy}"


@dataclass(slots=True, kw_only=True, frozen=True)
class Report:
    """Canonical model rendered once into all three artifacts."""

    data: Inputs
    plans: tuple[Plan, ...]
    generated_at: datetime
    sales_tax_rate: Decimal = DEFAULT_SALES_TAX_RATE
    broker_fee_rate: Decimal = DEFAULT_BROKER_FEE_RATE


class Unavailable(ValueError):
    """Known missing or unsupported route; keep an explicitly incomplete row."""


def known_sum(values: Iterable[Decimal | None]) -> Decimal | None:
    """Sum monetary components only when every required value is known."""
    result = D(0)
    for value in values:
        if value is None:
            return None
        result += value
    return result


def rounded_attempts(probability: Decimal | Fraction) -> int:
    """Budget ceil(1/p) per successful BPC, without a confidence guarantee."""
    if isinstance(probability, Decimal) and not probability.is_finite():
        raise ValueError("Invention probability must be finite and in (0, 1].")
    if not 0 < probability <= 1:
        raise ValueError("Invention probability must be finite and in (0, 1].")
    return (Fraction(1) / Fraction(probability)).__ceil__()


def split_runs(*, runs: int, limit: int) -> tuple[int, ...]:
    """Split licensed runs into positive whole jobs, leaving no phantom runs."""
    if runs < 1 or limit < 1:
        raise ValueError("Runs and BPC limits must be positive.")
    full, remainder = divmod(runs, limit)
    return (limit,) * full + ((remainder,) if remainder else ())


class Planner:
    """Compose the production DAG without fetching, writing, or changing sources."""

    def __init__(self, data: Inputs) -> None:
        """Index all routes and select actual original instances."""
        self.data = data
        self.routes: dict[int, list[Blueprint]] = defaultdict(list)
        for bp in data.blueprints.values():
            if bp.output < 1 or bp.max_runs < 1:
                raise ValueError(f"Invalid recipe output/copy limit: {bp.blueprint_id}")
            self.routes[bp.product_id].append(bp)
        self.originals: dict[int, Original] = {}
        for original in sorted(data.originals, key=lambda o: (-o.me, -o.te, o.item_id)):
            self.originals.setdefault(original.blueprint_id, original)

    def route(self, type_id: int) -> Blueprint:
        """Require one supported manufacturing route instead of guessing."""
        item = self.data.items.get(type_id)
        if item is None:
            raise Unavailable(f"Missing static type {type_id}.")
        if item.family == "unsupported" or type_id in self.data.reaction_products:
            raise Unavailable(f"Unsupported manufacturing family for {type_id}.")
        candidates = self.routes.get(type_id, [])
        if len(candidates) != 1:
            raise Unavailable(
                f"Missing or ambiguous manufacturing route for {type_id}."
            )
        return candidates[0]

    def blueprint_access(
        self, bp: Blueprint
    ) -> tuple[Original, Invention | None, int, int]:
        """Resolve BPO copying or a unique owned-BPO invention route."""
        item = self.data.items[bp.product_id]
        if item.family.startswith("t2"):
            routes = [
                route
                for route in self.data.inventions
                if route.target_blueprint_id == bp.blueprint_id
                and route.source_blueprint_id in self.originals
            ]
            if len(routes) != 1:
                raise Unavailable(
                    f"Missing BPO or ambiguous invention route for {bp.product_id}."
                )
            route = routes[0]
            expected_runs = 1 if item.family == "t2-ship-rig" else 10
            if route.licensed_runs != expected_runs:
                raise Unavailable(
                    f"Unexpected invented BPC runs for {bp.product_id}: "
                    f"{route.licensed_runs}, expected {expected_runs}."
                )
            return self.originals[route.source_blueprint_id], route, 2, 4
        original = self.originals.get(bp.blueprint_id)
        if original is None:
            raise Unavailable(f"Missing owned BPO for {bp.product_id}.")
        return original, None, original.me, original.te

    def charges(
        self, bp: Blueprint, *, activity: str, runs: int, plan: Plan
    ) -> Charges:
        """Use Decimal for EIV/PTV/fees; no binary-float currency conversion."""
        components: list[Decimal] = []
        for material in bp.materials:
            adjusted = self.data.adjusted_prices.get(material.type_id)
            if adjusted is None:
                plan.warnings.append(
                    f"Missing adjusted price for {material.type_id} (EIV {bp.blueprint_id})."
                )
            else:
                components.append(adjusted * material.quantity)
        eiv = sum(components, D(0)) if len(components) == len(bp.materials) else None
        index = self.data.indices.get(activity)
        if index is None:
            plan.warnings.append(f"Missing Osmeden {activity} cost index.")
        multiplier = D(1) if activity == "manufacturing" else D("0.02")
        ptv = None if eiv is None else eiv * runs * multiplier
        return Charges(
            eiv=eiv,
            ptv=ptv,
            index=None if ptv is None or index is None else ptv * index,
            facility=None if ptv is None else ptv * D("0.0025"),
            scc=None if ptv is None else ptv * D("0.04"),
        )

    def copy_jobs(
        self,
        bp: Blueprint,
        *,
        original: Original,
        runs: int,
        prefix: str,
        plan: Plan,
    ) -> list[Job]:
        """Size copies and consume copying materials per licensed BPC run."""
        if bp.copying_seconds is None:
            raise Unavailable(f"No copying activity for BPO {bp.blueprint_id}.")
        jobs: list[Job] = []
        for i, count in enumerate(split_runs(runs=runs, limit=bp.max_runs), 1):
            job = Job(
                job_id=f"{prefix}-copy-{i}",
                activity="copying",
                blueprint_id=bp.blueprint_id,
                original_item_id=original.item_id,
                runs=count,
                licensed_runs=count,
                inputs=tuple(
                    Material(type_id=m.type_id, quantity=m.quantity * count)
                    for m in bp.copying_materials
                    if m.quantity
                ),
                me=original.me,
                te=original.te,
                charges=self.charges(bp, activity="copying", runs=count, plan=plan),
                duration=D(
                    str(
                        formulas.copying_duration_seconds(
                            base_seconds=bp.copying_seconds,
                            runs_per_copy=count,
                            copies=1,
                            time_factors=(
                                formulas.science_copy_time_factor(level=5),
                                formulas.advanced_industry_time_factor(level=5),
                            ),
                        )
                    )
                ),
            )
            jobs.append(job)
        return jobs

    def node(
        self, *, type_id: int, required: int, plan: Plan
    ) -> tuple[Node, list[Job], dict[int, int]]:
        """Size one aggregated product demand and all BPC preparation."""
        bp = self.route(type_id)
        original, invention, me, te = self.blueprint_access(bp)
        runs = (required + bp.output - 1) // bp.output
        limit = min(bp.max_runs, invention.licensed_runs) if invention else bp.max_runs
        batches = split_runs(runs=runs, limit=limit)
        jobs: list[Job] = []
        extras: dict[int, int] = defaultdict(int)
        probability: Decimal | None = None
        attempts_per_bpc = 0
        if invention:
            if not invention.base_probability.is_finite() or not (
                0 < invention.base_probability <= 1
            ):
                raise Unavailable(f"Unavailable invention probability for {type_id}.")
            # Exact rational skill multiplier avoids ceil errors near integer ratios.
            chance = min(
                Fraction(1), Fraction(invention.base_probability) * Fraction(35, 24)
            )
            probability = D(chance.numerator) / D(chance.denominator)
            attempts_per_bpc = rounded_attempts(chance)
            attempts = len(batches) * attempts_per_bpc
            source = self.data.blueprints.get(invention.source_blueprint_id)
            if source is None:
                raise Unavailable(f"No source manufacturing recipe for {type_id}.")
            copies = self.copy_jobs(
                source,
                original=original,
                runs=attempts,
                prefix=f"bpc-{type_id}",
                plan=plan,
            )
            jobs.extend(copies)
            for i, copy in enumerate(copies, 1):
                consumed = tuple(
                    Material(type_id=m.type_id, quantity=m.quantity * copy.runs)
                    for m in invention.materials
                )
                jobs.append(
                    Job(
                        job_id=f"invent-{type_id}-{i}",
                        activity="invention",
                        blueprint_id=source.blueprint_id,
                        runs=copy.runs,
                        me=2,
                        te=4,
                        licensed_runs=invention.licensed_runs,
                        dependencies=(copy.job_id,),
                        inputs=consumed,
                        charges=self.charges(
                            bp, activity="invention", runs=copy.runs, plan=plan
                        ),
                        duration=D(
                            str(
                                formulas.invention_duration_seconds(
                                    base_seconds=invention.seconds,
                                    attempts=copy.runs,
                                    time_factors=(
                                        formulas.advanced_industry_time_factor(level=5),
                                    ),
                                )
                            )
                        ),
                    )
                )
            bpc_dependencies = tuple(
                job.job_id for job in jobs if job.activity == "invention"
            )
        else:
            jobs.extend(
                self.copy_jobs(
                    bp, original=original, runs=runs, prefix=f"bpc-{type_id}", plan=plan
                )
            )
            bpc_dependencies = ()
        prep_ids = {job.job_id for job in jobs}
        for job in jobs:
            for material in job.inputs:
                extras[material.type_id] += material.quantity
        materials: dict[int, int] = defaultdict(int)
        manufacturing_ids: list[str] = []
        for i, count in enumerate(batches, 1):
            consumed = tuple(
                Material(
                    type_id=m.type_id,
                    quantity=formulas.manufacturing_material_quantity(
                        base_quantity=m.quantity,
                        runs=count,
                        material_efficiency=me,
                    ),
                )
                for m in bp.materials
                if m.quantity
            )
            for material in consumed:
                materials[material.type_id] += material.quantity
            job_id = f"make-{type_id}-{i}"
            manufacturing_ids.append(job_id)
            jobs.append(
                Job(
                    job_id=job_id,
                    activity="manufacturing",
                    blueprint_id=bp.blueprint_id,
                    runs=count,
                    licensed_runs=invention.licensed_runs if invention else count,
                    remaining_runs=(invention.licensed_runs - count)
                    if invention
                    else 0,
                    me=me,
                    te=te,
                    inputs=consumed,
                    dependencies=bpc_dependencies
                    if invention
                    else (f"bpc-{type_id}-copy-{i}",),
                    charges=self.charges(
                        bp, activity="manufacturing", runs=count, plan=plan
                    ),
                    duration=D(
                        str(
                            formulas.manufacturing_duration_seconds(
                                base_seconds=bp.manufacturing_seconds,
                                runs=count,
                                time_efficiency=te,
                                time_factors=(
                                    formulas.industry_time_factor(level=5),
                                    formulas.advanced_industry_time_factor(level=5),
                                    *(
                                        formulas.science_skill_manufacturing_time_factor(
                                            level=5
                                        )
                                        for _ in range(bp.science_skills)
                                    ),
                                ),
                            )
                        )
                    ),
                )
            )
        preparation_cost = known_sum(
            [job.total_fee for job in jobs if job.job_id in prep_ids]
            + [
                self.purchase(t, q, reason="blueprint preparation").cost
                for t, q in extras.items()
            ]
        )
        node = Node(
            type_id=type_id,
            blueprint_id=bp.blueprint_id,
            required=required,
            produced=runs * bp.output,
            me=me,
            te=te,
            probability=probability,
            attempts_per_bpc=attempts_per_bpc,
            bpcs=len(batches),
            materials=tuple(
                Material(type_id=t, quantity=q) for t, q in sorted(materials.items())
            ),
            job_ids=tuple(manufacturing_ids),
            preparation_cost=preparation_cost,
        )
        return node, jobs, extras

    def purchase(self, type_id: int, quantity: int, *, reason: str) -> Purchase:
        """Never substitute another market when the Jita sell side is missing."""
        return Purchase(
            type_id=type_id,
            quantity=quantity,
            unit_price=self.data.input_prices.get(type_id),
            reason=reason,
        )

    def is_subassembly(self, material: Material) -> bool:
        """Identify expandable manufacturing inputs independently of BPO access."""
        item = self.data.items.get(material.type_id)
        return (
            material.quantity > 0
            and material.type_id in self.routes
            and material.type_id not in self.data.reaction_products
            and (item is None or item.family != "unsupported")
        )

    def has_subassemblies(self, type_id: int) -> bool:
        """Suppress make only when a resolved recipe has no expandable inputs."""
        routes = self.routes.get(type_id, [])
        if len(routes) != 1:
            return True
        return any(self.is_subassembly(material) for material in routes[0].materials)

    def graph(self, root: int, strategy: Strategy) -> list[int]:
        """Return parent-before-child topological order, combining shared nodes."""
        visited: set[int] = set()
        active: set[int] = set()
        ordered: list[int] = []

        def visit(type_id: int) -> None:
            if type_id in active:
                raise Unavailable(f"Production dependency cycle at type {type_id}.")
            if type_id in visited:
                return
            active.add(type_id)
            bp = self.route(type_id)
            self.blueprint_access(bp)
            if strategy == "make-all-inputs":
                for material in bp.materials:
                    if self.is_subassembly(material):
                        visit(material.type_id)
            active.remove(type_id)
            visited.add(type_id)
            ordered.append(type_id)

        visit(root)
        return list(reversed(ordered))

    def plan(self, type_id: int, *, strategy: Strategy) -> Plan:
        """Plan a reference batch; preserve known-data failures as incomplete."""
        item = self.data.items[type_id]
        reference_runs = 1 if item.family == "t2-ship-rig" else 10
        plan = Plan(type_id=type_id, strategy=strategy, reference_runs=reference_runs)
        try:
            order = self.graph(type_id, strategy)
            required: dict[int, int] = defaultdict(int)
            required[type_id] = reference_runs * self.route(type_id).output
            purchases: dict[tuple[int, str], int] = defaultdict(int)
            node_jobs: dict[int, list[Job]] = {}
            for product in order:
                node, jobs, extras = self.node(
                    type_id=product, required=required[product], plan=plan
                )
                plan.nodes.append(node)
                node_jobs[product] = jobs
                for t, q in extras.items():
                    purchases[t, "blueprint preparation consumable"] += q
                for material in node.materials:
                    if material.type_id in order:
                        required[material.type_id] += material.quantity
                    else:
                        reason = (
                            "reaction unavailable at NPC station"
                            if material.type_id in self.data.reaction_products
                            else "external recipe input"
                        )
                        purchases[material.type_id, reason] += material.quantity
            nodes = {node.type_id: node for node in plan.nodes}
            for node in reversed(plan.nodes):
                for job in node_jobs[node.type_id]:
                    dependencies = list(job.dependencies)
                    for material in job.inputs:
                        if (
                            job.activity == "manufacturing"
                            and material.type_id in nodes
                        ):
                            dependencies.extend(nodes[material.type_id].job_ids)
                    plan.jobs.append(
                        replace(job, dependencies=tuple(dict.fromkeys(dependencies)))
                    )
                components: list[Decimal | None] = [
                    job.total_fee for job in node_jobs[node.type_id]
                ]
                for material in node.materials:
                    child = nodes.get(material.type_id)
                    if child is None:
                        components.append(
                            self.purchase(
                                material.type_id, material.quantity, reason="input"
                            ).cost
                        )
                    else:
                        components.append(
                            None
                            if child.cost is None
                            else child.cost * material.quantity / child.required
                        )
                for job in node_jobs[node.type_id]:
                    if job.activity in ("copying", "invention"):
                        components.extend(
                            self.purchase(
                                m.type_id, m.quantity, reason="blueprint preparation"
                            ).cost
                            for m in job.inputs
                        )
                node.cost = known_sum(components)
            plan.shopping = [
                self.purchase(t, q, reason=reason)
                for (t, reason), q in sorted(purchases.items())
            ]
            for line in plan.shopping:
                if line.type_id not in self.data.items:
                    plan.warnings.append(
                        f"Missing static identity for input {line.type_id}; retained by ID."
                    )
                if line.unit_price is None:
                    plan.warnings.append(f"Missing Jita sell 5% price: {line.type_id}.")
            plan.produced = plan.nodes[0].produced
            plan.total = known_sum(
                [line.cost for line in plan.shopping]
                + [job.total_fee for job in plan.jobs]
            )
            plan.unit_cost = None if plan.total is None else plan.total / plan.produced
        except Unavailable as error:
            plan.warnings.append(str(error))
        plan.warnings = list(dict.fromkeys(plan.warnings))
        return plan


def build_report(
    data: Inputs,
    *,
    product_ids: tuple[int, ...],
    sales_tax_rate: Decimal = DEFAULT_SALES_TAX_RATE,
    broker_fee_rate: Decimal = DEFAULT_BROKER_FEE_RATE,
) -> Report:
    """Collect both strategies and all hub outcomes from explicit inputs."""
    for rate in (sales_tax_rate, broker_fee_rate):
        if not rate.is_finite() or not 0 <= rate <= 1:
            raise ValueError("Sale fee fractions must be finite and in [0, 1].")
    if not product_ids or any(t not in data.items for t in product_ids):
        raise ValueError("Select known product type IDs.")
    for value in (
        *data.input_prices.values(),
        *data.adjusted_prices.values(),
        *data.indices.values(),
    ):
        if not value.is_finite() or value < 0:
            raise ValueError("Prices and indices must be finite and nonnegative.")
    planner = Planner(data)
    plans: list[Plan] = []
    for type_id in sorted(set(product_ids)):
        for strategy in ("buy-all-inputs", "make-all-inputs"):
            if strategy == "make-all-inputs" and not planner.has_subassemblies(type_id):
                continue
            plan = planner.plan(type_id, strategy=strategy)
            for hub in MARKET_HUBS:
                market = data.markets.get((hub.station_id, type_id))
                for basis in ("buy_5pct", "sell_5pct", "history_average"):
                    price = None
                    depth = None
                    if market is not None:
                        match basis:
                            case "buy_5pct":
                                price, depth = market.buy, market.buy_depth
                            case "sell_5pct":
                                price, depth = market.sell, market.sell_depth
                            case _:
                                price = market.history_price
                    fee_rate = sales_tax_rate + (
                        broker_fee_rate if basis != "buy_5pct" else D(0)
                    )
                    net = None if price is None else price * (1 - fee_rate)
                    profit = (
                        None
                        if net is None or plan.unit_cost is None
                        else net - plan.unit_cost
                    )
                    total_profit = None if profit is None else profit * plan.produced
                    status = "available"
                    if price is None:
                        status = "missing price"
                    elif plan.total is None:
                        status = "incomplete production cost"
                    elif depth is not None and depth < plan.produced:
                        status = "indicative; insufficient 5% depth"
                    elif basis == "history_average":
                        status = "regional proxy; no fill guarantee"
                    plan.outcomes.append(
                        Outcome(
                            station_id=hub.station_id,
                            basis=basis,
                            price=price,
                            depth=depth,
                            gross=None if price is None else price * plan.produced,
                            fees=None
                            if price is None
                            else price * plan.produced * fee_rate,
                            sales_tax=None
                            if price is None
                            else price * plan.produced * sales_tax_rate,
                            broker_fee=None
                            if price is None
                            else price
                            * plan.produced
                            * (broker_fee_rate if basis != "buy_5pct" else ZERO),
                            net_per_unit=net,
                            profit_per_unit=profit,
                            total_profit=total_profit,
                            return_pct=None
                            if total_profit is None or not plan.total
                            else 100 * total_profit / plan.total,
                            status=status,
                        )
                    )
            plans.append(plan)
    return Report(
        data=data,
        plans=tuple(plans),
        generated_at=datetime.now(UTC),
        sales_tax_rate=sales_tax_rate,
        broker_fee_rate=broker_fee_rate,
    )
