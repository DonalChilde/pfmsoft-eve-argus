"""Commands for fetching data."""

import typer

from pfmsoft.eve_argus.cli.fetch.corporation_blueprints import (
    app as fetch_corporation_blueprints_app,
)
from pfmsoft.eve_argus.cli.fetch.corporation_jobs import (
    app as fetch_corporation_jobs_app,
)
from pfmsoft.eve_argus.cli.fetch.hub_orders import app as fetch_hubs_app
from pfmsoft.eve_argus.cli.fetch.industry_systems import (
    app as fetch_industry_systems_app,
)
from pfmsoft.eve_argus.cli.fetch.market_history import app as fetch_market_history_app
from pfmsoft.eve_argus.cli.fetch.markets_prices import app as fetch_markets_prices_app
from pfmsoft.eve_argus.cli.fetch.region_orders import app as fetch_region_orders_app

app = typer.Typer(no_args_is_help=True, help="Commands for fetching data.")
app.add_typer(fetch_hubs_app)
app.add_typer(fetch_region_orders_app)
app.add_typer(fetch_market_history_app)
app.add_typer(fetch_markets_prices_app)
app.add_typer(fetch_industry_systems_app)
app.add_typer(fetch_corporation_jobs_app)
app.add_typer(fetch_corporation_blueprints_app)
