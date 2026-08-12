# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pfmsoft-eve-link>=0.4.5",
#     "typer>=0.26.8",
# ]
# [tool.uv]
# exclude-newer-package = {pfmsoft-eve-link = false}
# [tool.uv.sources]
# pfmsoft-eve-link = { git = "https://github.com/DonalChilde/pfmsoft-eve-link.git", branch = "dev" }
# ///

####################################################################################################
# run with `uv run <script>`
# Add this to the script config header to use the dev branch of pfmsoft-eve-link:
# [tool.uv.sources]
# pfmsoft-eve-link = { git = "https://github.com/DonalChilde/pfmsoft-eve-link.git", branch = "dev" }
# And this to override a default dependency cool-down
# [tool.uv]
# exclude-newer-package = {pfmsoft-eve-link = false}
####################################################################################################

"""This script fetches market orders for a given region ID from the EVE Online API and saves them to a file or prints them to stdout."""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, cast

import typer
from pydantic import RootModel
from rich.console import Console
from whenever import Instant

from pfmsoft.eve_link import EsiLink, EsiSchema, SimpleRequests
from pfmsoft.eve_link import request_factory as RF
from pfmsoft.eve_link.cli.helpers import output_to_stdout_or_file
from pfmsoft.eve_link.esi_request.models import EsiResponse, FailedEsiResponse
from pfmsoft.eve_link.settings import get_settings

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.WARNING

app = typer.Typer(no_args_is_help=True)


@dataclass(slots=True, kw_only=True)
class GetMarketsRegionIdOrdersDetail:
    """TypedDict for market orders response."""

    duration: int
    is_buy_order: bool
    issued: str
    location_id: int
    min_volume: int
    order_id: int
    price: float
    range: str
    system_id: int
    type_id: int
    volume_remain: int
    volume_total: int


RegionalOrdersRoot = RootModel[list[GetMarketsRegionIdOrdersDetail]]


@dataclass(slots=True, kw_only=True)
class DividedOrders:
    buy_orders: list[GetMarketsRegionIdOrdersDetail] = field(
        default_factory=list[GetMarketsRegionIdOrdersDetail]
    )
    sell_orders: list[GetMarketsRegionIdOrdersDetail] = field(
        default_factory=list[GetMarketsRegionIdOrdersDetail]
    )


TypeId = int
OrdersDict = dict[TypeId, DividedOrders]  # type_id -> DividedOrders


@dataclass(slots=True, kw_only=True)
class MarketOrdersResponse:
    region_id: int
    """The region ID for which the market orders were fetched."""
    received_at: Instant
    """The timestamp when the market orders were fetched."""
    expires_at: Instant | None
    """The timestamp when the market orders will expire, if provided by the ESI response."""
    orders: OrdersDict
    """The market orders divided by type ID and buy/sell orders."""

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the MarketOrdersResponse to a JSON string."""
        return MarketOrdersResponseRoot(root=self).model_dump_json(
            indent=indent,
        )


MarketOrdersResponseRoot = RootModel[MarketOrdersResponse]


@app.command()
def main(
    region_id: Annotated[
        int,
        typer.Option("--region-id", help="The region ID to fetch market orders for"),
    ],
    output_directory: Annotated[
        Path,
        typer.Option(
            "--to",
            help="Path to the directory where the market orders will be saved. Use '-' "
            "to print to stdout.",
            exists=False,
            file_okay=False,
            dir_okay=True,
            show_default=True,
        ),
    ] = Path("-"),
    filename: Annotated[
        str | None,
        typer.Option(
            "--filename",
            help="Name of the file to save the market orders to. If not given, a default "
            "filename will be generated. Ignored if output directory is '-'",
            show_default=True,
        ),
    ] = None,
    indent: Annotated[
        int,
        typer.Option(
            "--indent",
            help="Number of spaces to use for indentation in the output JSON",
            show_default=True,
        ),
    ] = 2,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Whether to suppress status output messages",
            show_default=True,
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Whether to overwrite the output file if it already exists",
            show_default=True,
        ),
    ] = False,
):
    """Fetches market orders for a given region ID from the EVE Online API.

    Response is saved to a file or printed to stdout.
    """
    if quiet:
        messenger = Console(stderr=True, quiet=True)
    else:
        messenger = Console(stderr=True)

    ###################################
    # Fetch the response and process it
    ###################################
    settings = get_settings()
    simple_requests = SimpleRequests(settings=settings)
    esi_schema = simple_requests.get_schema()
    esi_link = simple_requests.esi_link_factory()

    async def fetch() -> EsiResponse | FailedEsiResponse:
        async with esi_link:
            return await fetch_market_orders(
                esi_link=esi_link,
                esi_schema=esi_schema,
                region_id=region_id,
            )

    response = asyncio.run(fetch())
    response = _check_failed_response(esi_response=response)
    response_status_message(esi_response=response, messenger=messenger)
    processed_response = _process_response(esi_response=response)
    if output_directory == Path("-"):
        filepath = Path("-")
    else:
        if filename is None:
            filename = _generate_filename(given_filename=filename, response=response)
        filepath = output_directory / filename

    #######################################
    # Output the result to a file or stdout
    #######################################
    output_to_stdout_or_file(
        data_string=processed_response.serialize(indent=indent),
        filepath=filepath,
        overwrite=overwrite,
        messenger=messenger,
    )


#############################################################################
# These functions should be edited to be appropriate for the specific script.
#############################################################################
async def fetch_market_orders(
    esi_link: EsiLink, esi_schema: EsiSchema, *, region_id: int
) -> EsiResponse | FailedEsiResponse:
    """Fetches market orders for a given region ID from the EVE Online API."""
    esi_request = RF.market.get_markets_region_id_orders(
        region_id=region_id, order_type="all"
    )
    return await esi_link.make_request(esi_request=esi_request, schema=esi_schema)


def _generate_filename(given_filename: str | None, response: EsiResponse) -> str:
    """Generates a default filename for the market orders response based on the region ID and timestamp."""
    if given_filename is not None:
        return given_filename
    region_id = cast(int, response.esi_request.path_parameters["region_id"])
    timestamp = response.received_at_instant.timestamp_nanos()
    return f"GetMarketsRegionIdOrders_{region_id}_{timestamp}.json"


def _process_response(esi_response: EsiResponse) -> MarketOrdersResponse:
    """Processes the ESI response and returns a structured MarketOrdersResponse."""
    orders_by_type: dict[int, DividedOrders] = {}
    region_id = cast(int, esi_response.esi_request.path_parameters["region_id"])
    regional_orders = RegionalOrdersRoot(root=esi_response.response_data).root  # type: ignore
    for order in regional_orders:
        type_id = order.type_id
        if type_id not in orders_by_type:
            orders_by_type[type_id] = DividedOrders()
        if order.is_buy_order:
            orders_by_type[type_id].buy_orders.append(order)
        else:
            orders_by_type[type_id].sell_orders.append(order)
    received_at = esi_response.received_at_instant
    expires_at = esi_response.expires_at_instant

    return MarketOrdersResponse(
        region_id=region_id,
        received_at=received_at,
        expires_at=expires_at,
        orders=orders_by_type,
    )


################################################################
# These functions should not need to be edited for a new script.
################################################################
def _check_failed_response(
    esi_response: EsiResponse | FailedEsiResponse,
) -> EsiResponse:
    """Checks if the ESI response is a failed response and raises an error if so."""
    if isinstance(esi_response, FailedEsiResponse):
        logger.error("Failed response: %r", esi_response)
        raise ValueError(
            f"Failed request to: {esi_response.esi_request.operation_id}, "
            f"error messages: {esi_response.failed_response.error_messages}"
        )
    return esi_response


def response_status_message(esi_response: EsiResponse, messenger: Console) -> None:
    """Prints a status message about the ESI response."""
    if esi_response.expires_at_instant is None:
        messenger.print(
            f"Response from {esi_response.esi_request.operation_id} has no expiration time."
        )
    else:
        messenger.print(
            f"Response from {esi_response.esi_request.operation_id} expires at "
            f"{esi_response.expires_at_instant}, in {(esi_response.expires_at_instant - Instant.now()).format_iso()}."
        )


if __name__ == "__main__":
    logging.basicConfig(level=LOG_LEVEL)
    app()
