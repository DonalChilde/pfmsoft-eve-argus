"""App-agnostic reference formulas for EVE Online industry calculations.

Game mechanics current as of 2026-10-27.

This module is a documented, dependency-free reference for EVE Online industry
mechanics. It contains only pure functions over plain numbers; data loading,
pricing policy, and application-specific defaults belong elsewhere. Formulas are
added only after comparison with in-game quotes, and each records its evidence.
When game mechanics change, update the date above and the affected docstrings.

Currently covered:
    - Blueprint Material Efficiency (ME) and Time Efficiency (TE) research,
      including job duration, process time value (PTV), and job cost.
    - Invention, including success chance, decryptors, consumed inputs, invented
      blueprint attributes, PTV, duration, and attempt/confidence statistics.
    - Manufacturing, including material quantities, PTV, and duration with
      Industry, Advanced Industry, and science skill factors.
    - Blueprint copying, including PTV, job cost, and duration with Science and
      Advanced Industry.

Key terms:
    EIV: Estimated item value. The sum of the blueprint's unmodified
        manufacturing material quantities times CCP's adjusted prices (ESI
        ``/markets/prices/`` ``adjusted_price``). For invention, this is the
        EIV of the T2 blueprint being invented.
    PTV: Process time value. The value a job's fees are calculated from.
    SCI: System cost index, a per-system, per-activity fraction (e.g. 0.0525
        for a displayed 5.25%). The client displays two decimal places of a
        percentage, but the underlying value is more precise.
    Factor: A multiplier applied to time or cost, e.g. 0.8 for a 20% bonus.

Verification status (in-game comparisons recorded on 2026-10-27):
    Verified: research level multipliers; research PTV; research job cost with
        NPC facility tax, SCC surcharge, and Alpha clone tax; structure cost
        bonuses applying only to the gross job cost; research duration with
        skills and structure time role bonuses composing multiplicatively;
        invention PTV, job cost, success chance, duration with Advanced
        Industry, and per-attempt input consumption, for one and two attempts;
        the Attainment decryptor's chance, runs, ME, and TE effects;
        manufacturing per-job material rounding with a minimum of one per run,
        PTV and job cost, and duration with TE, Industry, Advanced Industry,
        and T2 science skills composing multiplicatively; structure and rig
        material bonuses composing multiplicatively with ME; structure
        manufacturing time bonus (Raitaru 15%); copying PTV, job cost with 4%
        SCC, and duration with Science and Advanced Industry at an NPC station.
    Assumed: research rig and implant bonuses are further independent factors;
        the other decryptors follow the EVE University table; structure bonuses
        apply to invention and copying as to research; rig manufacturing time
        factors; rig security scaling; invention success chance is capped at 1.
    Unresolved: the client's exact rounding. Whole-ISK, per-component half-up
        rounding (:meth:`JobCost.to_whole_isk`) usually matches to within a few
        ISK. The two-decimal material round is community-reported.

Sources:
    https://wiki.eveuniversity.org/Research
    https://wiki.eveuniversity.org/Invention
    https://wiki.eveuniversity.org/Blueprint_copying
    https://wiki.eveuniversity.org/Manufacturing#Total_job_cost
    https://wiki.eveuniversity.org/Upwell_structures#Engineering_complexes
    https://www.eveonline.com/news/view/industry-3rd-party-developers
    https://www.eveonline.com/news/view/viridian-expansion-notes
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

MAX_RESEARCH_LEVEL = 10
"""Number of ME and TE research steps a blueprint original can receive."""

ME_PERCENT_PER_LEVEL = 1
"""Material reduction, in percent, gained per ME research level."""

TE_PERCENT_PER_LEVEL = 2
"""Time reduction, in percent, gained per TE research level."""

RESEARCH_REFERENCE_STEP_SECONDS = 105
"""Base ME/TE step time of a rank-one blueprint, in seconds."""

RESEARCH_CUMULATIVE_RANK_ONE_SECONDS: tuple[int, ...] = (
    0,
    105,
    250,
    595,
    1414,
    3360,
    8000,
    19000,
    45255,
    107700,
    256000,
)
"""Unmodified time, in seconds, to research a rank-one blueprint from 0 to a level.

Indexed by research level. Applies to both ME and TE. Other blueprints scale by
their base step time divided by :data:`RESEARCH_REFERENCE_STEP_SECONDS`.
Source: https://wiki.eveuniversity.org/Research
"""

RESEARCH_PTV_EIV_RATE = 0.02
"""Fraction of EIV used per unit of research level multiplier to compute PTV."""

RESEARCH_SKILL_BONUS_PER_LEVEL = 0.05
"""Research time reduction per level of the activity skill.

Research skill for ME research, Metallurgy skill for TE research (verified
in-game 2026-10-27).
"""

ADVANCED_INDUSTRY_BONUS_PER_LEVEL = 0.03
"""Time reduction per Advanced Industry level, for manufacturing and science jobs."""

INDUSTRY_BONUS_PER_LEVEL = 0.04
"""Manufacturing time reduction per Industry skill level."""

SCIENCE_SKILL_MANUFACTURING_BONUS_PER_LEVEL = 0.01
"""Manufacturing time reduction per level of each required science skill."""

RESEARCH_SCC_RATE = 0.02
"""SCC surcharge rate for ME and TE research jobs, applied to PTV."""

MANUFACTURING_SCC_RATE = 0.04
"""SCC surcharge rate for manufacturing jobs, applied to PTV."""

INVENTION_SCC_RATE = 0.04
"""SCC surcharge rate for invention jobs, applied to PTV."""

COPYING_SCC_RATE = 0.04
"""SCC surcharge rate for blueprint copying jobs, applied to PTV."""

COPYING_PTV_EIV_RATE = 0.02
"""Fraction of the product's EIV used as PTV per licensed run copied."""

SCIENCE_COPY_BONUS_PER_LEVEL = 0.05
"""Copy time reduction per Science skill level."""

ALPHA_CLONE_TAX_RATE = 0.0025
"""Additional tax rate for Alpha clone characters, applied to PTV."""

NPC_FACILITY_TAX_RATE = 0.0025
"""Facility tax rate at NPC stations, applied to PTV."""

MAX_SKILL_LEVEL = 5

INVENTION_PTV_EIV_RATE = 0.02
"""Fraction of the invented T2 blueprint's EIV used as PTV per attempt.

Source: https://www.eveonline.com/news/view/industry-3rd-party-developers
"""

INVENTION_BASE_ME = 2
"""ME level of an invented blueprint copy before decryptor modifiers."""

INVENTION_BASE_TE = 4
"""TE level of an invented blueprint copy before decryptor modifiers."""

INVENTION_SCIENCE_SKILL_DIVISOR = 30
"""Divisor applied to the sum of the two science skill levels in success chance."""

INVENTION_ENCRYPTION_SKILL_DIVISOR = 40
"""Divisor applied to the encryption skill level in success chance."""


@dataclass(slots=True, kw_only=True, frozen=True)
class Decryptor:
    """An invention decryptor and its effects.

    Attributes:
        name: Decryptor name without the "Decryptor" suffix.
        type_id: The decryptor's EVE type ID.
        probability_modifier: Fractional change to success chance, e.g. 0.2
            multiplies chance by 1.2.
        runs: Runs added to the invented blueprint copy.
        me: ME levels added to the invented blueprint copy.
        te: TE levels added to the invented blueprint copy.
    """

    name: str
    type_id: int
    probability_modifier: float
    runs: int
    me: int
    te: int


DECRYPTORS: dict[str, Decryptor] = {
    d.name: d
    for d in (
        Decryptor(
            name="Accelerant",
            type_id=34201,
            probability_modifier=0.20,
            runs=1,
            me=2,
            te=10,
        ),
        Decryptor(
            name="Attainment",
            type_id=34202,
            probability_modifier=0.80,
            runs=4,
            me=-1,
            te=4,
        ),
        Decryptor(
            name="Augmentation",
            type_id=34203,
            probability_modifier=-0.40,
            runs=9,
            me=-2,
            te=2,
        ),
        Decryptor(
            name="Parity", type_id=34204, probability_modifier=0.50, runs=3, me=1, te=-2
        ),
        Decryptor(
            name="Process", type_id=34205, probability_modifier=0.10, runs=0, me=3, te=6
        ),
        Decryptor(
            name="Symmetry", type_id=34206, probability_modifier=0.0, runs=2, me=1, te=8
        ),
        Decryptor(
            name="Optimized Attainment",
            type_id=34207,
            probability_modifier=0.90,
            runs=2,
            me=1,
            te=-2,
        ),
        Decryptor(
            name="Optimized Augmentation",
            type_id=34208,
            probability_modifier=-0.10,
            runs=7,
            me=2,
            te=0,
        ),
    )
}
"""Standard invention decryptors keyed by name.

Values are from the EVE University decryptor table. Attainment was verified
in-game 2026-10-27; the others are not yet verified
in-game. Source: https://wiki.eveuniversity.org/Invention
"""


@dataclass(slots=True, kw_only=True, frozen=True)
class InventedBlueprint:
    """Attributes of a successfully invented blueprint copy.

    Attributes:
        runs: Manufacturing runs on the copy.
        me: Material efficiency level, in percent.
        te: Time efficiency level, in percent.
    """

    runs: int
    me: int
    te: int


@dataclass(slots=True, kw_only=True, frozen=True)
class MaterialValue:
    """One blueprint input material for EIV calculation.

    Attributes:
        quantity: Unmodified material quantity per run, before any ME reduction.
        adjusted_price: CCP adjusted price for the material type, in ISK.
    """

    quantity: float
    adjusted_price: float


@dataclass(slots=True, kw_only=True, frozen=True)
class JobCost:
    """Itemized industry job installation cost, in ISK.

    Labels mirror the in-game job window: Gross Job Cost, Total Taxes, and
    Total Job Cost.

    Attributes:
        process_time_value: The value fees are calculated from.
        gross_job_cost: ``PTV * SCI`` after cost bonuses.
        facility_tax: ``PTV * facility tax rate``.
        scc_surcharge: ``PTV * SCC rate``.
        alpha_tax: ``PTV * Alpha clone tax rate``; zero for Omega clones.
        total_taxes: Sum of facility tax, SCC surcharge, and Alpha tax.
        total_job_cost: Gross job cost plus total taxes.
    """

    process_time_value: float
    gross_job_cost: float
    facility_tax: float
    scc_surcharge: float
    alpha_tax: float
    total_taxes: float
    total_job_cost: float

    def to_whole_isk(self) -> JobCost:
        """Round each charge to whole ISK, half up, and recompute totals.

        This is a provisional estimate of client rounding. It matched one
        in-game quote exactly and others to within 1-2 ISK.

        Returns:
            A new JobCost containing whole-ISK values.
        """
        gross = round_isk_half_up(self.gross_job_cost)
        facility = round_isk_half_up(self.facility_tax)
        scc = round_isk_half_up(self.scc_surcharge)
        alpha = round_isk_half_up(self.alpha_tax)
        taxes = facility + scc + alpha
        return JobCost(
            process_time_value=round_isk_half_up(self.process_time_value),
            gross_job_cost=gross,
            facility_tax=facility,
            scc_surcharge=scc,
            alpha_tax=alpha,
            total_taxes=taxes,
            total_job_cost=gross + taxes,
        )


def round_isk_half_up(value: float) -> int:
    """Round a non-negative ISK amount to whole ISK, rounding halves up.

    Python's built-in :func:`round` rounds halves to even, which is not used here.

    Args:
        value: The non-negative ISK amount.

    Returns:
        The amount rounded to whole ISK.
    """
    return math.floor(value + 0.5)


def bonus_to_factor(*, bonus: float) -> float:
    """Convert a reduction bonus to a multiplicative factor.

    For example, a structure's 20% time role bonus becomes ``0.8``.

    Args:
        bonus: Reduction as a fraction from 0 to 1, e.g. 0.20 for 20%.

    Returns:
        ``1 - bonus``.

    Raises:
        ValueError: If bonus is outside 0 to 1.
    """
    if not 0 <= bonus <= 1:
        raise ValueError(f"bonus must be between 0 and 1, got {bonus}")
    return 1 - bonus


def material_efficiency_percent(*, level: int) -> int:
    """Return the material reduction percent for an ME research level.

    Args:
        level: ME research level, 0 to 10.

    Returns:
        Material reduction in percent, 0 to 10.

    Raises:
        ValueError: If level is out of range.
    """
    _validate_research_level(level)
    return level * ME_PERCENT_PER_LEVEL


def time_efficiency_percent(*, level: int) -> int:
    """Return the time reduction percent for a TE research level.

    Args:
        level: TE research level, 0 to 10.

    Returns:
        Time reduction in percent, 0 to 20.

    Raises:
        ValueError: If level is out of range.
    """
    _validate_research_level(level)
    return level * TE_PERCENT_PER_LEVEL


def research_level_multiplier(*, start_level: int, target_level: int) -> float:
    """Return the research level multiplier for a single ME or TE job.

    The multiplier is the job's unmodified rank-one duration divided by the
    105-second reference step time. For a single step it equals CCP's published
    per-level multipliers (1, 29/21, 23/7, ...). The in-game client quotes a
    multi-step job (e.g. 0 to 10) as one job.

    Source: https://www.eveonline.com/news/view/industry-3rd-party-developers

    Args:
        start_level: Current research level, 0 to 10.
        target_level: Target research level, start_level to 10.

    Returns:
        The level multiplier; zero when start and target are equal.

    Raises:
        ValueError: If a level is out of range or target is below start.
    """
    _validate_level_range(start_level=start_level, target_level=target_level)
    cumulative = RESEARCH_CUMULATIVE_RANK_ONE_SECONDS
    return (
        cumulative[target_level] - cumulative[start_level]
    ) / RESEARCH_REFERENCE_STEP_SECONDS


def estimated_item_value(*, materials: Iterable[MaterialValue]) -> float:
    """Return the estimated item value (EIV) of a blueprint's manufacturing inputs.

    Uses unmodified manufacturing quantities; blueprint ME does not reduce EIV.

    Source: https://wiki.eveuniversity.org/Manufacturing#Total_job_cost

    Args:
        materials: Manufacturing materials with unmodified quantities and CCP
            adjusted prices.

    Returns:
        The EIV, in ISK.

    Raises:
        ValueError: If any quantity or price is negative.
    """
    total = 0.0
    for material in materials:
        if material.quantity < 0 or material.adjusted_price < 0:
            raise ValueError(f"material values must be non-negative: {material}")
        total += material.quantity * material.adjusted_price
    return total


def research_process_time_value(
    *, estimated_item_value: float, start_level: int, target_level: int
) -> float:
    """Return the PTV of an ME or TE research job.

    ``PTV = EIV * 0.02 * research_level_multiplier``. ME and TE research use the
    same PTV. It does not depend on the blueprint's base research time, skills, or
    facility. Verified in-game 2026-10-27 for rank-one and rank-fifteen blueprints.

    Args:
        estimated_item_value: The blueprint's manufacturing EIV, in ISK.
        start_level: Current research level, 0 to 10.
        target_level: Target research level, start_level to 10.

    Returns:
        The PTV, in ISK.

    Raises:
        ValueError: If EIV is negative or the levels are invalid.
    """
    if estimated_item_value < 0:
        raise ValueError(
            f"estimated_item_value must be non-negative, got {estimated_item_value}"
        )
    multiplier = research_level_multiplier(
        start_level=start_level, target_level=target_level
    )
    return estimated_item_value * RESEARCH_PTV_EIV_RATE * multiplier


def research_skill_time_factor(
    *, primary_skill_level: int, advanced_industry_level: int
) -> float:
    """Return the combined skill time factor for an ME or TE research job.

    Skill reductions multiply rather than add, e.g. level 5 in both skills gives
    ``0.75 * 0.85 = 0.6375``. The client shows this as a -36.3% skill bonus.
    Verified in-game 2026-10-27.

    Args:
        primary_skill_level: Research skill level for ME research, or
            Metallurgy skill level for TE research.
        advanced_industry_level: Advanced Industry skill level.

    Returns:
        The multiplicative time factor.

    Raises:
        ValueError: If a skill level is outside 0 to 5.
    """
    for level in (primary_skill_level, advanced_industry_level):
        _validate_skill_level(level)
    return (
        1 - RESEARCH_SKILL_BONUS_PER_LEVEL * primary_skill_level
    ) * advanced_industry_time_factor(level=advanced_industry_level)


def research_duration_seconds(
    *,
    base_step_seconds: float,
    start_level: int,
    target_level: int,
    time_factors: Iterable[float] = (),
) -> float:
    """Return the duration of an ME or TE research job, in seconds.

    ``duration = base_step_seconds * research_level_multiplier * product(factors)``.
    Time factors compose multiplicatively. Verified in-game 2026-10-27 for skill
    factors (:func:`research_skill_time_factor`) and structure time role bonuses.
    Research rig and implant factors are assumed to compose the same way. Alpha
    clones were observed to receive no skill time bonus; pass no skill factor for
    them. The client's final rounding of the duration is unverified.

    Args:
        base_step_seconds: The blueprint's base research time for the activity,
            i.e. the static data ``research_material`` (ME) or ``research_time``
            (TE) activity time.
        start_level: Current research level, 0 to 10.
        target_level: Target research level, start_level to 10.
        time_factors: Multiplicative time factors such as skill, structure,
            rig, and implant factors.

    Returns:
        The job duration, in seconds.

    Raises:
        ValueError: If base time is not positive, a factor is negative, or the
            levels are invalid.
    """
    if base_step_seconds <= 0:
        raise ValueError(f"base_step_seconds must be positive, got {base_step_seconds}")
    multiplier = research_level_multiplier(
        start_level=start_level, target_level=target_level
    )
    return base_step_seconds * multiplier * _product(time_factors)


def job_cost(
    *,
    process_time_value: float,
    system_cost_index: float,
    facility_tax_rate: float,
    scc_rate: float,
    alpha_tax_rate: float = 0.0,
    cost_factors: Iterable[float] = (),
) -> JobCost:
    """Return the itemized installation cost of an industry job.

    ``gross = PTV * SCI * product(cost_factors)`` and each tax is ``PTV * rate``.
    Cost bonuses, such as a structure's cost bonus, reduce only the gross job cost,
    never the taxes. Verified in-game 2026-10-27 for ME and TE research at an NPC
    station and an Upwell structure with a 4% cost bonus.

    The same formula applies to other activities with an activity-specific PTV and
    SCC rate, e.g. :data:`MANUFACTURING_SCC_RATE`, but only research has been
    verified here.

    Sources:
        https://www.eveonline.com/news/view/viridian-expansion-notes
        https://wiki.eveuniversity.org/Manufacturing#Total_job_cost

    Args:
        process_time_value: The job's PTV, in ISK.
        system_cost_index: The activity's SCI as a fraction, e.g. 0.0525.
        facility_tax_rate: Facility tax as a fraction, e.g.
            :data:`NPC_FACILITY_TAX_RATE`.
        scc_rate: Activity SCC surcharge rate, e.g. :data:`RESEARCH_SCC_RATE`.
        alpha_tax_rate: :data:`ALPHA_CLONE_TAX_RATE` for Alpha clones, otherwise 0.
        cost_factors: Multiplicative cost factors applied to ``PTV * SCI``.

    Returns:
        The unrounded, itemized job cost.

    Raises:
        ValueError: If any value, rate, or factor is negative.
    """
    values = {
        "process_time_value": process_time_value,
        "system_cost_index": system_cost_index,
        "facility_tax_rate": facility_tax_rate,
        "scc_rate": scc_rate,
        "alpha_tax_rate": alpha_tax_rate,
    }
    for name, value in values.items():
        if value < 0:
            raise ValueError(f"{name} must be non-negative, got {value}")
    gross = process_time_value * system_cost_index * _product(cost_factors)
    facility = process_time_value * facility_tax_rate
    scc = process_time_value * scc_rate
    alpha = process_time_value * alpha_tax_rate
    taxes = facility + scc + alpha
    return JobCost(
        process_time_value=process_time_value,
        gross_job_cost=gross,
        facility_tax=facility,
        scc_surcharge=scc,
        alpha_tax=alpha,
        total_taxes=taxes,
        total_job_cost=gross + taxes,
    )


def advanced_industry_time_factor(*, level: int) -> float:
    """Return the Advanced Industry time factor for science and manufacturing jobs.

    Advanced Industry reduces job time by 3% per level. Verified in-game
    2026-10-27 for ME/TE research and invention.

    Args:
        level: Advanced Industry skill level, 0 to 5.

    Returns:
        The multiplicative time factor.

    Raises:
        ValueError: If level is outside 0 to 5.
    """
    _validate_skill_level(level)
    return 1 - ADVANCED_INDUSTRY_BONUS_PER_LEVEL * level


def invention_success_chance(
    *,
    base_chance: float,
    science_skill_levels: tuple[int, int],
    encryption_skill_level: int,
    decryptor: Decryptor | None = None,
) -> float:
    """Return the success chance of one invention attempt.

    ``chance = base * (1 + (science_1 + science_2) / 30 + encryption / 40)
    * (1 + decryptor modifier)``, capped at 1. Verified in-game 2026-10-27
    with all skills 5 and a 34% base: 49.6% without a decryptor, and 89.3%
    (89.25%) with Attainment. The cap is unverified; with current base chances
    it is not reached.

    Source: https://wiki.eveuniversity.org/Invention

    Args:
        base_chance: The outcome's base chance, e.g. 0.34. Found in static
            data as the invention product probability.
        science_skill_levels: Levels of the two required science skills.
        encryption_skill_level: Level of the required encryption methods skill.
        decryptor: The decryptor used, if any.

    Returns:
        The success chance, from 0 to 1.

    Raises:
        ValueError: If base_chance is outside 0 to 1, a skill level is invalid,
            or science_skill_levels does not have exactly two levels.
    """
    if not 0 <= base_chance <= 1:
        raise ValueError(f"base_chance must be between 0 and 1, got {base_chance}")
    if len(science_skill_levels) != 2:
        raise ValueError(
            f"expected two science skill levels, got {science_skill_levels}"
        )
    for level in (*science_skill_levels, encryption_skill_level):
        _validate_skill_level(level)
    skill_multiplier = (
        1
        + sum(science_skill_levels) / INVENTION_SCIENCE_SKILL_DIVISOR
        + encryption_skill_level / INVENTION_ENCRYPTION_SKILL_DIVISOR
    )
    decryptor_multiplier = 1 + (decryptor.probability_modifier if decryptor else 0)
    return min(1.0, base_chance * skill_multiplier * decryptor_multiplier)


def invented_blueprint(
    *, base_runs: int, decryptor: Decryptor | None = None
) -> InventedBlueprint:
    """Return the attributes of a successfully invented blueprint copy.

    The input T1 copy's ME, TE, and runs have no effect. Decryptor modifiers
    are added to the base values (verified in-game 2026-10-27 for Attainment).

    Source: https://wiki.eveuniversity.org/Invention

    Args:
        base_runs: The invention product quantity from static data, e.g. 10
            for most modules and 1 for ships and rigs.
        decryptor: The decryptor used, if any.

    Returns:
        The invented copy's runs, ME, and TE.

    Raises:
        ValueError: If base_runs is not positive.
    """
    if base_runs < 1:
        raise ValueError(f"base_runs must be positive, got {base_runs}")
    if decryptor is None:
        return InventedBlueprint(
            runs=base_runs, me=INVENTION_BASE_ME, te=INVENTION_BASE_TE
        )
    return InventedBlueprint(
        runs=base_runs + decryptor.runs,
        me=INVENTION_BASE_ME + decryptor.me,
        te=INVENTION_BASE_TE + decryptor.te,
    )


def invention_process_time_value(
    *, estimated_item_value: float, attempts: int = 1
) -> float:
    """Return the PTV of an invention job.

    ``PTV = invented T2 blueprint EIV * 0.02 * attempts``. Note that the EIV is
    that of the T2 blueprint being invented, not the T1 input blueprint. Verified
    in-game 2026-10-27 for one and two attempts.

    Source: https://www.eveonline.com/news/view/industry-3rd-party-developers

    Args:
        estimated_item_value: EIV of the invented T2 blueprint's manufacturing
            materials, in ISK.
        attempts: Number of invention runs in the job.

    Returns:
        The PTV, in ISK. Use with :func:`job_cost` and :data:`INVENTION_SCC_RATE`.

    Raises:
        ValueError: If EIV is negative or attempts is not positive.
    """
    if estimated_item_value < 0:
        raise ValueError(
            f"estimated_item_value must be non-negative, got {estimated_item_value}"
        )
    _validate_attempts(attempts)
    return estimated_item_value * INVENTION_PTV_EIV_RATE * attempts


def invention_inputs(
    *,
    materials_per_attempt: Mapping[int, int],
    attempts: int = 1,
    decryptor: Decryptor | None = None,
) -> dict[int, int]:
    """Return the items consumed by an invention job, keyed by type ID.

    Datacores (the static invention materials) and the decryptor are each
    consumed once per attempt, whether the attempt succeeds or fails. Verified
    in-game 2026-10-27: two runs required two of each datacore and two
    decryptors. One run of the input T1 blueprint copy is also consumed per
    attempt; it is not included here.

    Args:
        materials_per_attempt: Static invention material quantities by type ID.
        attempts: Number of invention runs in the job.
        decryptor: The decryptor used, if any.

    Returns:
        Total quantities consumed, by type ID.

    Raises:
        ValueError: If a quantity is negative or attempts is not positive.
    """
    _validate_attempts(attempts)
    consumed: dict[int, int] = {}
    for type_id, quantity in materials_per_attempt.items():
        if quantity < 0:
            raise ValueError(f"quantity for {type_id} must be non-negative")
        consumed[type_id] = consumed.get(type_id, 0) + quantity * attempts
    if decryptor is not None:
        consumed[decryptor.type_id] = consumed.get(decryptor.type_id, 0) + attempts
    return consumed


def invention_duration_seconds(
    *, base_seconds: float, attempts: int = 1, time_factors: Iterable[float] = ()
) -> float:
    """Return the duration of an invention job, in seconds.

    ``duration = base_seconds * attempts * product(time_factors)``. Verified
    in-game 2026-10-27 for one and two attempts with Advanced Industry 5 (7800 s
    per attempt to 01:50:30 and 03:41:00). The science and encryption skills do
    not affect time. Structure and implant factors are assumed to compose
    multiplicatively, as for research.

    Args:
        base_seconds: The T1 blueprint's static invention activity time.
        attempts: Number of invention runs in the job.
        time_factors: Multiplicative time factors, e.g. from
            :func:`advanced_industry_time_factor`.

    Returns:
        The job duration, in seconds.

    Raises:
        ValueError: If base time or attempts is not positive, or a factor is
            negative.
    """
    if base_seconds <= 0:
        raise ValueError(f"base_seconds must be positive, got {base_seconds}")
    _validate_attempts(attempts)
    return base_seconds * attempts * _product(time_factors)


def expected_attempts_per_success(*, success_chance: float) -> float:
    """Return the mean number of attempts per success, ``1 / chance``.

    Args:
        success_chance: Per-attempt success chance, greater than 0 up to 1.

    Returns:
        The expected attempts per success.

    Raises:
        ValueError: If success_chance is not in (0, 1].
    """
    _validate_success_chance(success_chance)
    return 1 / success_chance


def expected_cost_per_success(
    *, cost_per_attempt: float, success_chance: float
) -> float:
    """Return the expected cost of one success, ``cost_per_attempt / chance``.

    Per-attempt cost should include the job cost, datacores, any decryptor, and
    the value of the consumed T1 blueprint run; all are consumed on failure.

    Args:
        cost_per_attempt: Total cost of one attempt, in ISK.
        success_chance: Per-attempt success chance, greater than 0 up to 1.

    Returns:
        The expected cost per successful invented blueprint, in ISK.

    Raises:
        ValueError: If cost is negative or success_chance is not in (0, 1].
    """
    if cost_per_attempt < 0:
        raise ValueError(
            f"cost_per_attempt must be non-negative, got {cost_per_attempt}"
        )
    return cost_per_attempt * expected_attempts_per_success(
        success_chance=success_chance
    )


def probability_of_at_least_one_success(
    *, success_chance: float, attempts: int
) -> float:
    """Return the chance of one or more successes in independent attempts.

    Args:
        success_chance: Per-attempt success chance, greater than 0 up to 1.
        attempts: Number of attempts.

    Returns:
        ``1 - (1 - chance) ** attempts``.

    Raises:
        ValueError: If success_chance is not in (0, 1] or attempts is not
            positive.
    """
    _validate_success_chance(success_chance)
    _validate_attempts(attempts)
    return 1 - (1 - success_chance) ** attempts


def attempts_for_confidence(*, success_chance: float, confidence: float) -> int:
    """Return the fewest attempts giving at least one success with a confidence.

    Args:
        success_chance: Per-attempt success chance, greater than 0 up to 1.
        confidence: Target probability of at least one success, in (0, 1).

    Returns:
        The minimum number of attempts.

    Raises:
        ValueError: If success_chance is not in (0, 1] or confidence is not in
            (0, 1).
    """
    _validate_success_chance(success_chance)
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be between 0 and 1, got {confidence}")
    if success_chance == 1:
        return 1
    attempts = math.ceil(math.log(1 - confidence) / math.log(1 - success_chance))
    # Guard against floating point error placing an exact boundary one too high.
    if (
        attempts > 1
        and probability_of_at_least_one_success(
            success_chance=success_chance, attempts=attempts - 1
        )
        >= confidence
    ):
        attempts -= 1
    return max(1, attempts)


def manufacturing_material_quantity(
    *,
    base_quantity: int,
    runs: int,
    material_efficiency: int,
    material_factors: Iterable[float] = (),
) -> int:
    """Return the quantity of one material consumed by a manufacturing job.

    ``max(runs, ceil(round(base * runs * (1 - ME/100) * product(factors), 2)))``.

    Rounding is per job, not per run, so one multi-run job can need less than
    several single-run jobs. At least one unit per run is required. Verified
    in-game 2026-10-27 for ME10 Hobgoblin I (1 and 10 runs), the minimum of one
    per run for ME1 Hobgoblin II, and ME10 Cap Booster 200 in a Raitaru with its
    1% structure bonus and a 2% ammunition rig bonus, composing multiplicatively.

    The two-decimal round before ``ceil`` is community-reported and unverified
    in-game. It changes real results, not just floating-point artifacts, e.g.
    ``21 * 3 * 0.93 * 0.99 = 58.0041`` gives 58 rather than 59. Rig security
    scaling is unverified; pass the already-scaled rig bonus.

    Source: https://wiki.eveuniversity.org/Manufacturing

    Args:
        base_quantity: Unmodified per-run quantity from the blueprint.
        runs: Number of manufacturing runs.
        material_efficiency: Blueprint ME level, 0 to 10, in percent.
        material_factors: Multiplicative structure and rig material factors,
            e.g. 0.99 for a 1% engineering complex bonus.

    Returns:
        Whole units consumed by the job; 0 if base_quantity is 0.

    Raises:
        ValueError: If base_quantity is negative, runs is not positive, ME is
            outside 0 to 10, or a factor is negative.
    """
    if base_quantity < 0:
        raise ValueError(f"base_quantity must be non-negative, got {base_quantity}")
    _validate_runs(runs)
    _validate_research_level(material_efficiency)
    if base_quantity == 0:
        return 0
    modified = (
        base_quantity
        * runs
        * (1 - material_efficiency / 100)
        * _product(material_factors)
    )
    return max(runs, math.ceil(round(modified, 2)))


def manufacturing_materials(
    *,
    base_materials: Mapping[int, int],
    runs: int,
    material_efficiency: int,
    material_factors: Iterable[float] = (),
) -> dict[int, int]:
    """Return the materials consumed by a manufacturing job, keyed by type ID.

    Applies :func:`manufacturing_material_quantity` to each material.

    Args:
        base_materials: Unmodified per-run quantities by type ID.
        runs: Number of manufacturing runs.
        material_efficiency: Blueprint ME level, 0 to 10, in percent.
        material_factors: Multiplicative structure and rig material factors.

    Returns:
        Whole units consumed, by type ID.

    Raises:
        ValueError: If any input is invalid.
    """
    factors = tuple(material_factors)
    return {
        type_id: manufacturing_material_quantity(
            base_quantity=quantity,
            runs=runs,
            material_efficiency=material_efficiency,
            material_factors=factors,
        )
        for type_id, quantity in base_materials.items()
    }


def manufacturing_process_time_value(
    *, estimated_item_value: float, runs: int
) -> float:
    """Return the PTV of a manufacturing job, ``EIV * runs``.

    EIV uses the blueprint's unmodified (ME0) material quantities; blueprint ME
    and facility bonuses do not reduce it. Verified in-game 2026-10-27 for T1 and
    T2 manufacturing to within a few ISK (SCI display precision).

    Source: https://wiki.eveuniversity.org/Manufacturing#Total_job_cost

    Args:
        estimated_item_value: EIV of one run, in ISK.
        runs: Number of manufacturing runs.

    Returns:
        The PTV, in ISK. Use with :func:`job_cost` and
        :data:`MANUFACTURING_SCC_RATE`.

    Raises:
        ValueError: If EIV is negative or runs is not positive.
    """
    if estimated_item_value < 0:
        raise ValueError(
            f"estimated_item_value must be non-negative, got {estimated_item_value}"
        )
    _validate_runs(runs)
    return estimated_item_value * runs


def industry_time_factor(*, level: int) -> float:
    """Return the Industry skill manufacturing time factor, 4% per level.

    Verified in-game 2026-10-27.

    Args:
        level: Industry skill level, 0 to 5.

    Returns:
        The multiplicative time factor.

    Raises:
        ValueError: If level is outside 0 to 5.
    """
    _validate_skill_level(level)
    return 1 - INDUSTRY_BONUS_PER_LEVEL * level


def science_skill_manufacturing_time_factor(*, level: int) -> float:
    """Return a required science skill's manufacturing time factor, 1% per level.

    Applies to each science or engineering skill a blueprint requires for
    manufacturing (e.g. Graviton Physics for Hobgoblin II). Verified in-game
    2026-10-27 with two science skills at level 5 composing multiplicatively.

    Args:
        level: The skill level, 0 to 5.

    Returns:
        The multiplicative time factor.

    Raises:
        ValueError: If level is outside 0 to 5.
    """
    _validate_skill_level(level)
    return 1 - SCIENCE_SKILL_MANUFACTURING_BONUS_PER_LEVEL * level


def manufacturing_duration_seconds(
    *,
    base_seconds: float,
    runs: int,
    time_efficiency: int,
    time_factors: Iterable[float] = (),
) -> float:
    """Return the duration of a manufacturing job, in seconds.

    ``base_seconds * runs * (1 - TE/100) * product(time_factors)``. Verified
    in-game 2026-10-27 for Hobgoblin I (TE20, Industry and Advanced Industry),
    Hobgoblin II (TE8, plus two science skills), and Cap Booster 200 in a
    Raitaru (TE20 plus the 15% structure time bonus). Rig and implant factors
    are assumed to compose multiplicatively.

    Args:
        base_seconds: The blueprint's static manufacturing time per run.
        runs: Number of manufacturing runs.
        time_efficiency: Blueprint TE level, 0 to 20, in percent.
        time_factors: Multiplicative factors, e.g. from
            :func:`industry_time_factor`, :func:`advanced_industry_time_factor`,
            and :func:`science_skill_manufacturing_time_factor`.

    Returns:
        The job duration, in seconds.

    Raises:
        ValueError: If base time or runs is not positive, TE is outside 0 to 20,
            or a factor is negative.
    """
    if base_seconds <= 0:
        raise ValueError(f"base_seconds must be positive, got {base_seconds}")
    _validate_runs(runs)
    max_te = MAX_RESEARCH_LEVEL * TE_PERCENT_PER_LEVEL
    if not 0 <= time_efficiency <= max_te:
        raise ValueError(
            f"time_efficiency must be 0 to {max_te}, got {time_efficiency}"
        )
    return base_seconds * runs * (1 - time_efficiency / 100) * _product(time_factors)


def copying_process_time_value(
    *,
    estimated_item_value: float,
    runs_per_copy: int,
    copies: int,
    max_runs_per_copy: int | None = None,
) -> float:
    """Return the PTV of a blueprint copying job.

    ``PTV = 0.02 * EIV * runs_per_copy * copies``. EIV is that of the item the
    blueprint manufactures. Fees use :func:`job_cost` with
    :data:`COPYING_SCC_RATE`; structure cost bonuses reduce only the gross job
    cost. Verified in-game 2026-10-27 for Large Auxiliary Nano Pump I in Osmeden
    (1 copy x 10 runs, SCI 4.09%, NPC station): gross 23,511, facility tax 1,437,
    and SCC 22,993.

    Source: https://wiki.eveuniversity.org/Blueprint_copying

    Args:
        estimated_item_value: EIV of one manufacturing run of the product, in ISK.
        runs_per_copy: Licensed manufacturing runs on each copy.
        copies: Number of copies made.
        max_runs_per_copy: The blueprint's maximum runs per copy (SDE
            ``maxProductionLimit``), checked when given.

    Returns:
        The PTV, in ISK.

    Raises:
        ValueError: If EIV is negative, runs or copies is not positive, or runs
            exceeds ``max_runs_per_copy``.
    """
    if estimated_item_value < 0:
        raise ValueError(
            f"estimated_item_value must be non-negative, got {estimated_item_value}"
        )
    _validate_copy_counts(
        runs_per_copy=runs_per_copy,
        copies=copies,
        max_runs_per_copy=max_runs_per_copy,
    )
    return estimated_item_value * COPYING_PTV_EIV_RATE * runs_per_copy * copies


def science_copy_time_factor(*, level: int) -> float:
    """Return the Science skill copying time factor, 5% per level.

    Verified in-game 2026-10-27 with Science 5 and Advanced Industry 5 composing
    multiplicatively.

    Source: https://wiki.eveuniversity.org/Blueprint_copying

    Args:
        level: Science skill level, 0 to 5.

    Returns:
        The multiplicative time factor.

    Raises:
        ValueError: If level is outside 0 to 5.
    """
    _validate_skill_level(level)
    return 1 - SCIENCE_COPY_BONUS_PER_LEVEL * level


def copying_duration_seconds(
    *,
    base_seconds: float,
    runs_per_copy: int,
    copies: int,
    time_factors: Iterable[float] = (),
) -> float:
    """Return the duration of a blueprint copying job, in seconds.

    ``base_seconds * runs_per_copy * copies * product(time_factors)``. The
    original's ME and TE do not affect copying, and each copy inherits them.
    Verified in-game 2026-10-27 at an NPC station for Large Auxiliary Nano Pump I
    (3600 s per run, 1 copy x 10 runs, Science 5 and Advanced Industry 5:
    6:22:30). Structure, rig, and implant time factors are assumed to compose
    multiplicatively, as verified for research.

    Args:
        base_seconds: The blueprint's static copying time per run.
        runs_per_copy: Licensed manufacturing runs on each copy.
        copies: Number of copies made.
        time_factors: Multiplicative factors, e.g. from
            :func:`science_copy_time_factor` and
            :func:`advanced_industry_time_factor`.

    Returns:
        The job duration, in seconds.

    Raises:
        ValueError: If base time, runs, or copies is not positive, or a factor
            is negative.
    """
    if base_seconds <= 0:
        raise ValueError(f"base_seconds must be positive, got {base_seconds}")
    _validate_copy_counts(runs_per_copy=runs_per_copy, copies=copies)
    return base_seconds * runs_per_copy * copies * _product(time_factors)


def _validate_copy_counts(
    *, runs_per_copy: int, copies: int, max_runs_per_copy: int | None = None
) -> None:
    if runs_per_copy < 1:
        raise ValueError(f"runs_per_copy must be positive, got {runs_per_copy}")
    if copies < 1:
        raise ValueError(f"copies must be positive, got {copies}")
    if max_runs_per_copy is not None and runs_per_copy > max_runs_per_copy:
        raise ValueError(
            f"runs_per_copy {runs_per_copy} exceeds the limit {max_runs_per_copy}"
        )


def _validate_runs(runs: int) -> None:
    """Raise ValueError if runs is not positive."""
    if runs < 1:
        raise ValueError(f"runs must be positive, got {runs}")


def _validate_skill_level(level: int) -> None:
    """Raise ValueError if a skill level is outside 0 to MAX_SKILL_LEVEL."""
    if not 0 <= level <= MAX_SKILL_LEVEL:
        raise ValueError(f"skill level must be 0 to {MAX_SKILL_LEVEL}, got {level}")


def _validate_attempts(attempts: int) -> None:
    """Raise ValueError if attempts is not positive."""
    if attempts < 1:
        raise ValueError(f"attempts must be positive, got {attempts}")


def _validate_success_chance(success_chance: float) -> None:
    """Raise ValueError if success_chance is not in (0, 1]."""
    if not 0 < success_chance <= 1:
        raise ValueError(
            f"success_chance must be greater than 0 and at most 1, got {success_chance}"
        )


def _product(factors: Iterable[float]) -> float:
    """Return the product of non-negative factors; 1 when empty."""
    result = 1.0
    for factor in factors:
        if factor < 0:
            raise ValueError(f"factors must be non-negative, got {factor}")
        result *= factor
    return result


def _validate_research_level(level: int) -> None:
    """Raise ValueError if level is outside 0 to MAX_RESEARCH_LEVEL."""
    if not 0 <= level <= MAX_RESEARCH_LEVEL:
        raise ValueError(
            f"research level must be 0 to {MAX_RESEARCH_LEVEL}, got {level}"
        )


def _validate_level_range(*, start_level: int, target_level: int) -> None:
    """Raise ValueError for invalid levels or a target below the start."""
    _validate_research_level(start_level)
    _validate_research_level(target_level)
    if target_level < start_level:
        raise ValueError(
            f"target_level {target_level} is below start_level {start_level}"
        )
