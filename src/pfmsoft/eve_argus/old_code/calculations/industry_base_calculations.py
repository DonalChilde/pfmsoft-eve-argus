"""Industry calculations using the most basic inputs."""

from enum import Enum
from math import ceil, floor
from typing import Any, TypedDict

# TODO add types for arguments for clarity
# TODO Thorough testing, with explicit examples in a main function
# TODO step by step documentation for all the calculations, with examples and references to ESI docs and other sources.

type TypeId = int
"""Type alias for type IDs."""
type Quantity = int
"""Type alias for quantities."""
type Price = float
"""Type alias for prices."""
type BaseMaterials = dict[TypeId, Quantity]
"""Type alias for base materials dict[TypeId, Quantity]."""
type MaterialPrices = dict[TypeId, Price]
"""Type alias for prices dict[TypeId, Price]."""

RESEARCH_TIME_MULTIPLIER: list[float] = [
    1,
    29 / 21,
    23 / 7,
    39 / 5,
    278 / 15,
    928 / 21,
    2200 / 21,
    5251 / 21,
    4163 / 7,
    29660 / 21,
]
"""List of research time multipliers for steps 1-10.

These multipliers are used to calculate the research time for each step.
0-1 is one, and 1-2 is 29/21, or about 1.380952381.
The progression is 2**1.25, or about 2.3784 from lvl 2 onward. Math needs to be done to see if the 
fractions, or the decimal, is more accurate. The fractions are from fuzzworks blueprint 
calculator, and seem to be accurate. But the difference between the two methods is so 
small that it would be hard to tell. Test in-game.
"""


class ActivityId(Enum):
    """Constants for industry activity IDs."""

    MANUFACTURING = 1
    RESEARCHING_TIME_EFFICIENCY = 3
    RESEARCHING_MATERIAL_EFFICIENCY = 4
    COPYING = 5
    INVENTION = 8
    REACTIONS = 11


# TODO at this level, can one cost dict cover all the actions?
class JobCosts(TypedDict):
    """TypedDict for job costs."""

    job_cost: float
    facility_tax: float
    scc: float
    alpha: float


def reprocess(base_materials: dict[int, int], reprocess_yield: float) -> dict[int, int]:
    """Calculates the materials obtained from reprocessing.

    base_materials for reprocessing comes from the typeMaterials.jsonl SDE dataset.

    Reprocessing calculations round down to the nearest whole number.

    Args:
        base_materials (dict[int, int]): A dictionary of material IDs and their quantities.
        reprocess_yield (float): The reprocessing yield as a decimal (e.g., 0.5 for 50%).

    Returns:
        dict[int, int]: A dictionary of reprocessed materials with their quantities.
    """
    reprocessed_materials: dict[int, int] = {}
    for material_id, quantity in base_materials.items():
        reprocessed_quantity = floor(quantity * reprocess_yield)
        reprocessed_materials[material_id] = reprocessed_quantity
    return reprocessed_materials


def eiv(base_materials: dict[int, int], adjusted_prices: dict[int, float]) -> float:
    """Calculates the estimated item value (EIV) of a set of materials.

    EIV is calculated from the base materials of a blueprint, with no ME correction.

    Invention EIV is calculated from the material requirements from the produced T2 blueprint.

    Args:
        base_materials (dict[int, int]): A dictionary of material IDs and their quantities.
        adjusted_prices (dict[int, float]): A dictionary of material IDs and their adjusted prices.

    Returns:
        float: The estimated item value of the materials.
    """
    total_value = 0.0
    for material_id, quantity in base_materials.items():
        if material_id in adjusted_prices:
            total_value += adjusted_prices[material_id] * quantity
        else:
            raise ValueError(
                f"Material ID {material_id} not found in adjusted_prices dictionary."
            )

    return total_value


def process_time_value(time_required: int, eiv: float, base_time: int) -> int:
    """Calculates the process time value (PTV) based on the time required and EIV.

    Required for researching ME and TE.

    Args:
        time_required (int): The time required for the process in seconds.
        eiv (float): The estimated item value of blueprint product.
        base_time (int): The base time for the process in seconds.
    """
    ptv = ceil(time_required * (0.02 / base_time) * eiv)
    return ptv


def manufacturing_materials_required(
    base_materials: dict[int, int],
    runs: int,
    me: float,
    structure: float = 0.0,
    rig: float = 0.0,
) -> dict[int, int]:
    """Calculates the materials required for a manufacturing job.

    Args:
        base_materials (dict[int, int]): The base materials required for the job.
        runs (int): The number of runs for the job.
        me (float): Material efficiency factor.
        structure (float): Structure bonus factor.
        rig (float): Rig bonus factor.

    Returns:
        dict[int, int]: A dictionary of required materials with their quantities.
    """
    if runs < 1:
        raise ValueError("Runs must be one or greater.")

    required_materials: dict[int, int] = {}
    for material_id, quantity in base_materials.items():
        req_mats = quantity * (1 - me) * (1 - structure) * (1 - rig)
        if req_mats < 0:
            req_mats = 1
        required_materials[material_id] = ceil(req_mats * runs)
    return required_materials


def manufacturing_job_cost(
    eiv: float,
    system_cost_index: float,
    structure_bonus: float = 0.0,
    facility_tax: float = 0.0,
    scc: float = 0.04,
    alpha_rate: float = 0.0025,
    is_alpha: bool = False,
) -> JobCosts:
    """Calculates the cost of a manufacturing job.

    There is still some question about rounding vs ceil behavior, but this
    should be within a couple of isk of the actual cost.

    Args:
        eiv (float): Estimated Industry Value of the job.
        system_cost_index (float): Cost index of the system.
        structure_bonus (float): Bonus from the structure used.
        facility_tax (float): Tax applied by the facility.
        scc (float): Standard Concord Charge.
        alpha_rate (float): Alpha clone rate.
        is_alpha (bool): Whether the job is being run by an alpha clone.

    Returns:
        JobCosts: A dictionary containing the job cost, facility tax, SCC, and alpha cost.
    """
    job_cost = round(eiv * system_cost_index * (1 - structure_bonus))
    result = JobCosts(
        job_cost=job_cost,
        facility_tax=round(eiv * facility_tax),
        scc=round(eiv * scc),
        alpha=round(eiv * alpha_rate) if is_alpha else 0.0,
    )
    return result


def research_job_cost(
    ptv: float,
    system_cost_index: float,
    structure_bonus: float = 0.0,
    facility_tax: float = 0.0,
    scc: float = 0.04,
    alpha_rate: float = 0.0025,
    is_alpha: bool = False,
) -> JobCosts:
    """Calculates the cost of a research ME or TE job.

    There is still some question about rounding vs ceil behavior, but this
    should be within a couple of isk of the actual cost.

    Args:
        ptv (float): Process Time Value of the job.
        system_cost_index (float): Cost index of the system.
        structure_bonus (float): Bonus from the structure used.
        facility_tax (float): Tax applied by the facility.
        scc (float): Standard Concord Charge.
        alpha_rate (float): Alpha clone rate.
        is_alpha (bool): Whether the job is being run by an alpha clone.

    Returns:
        JobCosts: A dictionary containing the job cost, facility tax, SCC, and alpha cost.
    """
    job_cost = round(ptv * system_cost_index * (1 - structure_bonus))
    result = JobCosts(
        job_cost=job_cost,
        facility_tax=round(ptv * facility_tax),
        scc=round(ptv * scc),
        alpha=round(ptv * alpha_rate) if is_alpha else 0.0,
    )
    return result


def invention_job_cost(
    eiv: float,
    system_cost_index: float,
    structure_bonus: float = 0.0,
    facility_tax: float = 0.0,
    scc: float = 0.04,
    alpha_rate: float = 0.0025,
    is_alpha: bool = False,
) -> JobCosts:
    """Calculates the cost of an invention job.

    There is still some question about rounding vs ceil behavior, but this
    should be within a couple of isk of the actual cost.

    Args:
        eiv (float): Estimated Industry Value of the job.
        system_cost_index (float): Cost index of the system.
        structure_bonus (float): Bonus from the structure used.
        facility_tax (float): Tax applied by the facility.
        scc (float): Standard Concord Charge.
        alpha_rate (float): Alpha clone rate.
        is_alpha (bool): Whether the job is being run by an alpha clone.

    Returns:
        JobCosts: A dictionary containing the job cost, facility tax, SCC, and alpha cost.
    """
    job_cost_base = eiv * 0.02
    job_cost = round(job_cost_base * system_cost_index * (1 - structure_bonus))
    result = JobCosts(
        job_cost=job_cost,
        facility_tax=round(job_cost_base * facility_tax),
        scc=round(job_cost_base * scc),
        alpha=round(job_cost_base * alpha_rate) if is_alpha else 0.0,
    )
    return result


def copy_job_cost(
    eiv: float,
    system_cost_index: float,
    structure_bonus: float = 0.0,
    facility_tax: float = 0.0,
    scc: float = 0.04,
    alpha_rate: float = 0.0025,
    is_alpha: bool = False,
) -> JobCosts:
    """Calculates the cost of a copy job.

    There is still some question about rounding vs ceil behavior, but this
    should be within a couple of isk of the actual cost.

    Args:
        eiv (float): Estimated Industry Value of the job.
        system_cost_index (float): Cost index of the system.
        structure_bonus (float): Bonus from the structure used.
        facility_tax (float): Tax applied by the facility.
        scc (float): Standard Concord Charge.
        alpha_rate (float): Alpha clone rate.
        is_alpha (bool): Whether the job is being run by an alpha clone.

    Returns:
        JobCosts: A dictionary containing the job cost, facility tax, SCC, and alpha cost.
    """
    job_cost_base = eiv * 0.02
    job_cost = round(job_cost_base * system_cost_index * (1 - structure_bonus))
    result = JobCosts(
        job_cost=job_cost,
        facility_tax=round(job_cost_base * facility_tax),
        scc=round(job_cost_base * scc),
        alpha=round(job_cost_base * alpha_rate) if is_alpha else 0.0,
    )
    return result


def manufacturing_time(
    base_time: int,
    te: float,
    runs: int,
    structure: float = 0.0,
    rigs: float = 0.0,
    skills: float = 0.0,
    implants: float = 0.0,
) -> int:
    """Calculates the manufacturing time for a job.

    Needs more documentation around skills and implants, but the idea is that you can input the total bonus from skills and implants here.
    """
    elapsed = (
        base_time
        * (1 - te)
        * (1 - structure)
        * (1 - skills)
        * (1 - implants)
        * (1 - rigs)
    )
    elapsed = ceil(elapsed * runs)

    return elapsed


def research_time(
    base_time: int,
    beginning_runs: int,
    desired_runs: int,
    skills: float,
    implants: float,
    structure: float,
    rigs: float,
) -> int:
    """Calculates the time required for a research job."""
    base_required = base_research_time(
        bp_time=base_time, beginning_runs=beginning_runs, desired_runs=desired_runs
    )
    time_required = (
        base_required * (1 - skills) * (1 - implants) * (1 - structure) * (1 - rigs)
    )
    time_required = ceil(time_required)

    return time_required


def invention_time(
    FOO: Any,
    base_time: int,
    runs: int,
    skills: float,
    structure: float,
    rigs: float,
) -> int:
    """Returns the time required for an invention job."""
    # TODO stub
    return 0


def copy_time() -> int:
    """Returns the time required for a copy job."""
    # TODO stub
    return 0


def base_research_time(
    bp_time: int, beginning_runs: int = 0, desired_runs: int = 10
) -> int:
    """Calculate the base time for research based on the blueprint time, already completed runs, and desired runs.

    Args:
        bp_time (int): The base time for the blueprint.
        beginning_runs (int): The number of already completed runs.
        desired_runs (int): The desired number of runs for the research job.

    Returns:
        int: The total base time for the research job in seconds.
    """
    if beginning_runs == 0:
        already_completed_time = 0
    else:
        already_completed_time = _research_time(runs=beginning_runs, base_time=bp_time)
    desired_time = _research_time(runs=desired_runs, base_time=bp_time)

    return desired_time - already_completed_time


def _research_time(runs: int, base_time: int) -> int:
    """Calculate the total research time based on runs and base time.

    Argh damned eve math. Got research multipliers from fuzzworks blueprint calculator.
    Seems accurate.

    Args:
        runs (int): The number of runs for the research job.
        base_time (int): The base time for the research job.

    Returns:
        int: The total research time in seconds.
    """
    metime = 0
    for i in range(0, runs):
        metime = round(metime + (RESEARCH_TIME_MULTIPLIER[i] * base_time))
    return metime


def reaction_time(**kwargs) -> int:  # type: ignore
    """Returns the time required for a reaction job."""
    # TODO stub
    return 0


def reaction_cost(**kwargs) -> JobCosts:  # type: ignore
    """Returns the cost of a reaction job."""
    # TODO stub
    result = JobCosts(
        job_cost=0.0,
        facility_tax=0.0,
        scc=0.0,
        alpha=0.0,
    )
    return result
