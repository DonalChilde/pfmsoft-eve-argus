"""App-agnostic reference formulas for EVE Online industry calculations.

Game mechanics current as of 2026-10-27.

This module is a documented, dependency-free reference for EVE Online industry
mechanics. It contains only pure functions over plain numbers; data loading,
pricing policy, and application-specific defaults belong elsewhere. Formulas are
added only after comparison with in-game quotes, and each records its evidence.
When game mechanics change, update the date above and the affected docstrings.

Currently covered: blueprint Material Efficiency (ME) and Time Efficiency (TE)
research, including job duration, process time value (PTV), and job cost.

Key terms:
    EIV: Estimated item value. The sum of the blueprint's unmodified
        manufacturing material quantities times CCP's adjusted prices (ESI
        ``/markets/prices/`` ``adjusted_price``).
    PTV: Process time value. The value a job's fees are calculated from.
    SCI: System cost index, a per-system, per-activity fraction (e.g. 0.0525
        for a displayed 5.25%). The client displays two decimal places of a
        percentage, but the underlying value is more precise.
    Factor: A multiplier applied to time or cost, e.g. 0.8 for a 20% bonus.

Verification status (in-game comparisons recorded on 2026-10-27):
    Verified: research level multipliers; research PTV; research job cost with
        NPC facility tax, SCC surcharge, and Alpha clone tax; structure cost
        bonuses applying only to the gross job cost; research duration with
        skills and structure time role bonuses composing multiplicatively.
    Assumed: research rig and implant bonuses are further independent factors.
    Unresolved: the client's exact rounding. Whole-ISK, per-component half-up
        rounding (:meth:`JobCost.to_whole_isk`) usually matches to within 1-2 ISK.

Sources:
    https://wiki.eveuniversity.org/Research
    https://wiki.eveuniversity.org/Manufacturing#Total_job_cost
    https://wiki.eveuniversity.org/Upwell_structures#Engineering_complexes
    https://www.eveonline.com/news/view/industry-3rd-party-developers
    https://www.eveonline.com/news/view/viridian-expansion-notes
"""

import math
from collections.abc import Iterable
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
"""Research time reduction per Advanced Industry level, for ME and TE research."""

RESEARCH_SCC_RATE = 0.02
"""SCC surcharge rate for ME and TE research jobs, applied to PTV."""

MANUFACTURING_SCC_RATE = 0.04
"""SCC surcharge rate for manufacturing jobs, applied to PTV."""

ALPHA_CLONE_TAX_RATE = 0.0025
"""Additional tax rate for Alpha clone characters, applied to PTV."""

NPC_FACILITY_TAX_RATE = 0.0025
"""Facility tax rate at NPC stations, applied to PTV."""

MAX_SKILL_LEVEL = 5


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
        if not 0 <= level <= MAX_SKILL_LEVEL:
            raise ValueError(f"skill level must be 0 to {MAX_SKILL_LEVEL}, got {level}")
    return (1 - RESEARCH_SKILL_BONUS_PER_LEVEL * primary_skill_level) * (
        1 - ADVANCED_INDUSTRY_BONUS_PER_LEVEL * advanced_industry_level
    )


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
