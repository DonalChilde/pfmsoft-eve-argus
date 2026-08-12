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

"""This script fetches market groups from the EVE Online API and saves them to a file or prints them to stdout."""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer
from pfmsoft.eve_link import EsiLink, EsiRequest, EsiSchema, SimpleRequests
from pfmsoft.eve_link import request_factory as RF
from pfmsoft.eve_link.esi_request.models import (
    EsiRequestGroup,
    EsiResponse,
    EsiResponseGroup,
    FailedEsiResponse,
)
from pfmsoft.eve_link.settings import get_settings
from pfmsoft.eve_snippets.typer.output import output_to_stdout_or_file
from pydantic import RootModel
from rich.console import Console
from whenever import Instant

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.WARNING

app = typer.Typer(no_args_is_help=True)


@dataclass(slots=True, kw_only=True)
class MarketGroupDetail:
    """TypedDict for market group details response."""

    market_group_id: int
    name: str
    description: str | None = None
    parent_group_id: int | None = None
    types: list[int] = field(default_factory=list[int])


MarketGroupDetailsRoot = RootModel[MarketGroupDetail]
MarketGroupIdsRoot = RootModel[list[int]]


@dataclass(slots=True, kw_only=True)
class MarketGroupDetailsResponse:
    received_at: Instant
    """The timestamp when the market orders were fetched."""
    expires_at: Instant | None
    """The timestamp when the market orders will expire, if provided by the ESI response."""
    market_groups: dict[int, MarketGroupDetail] = field(
        default_factory=dict[int, MarketGroupDetail]
    )
    """The market group details keyed by market group ID."""
    path_str: dict[int, tuple[str, ...]] = field(
        default_factory=dict[int, tuple[str, ...]]
    )
    path_int: dict[int, tuple[int, ...]] = field(
        default_factory=dict[int, tuple[int, ...]]
    )

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the MarketGroupDetailsResponse to a JSON string."""
        return MarketGroupDetailsResponseRoot(root=self).model_dump_json(indent=indent)


MarketGroupDetailsResponseRoot = RootModel[MarketGroupDetailsResponse]


@app.command()
def main(
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
    """Fetches market groups from the EVE Online API.

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
    esi_schema = simple_requests.get_schema(compatibility_date=None)
    esi_link = simple_requests.esi_link_factory()

    async def fetch():
        async with esi_link:
            market_group_ids_response = await fetch_market_groups(
                esi_link=esi_link, esi_schema=esi_schema
            )
            checked_response = _check_failed_response(
                esi_response=market_group_ids_response
            )
            response_status_message(esi_response=checked_response, messenger=messenger)
            market_group_ids = MarketGroupIdsRoot(
                root=checked_response.response_data
            ).root
            market_details_response = await fetch_market_groups_details(
                esi_link=esi_link,
                esi_schema=esi_schema,
                market_group_ids=market_group_ids,
            )
            checked_response_group = _check_failed_response_group(
                esi_response_group=market_details_response
            )
            market_group_details = _collect_market_group_details(
                esi_response_group=checked_response_group
            )
            return (
                market_group_details,
                checked_response.received_at_instant,
                checked_response.expires_at_instant,
            )

    market_group_details, timestamp, expires_at = asyncio.run(fetch())
    processed_groups = _process_market_group_details(
        market_group_details=market_group_details,
        timestamp=timestamp,
        expires_at=expires_at,
    )
    data_string = processed_groups.serialize(indent=indent)
    if output_directory == Path("-"):
        filepath = Path("-")
    else:
        if filename is None:
            filename = _generate_filename(
                given_filename=filename, received_at=timestamp
            )
        filepath = output_directory / filename
    output_to_stdout_or_file(
        data_string=data_string,
        filepath=filepath,
        overwrite=overwrite,
        messenger=messenger,
    )


#############################################################################
# These functions should be edited to be appropriate for the specific script.
#############################################################################


def _process_market_group_details(
    market_group_details: dict[int, MarketGroupDetail],
    timestamp: Instant,
    expires_at: Instant | None,
) -> MarketGroupDetailsResponse:
    """Processes the market group details and returns a structured MarketGroupDetailsResponse."""
    path_str: dict[int, tuple[str, ...]] = {}
    path_int: dict[int, tuple[int, ...]] = {}

    def build_path_str(market_group_id: int) -> tuple[str, ...]:
        if market_group_id in path_str:
            return path_str[market_group_id]
        market_group = market_group_details[market_group_id]
        if market_group.parent_group_id is None:
            path_str[market_group_id] = (market_group.name,)
        else:
            parent_path_str = build_path_str(market_group.parent_group_id)
            path_str[market_group_id] = parent_path_str + (market_group.name,)
        return path_str[market_group_id]

    def build_path_int(market_group_id: int) -> tuple[int, ...]:
        if market_group_id in path_int:
            return path_int[market_group_id]
        market_group = market_group_details[market_group_id]
        if market_group.parent_group_id is None:
            path_int[market_group_id] = (market_group_id,)
        else:
            parent_path_int = build_path_int(market_group.parent_group_id)
            path_int[market_group_id] = parent_path_int + (market_group_id,)
        return path_int[market_group_id]

    for mg_id in market_group_details.keys():
        build_path_str(mg_id)
        build_path_int(mg_id)

    return MarketGroupDetailsResponse(
        received_at=timestamp,
        expires_at=expires_at,
        market_groups=market_group_details,
        path_str=path_str,
        path_int=path_int,
    )


def _collect_market_group_details(
    esi_response_group: EsiResponseGroup,
) -> dict[int, MarketGroupDetail]:
    """Collects market group details from the ESI response group and returns a dictionary of market group details."""
    market_group_details: dict[int, MarketGroupDetail] = {}
    for _, response in esi_response_group.successful_responses.items():
        market_group_detail = MarketGroupDetailsRoot(root=response.response.json).root
        market_group_details[market_group_detail.market_group_id] = market_group_detail
    return market_group_details


def _generate_filename(given_filename: str | None, received_at: Instant) -> str:
    """Generates a default filename for the market orders response based on the region ID and timestamp."""
    if given_filename is not None:
        return given_filename

    return f"Market_Groups_Processed_{received_at.timestamp_nanos()}.json"


async def fetch_market_groups(
    esi_link: EsiLink, esi_schema: EsiSchema
) -> EsiResponse | FailedEsiResponse:
    """Fetches the list of market group IDs from the EVE Online API."""
    esi_request = RF.market.get_markets_groups()
    return await esi_link.make_request(esi_request=esi_request, schema=esi_schema)


async def fetch_market_groups_details(
    esi_link: EsiLink, esi_schema: EsiSchema, *, market_group_ids: list[int]
) -> EsiResponseGroup:
    """Fetches the details for each market group ID from the EVE Online API."""
    requests = [
        RF.market.get_markets_groups_market_group_id(market_group_id=market_group_id)
        for market_group_id in market_group_ids
    ]
    request_group = EsiRequestGroup(requests={r.request_id: r for r in requests})
    return await esi_link.make_requests(esi_requests=request_group, schema=esi_schema)


################################################################
# These functions should not need to be edited for a new script.
################################################################
def _check_failed_response_group(
    esi_response_group: EsiResponseGroup,
) -> EsiResponseGroup:
    if esi_response_group.failed_responses:
        for failed_response in esi_response_group.failed_responses.values():
            try:
                _check_failed_response(failed_response)
            except ValueError:
                # TODO think about error output more.
                pass
        raise typer.Exit(code=1)
    return esi_response_group


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
