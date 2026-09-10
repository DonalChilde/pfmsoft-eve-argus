"""Application settings for pfmsoft-eve-argus.

The application directory setting can be configured via an environment variable or .env file.

Other settings are also configurable via a TOML configuration file in the application directory.
"""

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

from pfmsoft.eve_link.settings import EsiLinkSettings
from pfmsoft.eve_link.settings import get_settings as get_eve_link_settings
from pfmsoft.eve_sd.settings import EveSDSettings
from pfmsoft.eve_sd.settings import get_settings as get_eve_sd_settings
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typer import get_app_dir

from pfmsoft.eve_argus import (
    __app_name__,
    __url__,
    __version__,
)
from pfmsoft.eve_argus.helpers.package_resource import load_package_resouce_text

logger = logging.getLogger(__name__)

# Typical application settings
USER_AGENT = f"{__app_name__}/{__version__} ({__url__})"
APP_DOMAIN = f"{__app_name__}"
APP_NAMESPACE = uuid5(NAMESPACE_DNS, __app_name__)
ENV_PREFIX = __app_name__.replace(".", "_").replace("-", "_").upper() + "_"
SETTINGS_KEY = ENV_PREFIX + "SETTINGS"
TOML_SETTINGS_FILE = f"{__app_name__}.toml"


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
    compatibility_date: str | None = None
    """The date used for ESI compatibility checks, in YYYY-MM-DD format. If None, the 
    most recent valid date is used."""


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


class RateLimitSettings(BaseModel):
    """Settings for rate limiting of ESI requests."""

    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    max_rate: float = Field(default=50.0, gt=0)
    """The maximum rate for ESI requests per time period."""
    time_period: float = Field(default=1.0, gt=0)
    """The time period over which the maximum rate is applied."""


class EveArgusTomlSettings(BaseModel):
    """Settings loaded from the TOML configuration file."""

    model_config = ConfigDict(extra="forbid")

    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    """The rate limit settings for ESI requests."""


def _default_settings() -> EveArgusTomlSettings:
    """Return the default TOML settings."""
    return EveArgusTomlSettings(rate_limit=RateLimitSettings())


def _load_toml_settings(toml_file: Path) -> EveArgusTomlSettings:
    """Load settings from a TOML configuration file."""
    if not toml_file.exists():
        logger.warning("TOML file '%s' does not exist.", toml_file)
        raise ValueError(f"TOML file '{toml_file}' does not exist.")
    if toml_file.is_dir():
        logger.warning("TOML file '%s' is a directory.", toml_file)
        raise ValueError(f"TOML file '{toml_file}' is a directory.")
    with toml_file.open("rb") as f:
        try:
            toml_data = tomllib.load(f)
            if not toml_data:
                # If the TOML file is empty, log the information and return the default settings.
                # This is not considered an error; the application can proceed with default settings.
                logger.info(
                    "TOML file '%s' is empty. Using default settings.", toml_file
                )
                return _default_settings()
            logger.info("Settings loaded from TOML file are: %r", toml_data)
        except Exception as e:
            logger.error("Failed to read TOML file '%s': %s", toml_file, e)
            raise e
    try:
        toml_settings = EveArgusTomlSettings.model_validate(toml_data)
    except Exception as e:
        logger.error("Failed to load TOML settings from '%s': %s", toml_file, e)
        # FIXME Use an argus specific exception instead of ValueError, include possible solutions.
        raise ValueError(f"Failed to load TOML settings from '{toml_file}': {e}") from e
    return toml_settings


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
    _ensure_toml_settings_file(application_directory)

    # Apply TOML settings if available.
    toml_settings = _load_toml_settings(application_directory / TOML_SETTINGS_FILE)
    settings = _apply_toml_settings(settings, toml_settings)
    return settings


def _ensure_toml_settings_file(application_directory: Path) -> None:
    """Ensure that the TOML settings file exists in the application directory.

    If the file does not exist, it will be created with default settings.
    """
    toml_file = application_directory / TOML_SETTINGS_FILE
    if toml_file.exists():
        if not toml_file.is_file():
            raise ValueError(f"TOML settings path '{toml_file}' is not a file.")
        return

    # load the toml-settings-example.toml file as a package resource
    example_toml = load_package_resouce_text(
        "pfmsoft.eve_argus", "toml-settings-example.toml"
    )
    toml_file.write_text(example_toml)


def _apply_toml_settings(
    settings: EveArgusSettings, toml_settings: EveArgusTomlSettings
) -> EveArgusSettings:
    """Apply TOML settings to the runtime settings."""
    settings.eve_link_settings.max_rate = toml_settings.rate_limit.max_rate
    settings.eve_link_settings.time_period = toml_settings.rate_limit.time_period

    return settings
