"""Application settings for pfmsoft-eve-argus."""

from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

from pfmsoft.eve_link.settings import EsiLinkSettings
from pfmsoft.eve_link.settings import get_settings as get_eve_link_settings
from pfmsoft.eve_sd.settings import EveSDSettings
from pfmsoft.eve_sd.settings import get_settings as get_eve_sd_settings
from pydantic_settings import BaseSettings, SettingsConfigDict
from typer import get_app_dir

from pfmsoft.eve_argus import (
    __app_name__,
    __url__,
    __version__,
)

# Typical application settings
USER_AGENT = f"{__app_name__}/{__version__} ({__url__})"
APP_DOMAIN = f"{__app_name__}"
APP_NAMESPACE = uuid5(NAMESPACE_DNS, __app_name__)
ENV_PREFIX = __app_name__.replace(".", "_").replace("-", "_").upper() + "_"
SETTINGS_KEY = ENV_PREFIX + "SETTINGS"


@dataclass(slots=True)
class EveArgusSettings:
    """Runtime settings consumed by pfmsoft-eve-argus."""

    application_directory: Path
    """The directory where the application stores its data and logs."""
    logging_directory: Path
    """The directory where the application stores its log files."""
    static_database: Path
    """The path to the static database file used by the application."""
    eve_link_settings: EsiLinkSettings
    """The settings for the pfmsoft-eve-link package used by the application."""
    eve_sd_settings: EveSDSettings
    """The settings for the pfmsoft-eve-sd package used by the application."""


class EveArgusSettingsPydantic(BaseSettings):
    """Settings for the application loaded from environment variables and optional `.env` files.

    Values are read from environment variables prefixed with the application name,
    altered to uppercase and with non-alphanumeric characters replaced by underscores.
    Values are also read from `.env` or `.env.dev` when present.

    The .env file name must be application specific, so that companion apps not not
    error when trying to load someone elses settings.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=("eve-argus.env", "eve-argus.env.dev"),
        env_file_encoding="utf-8",
    )

    application_directory: Path = Path(get_app_dir(__app_name__))


def get_settings(
    application_directory: Path | None = None,
) -> EveArgusSettings:
    """Build runtime settings from a Pydantic settings model or application directory.

    Args:
        application_directory (Path | None): Optional application directory path.
            If not provided, the default application directory is used.

    Returns:
        Runtime settings dataclass used by the application.

    Raises:
        ValueError: If the provided application directory exists but is not a directory.
    """
    if application_directory is None:
        # If the application directory is not provided, use the value from the Pydantic
        # settings model. This allows for environment variable overrides and .env file loading.
        application_directory = EveArgusSettingsPydantic().application_directory
    application_directory = application_directory.expanduser().resolve()
    if application_directory.exists() and not application_directory.is_dir():
        raise ValueError(
            f"Application directory '{application_directory}' exists but is not a directory."
        )
    settings = _initialize_settings(application_directory)
    return settings


def _initialize_settings(application_directory: Path) -> EveArgusSettings:
    """Build default runtime settings.

    Also ensures that the application directories exist.
    """
    settings = EveArgusSettings(
        application_directory=application_directory,
        logging_directory=application_directory / "logs",
        static_database=application_directory / "static-db.sqlite",
        eve_link_settings=get_eve_link_settings(
            application_directory=application_directory / "eve_link"
        ),
        eve_sd_settings=get_eve_sd_settings(
            application_directory=application_directory / "eve_sd"
        ),
    )
    # Ensure that the application directories exist.
    settings.application_directory.mkdir(parents=True, exist_ok=True)
    settings.logging_directory.mkdir(parents=True, exist_ok=True)
    return settings
