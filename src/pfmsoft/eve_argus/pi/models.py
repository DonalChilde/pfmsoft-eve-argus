"""Typed PI recipes, reusable source quotes, and per-stage cost breakdowns."""

from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum, StrEnum


class Tier(IntEnum):
    """PI extraction/refinement tiers, independent of production locations."""

    P0 = 0
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4


class PlanetType(StrEnum):
    """Planet types appearing in the PI raw-resource reference."""

    BARREN = "Barren"
    GAS = "Gas"
    ICE = "Ice"
    LAVA = "Lava"
    OCEANIC = "Oceanic"
    PLASMA = "Plasma"
    STORM = "Storm"
    TEMPERATE = "Temperate"


class MarketPriceBasis(StrEnum):
    """A uniform acquisition-price basis for all purchased scenario inputs."""

    JITA_BUY = "jita-buy-5"
    JITA_SELL = "jita-sell-5"
    HISTORY = "the-forge-history-10d"


class CostBoundary(StrEnum):
    """Whether a source is local to the consuming stage or awaits planetary import."""

    ON_PLANET = "on-planet"
    OFF_PLANET = "off-planet"


def _validate_nonnegative_decimal(value: object, *, name: str) -> None:
    """Reject invalid monetary values rather than propagating NaN or float prices."""
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal.")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative.")


def validate_tax_rate(tax_rate: Decimal) -> None:
    """Validate an effective customs rate as a fraction in the inclusive range 0-1."""
    _validate_nonnegative_decimal(tax_rate, name="tax_rate")
    if tax_rate > 1:
        raise ValueError("tax_rate must be at most 1 (100%).")


@dataclass(slots=True, kw_only=True, frozen=True)
class RecipeInput:
    """Units of one material consumed per complete recipe cycle.

    Attributes:
        type_id: Positive EVE inventory type ID of the consumed material.
        quantity: Positive whole units consumed per recipe cycle, not per output unit.
    """

    type_id: int
    quantity: int

    def __post_init__(self) -> None:
        """Validate material identity and whole positive recipe quantities."""
        if type(self.type_id) is not int or self.type_id <= 0:
            raise ValueError("Recipe input type_id must be a positive integer.")
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValueError("Recipe input quantity must be a positive integer.")


@dataclass(slots=True, kw_only=True, frozen=True)
class Material:
    """PI identity, per-unit customs base/volume, and per-cycle recipe.

    Raw-resource planet types are reference data, not measured extraction yields.
    Higher tiers derive mining eligibility through their recipe inputs.

    Attributes:
        type_id: Positive EVE inventory type ID.
        name: Human-readable material name.
        tier: Extraction/refinement tier, P0 through P4.
        volume: Cubic meters per material unit.
        taxable_base: ISK per unit used for customs valuation, not a market price.
        output_quantity: Positive whole output units per recipe cycle. P0 uses
            one unit as a reference quantity, not an extraction-yield estimate.
        inputs: Per-cycle ingredient requirements; empty only for P0.
        raw_planet_types: Planet types containing this P0 resource. Empty for
            higher tiers; an empty P0 value means no documented eligible planet.
    """

    type_id: int
    name: str
    tier: Tier
    volume: Decimal
    taxable_base: Decimal
    output_quantity: int
    inputs: tuple[RecipeInput, ...] = ()
    raw_planet_types: tuple[PlanetType, ...] = ()

    def __post_init__(self) -> None:
        """Validate local recipe shape; cross-material references need a catalog."""
        if type(self.type_id) is not int or self.type_id <= 0:
            raise ValueError("Material type_id must be a positive integer.")
        if not self.name.strip():
            raise ValueError("Material name must not be empty.")
        _validate_nonnegative_decimal(self.volume, name="volume")
        _validate_nonnegative_decimal(self.taxable_base, name="taxable_base")
        if type(self.output_quantity) is not int or self.output_quantity <= 0:
            raise ValueError("Material output_quantity must be a positive integer.")
        if (self.tier == Tier.P0) != (not self.inputs):
            raise ValueError("Only P0 materials may have no recipe inputs.")
        if len({item.type_id for item in self.inputs}) != len(self.inputs):
            raise ValueError(f"Duplicate input in recipe for {self.type_id}.")
        if self.tier != Tier.P0 and self.raw_planet_types:
            raise ValueError("Only P0 materials may declare raw-resource planets.")


@dataclass(slots=True, kw_only=True, frozen=True)
class SourcePrice:
    """A reusable per-unit quote with its customs boundary and upstream assumptions.

    A missing cost must have an explicit reason. A None market basis denotes a
    mining-only source; a None tax rate denotes a tax-independent market quote.
    ON_PLANET explicitly means local to the next consuming stage, not another
    planet whose transport/customs costs can be ignored.

    Attributes:
        source_id: Reference identifying the selected market or production source.
        label: Human-readable description of the source.
        type_id: EVE inventory type ID of the quoted material.
        unit_cost: ISK per unit at boundary, including any upstream charges;
            None means unavailable, while zero is a known zero cost.
        boundary: Whether the quote is local to the consuming stage or off-planet
            awaiting import. An exported production quote includes its export tax.
        market_basis: Shared pricing basis for purchased leaves; None for a
            source with no market purchases.
        tax_rate: Effective customs fraction, from zero to one, used in this
            source's cost; None for a tax-independent market quote.
        unavailable_reason: Required explanation when unit_cost is None;
            otherwise None.
    """

    source_id: str
    label: str
    type_id: int
    unit_cost: Decimal | None
    boundary: CostBoundary
    market_basis: MarketPriceBasis | None = None
    tax_rate: Decimal | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        """Reject invalid quotes and unexplained unavailable values."""
        if not self.source_id.strip() or not self.label.strip():
            raise ValueError("Source identity and label must not be empty.")
        if type(self.type_id) is not int or self.type_id <= 0:
            raise ValueError("Source type_id must be a positive integer.")
        if self.tax_rate is not None:
            validate_tax_rate(self.tax_rate)
        if self.unit_cost is None:
            if not self.unavailable_reason or not self.unavailable_reason.strip():
                raise ValueError("A missing unit_cost requires an unavailable_reason.")
        else:
            _validate_nonnegative_decimal(self.unit_cost, name="unit_cost")
            if self.unavailable_reason is not None:
                raise ValueError("A known unit_cost cannot have an unavailable_reason.")


@dataclass(slots=True, kw_only=True, frozen=True)
class InputCost:
    """One cycle's input requirement, retaining the exact selected source quote.

    Attributes:
        quantity: Whole material units required for one output recipe cycle.
        source: Selected quote, including upstream identity and assumptions.
        acquisition_cost: ISK for quantity at the quoted unit cost, excluding this
            stage's import tax; None when the source cost is unavailable.
        import_tax: ISK charged to import this requirement into the current stage;
            zero for an explicitly local source.
    """

    quantity: int
    source: SourcePrice
    acquisition_cost: Decimal | None
    import_tax: Decimal


@dataclass(slots=True, kw_only=True, frozen=True)
class StageCost:
    """Per-cycle costs and a reusable per-unit quote at the declared output boundary.

    Acquisition cost includes upstream charges embedded in source prices; the
    import/export fields are only this stage's new customs charges.

    Attributes:
        output_quantity: Whole output units produced per recipe cycle.
        inputs: Per-cycle input breakdowns in the product recipe's ingredient order.
        acquisition_cost: Total input acquisition ISK per cycle; None if any
            required input cost is unavailable, rather than a partial sum.
        import_tax: Total new input import tax in ISK per cycle, including known
            charges even when acquisition costs are unavailable.
        export_tax: New output export tax in ISK per cycle; zero if output stays local.
        total_cost: Acquisition plus import and export ISK per cycle; None when
            any required acquisition cost is unavailable.
        output: Reusable per-unit quote normalized by output_quantity, retaining
            the chosen output boundary, price basis, tax rate, and availability.
    """

    output_quantity: int
    inputs: tuple[InputCost, ...]
    acquisition_cost: Decimal | None
    import_tax: Decimal
    export_tax: Decimal
    total_cost: Decimal | None
    output: SourcePrice
