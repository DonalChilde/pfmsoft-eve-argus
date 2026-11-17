"""Render collected PI inputs as a directly openable offline browser directory."""

from dataclasses import asdict, dataclass
from decimal import Decimal

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from whenever import Instant

from pfmsoft.eve_argus.helpers.package_resource import load_package_resource_text
from pfmsoft.eve_argus.pi.catalog import mining_planet_types
from pfmsoft.eve_argus.pi.models import CostBoundary, Tier, validate_tax_rate
from pfmsoft.eve_argus.reports.pi_browser import PiMarketInputs

BROWSER_FILES = (
    "index.html",
    "engine.js",
    "app.js",
    "styles.css",
    "decimal.js",
    "decimal-LICENCE.txt",
)


@dataclass(slots=True, kw_only=True, frozen=True)
class _BrowserPayload:
    """Exact snapshot facts and initial assumptions, not precalculated outcomes.

    Attributes:
        inputs: Collected prices, recipes, source provenance, and notices.
        tax_rate: Initial effective customs fraction, editable in the browser.
        intermediate_boundary: Initial treatment of expanded intermediate output.
        mining_type_ids: Materials with supported single-planet mining/refining.
    """

    inputs: PiMarketInputs
    tax_rate: Decimal
    intermediate_boundary: CostBoundary
    mining_type_ids: tuple[int, ...]


def _json_value(value: object) -> str:
    """Encode exact monetary strings and timestamps without binary floats."""
    match value:
        case Decimal():
            return format(value, "f")
        case Instant():
            return value.format_iso()
        case _:
            raise TypeError(
                f"Unsupported PI browser JSON value: {type(value).__name__}."
            )


def render_pi_browser(
    inputs: PiMarketInputs,
    *,
    tax_rate: Decimal = Decimal("0.06"),
    intermediate_boundary: CostBoundary = CostBoundary.ON_PLANET,
) -> dict[str, str]:
    """Render all files before writing; local classic scripts work under file://."""
    validate_tax_rate(tax_rate)
    if type(intermediate_boundary) is not CostBoundary:
        raise ValueError("Invalid intermediate customs boundary.")
    catalog = {row.material.type_id: row.material for row in inputs.materials}
    payload = _BrowserPayload(
        inputs=inputs,
        tax_rate=tax_rate,
        intermediate_boundary=intermediate_boundary,
        mining_type_ids=tuple(
            type_id
            for type_id, material in catalog.items()
            if material.tier <= Tier.P2
            and mining_planet_types(catalog=catalog, type_id=type_id)
        ),
    )
    environment = Environment(
        loader=PackageLoader("pfmsoft.eve_argus", "templates"),
        autoescape=select_autoescape(("html", "jinja2")),
        undefined=StrictUndefined,
    )
    environment.policies["json.dumps_kwargs"] = {
        "default": _json_value,
        "sort_keys": True,
        "allow_nan": False,
    }
    outputs = {
        "index.html": environment.get_template("pi_browser/index.html.jinja2").render(
            payload=asdict(payload), inputs=inputs
        )
    }
    for name in BROWSER_FILES[1:]:
        resource = {
            "decimal.js": "vendor/decimal.js",
            "decimal-LICENCE.txt": "vendor/LICENCE.md",
        }.get(name, name)
        outputs[name] = load_package_resource_text(
            "pfmsoft.eve_argus.templates", f"pi_browser/{resource}"
        )
    return outputs
