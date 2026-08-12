from dataclasses import dataclass
from typing import Self

from whenever import Instant


@dataclass(slots=True, kw_only=True)
class EsiModelBase:
    """Base class for ESI sourced models."""

    received_at: str
    """The timestamp as an ISO 8601 string when the ESI data was fetched."""
    expires_at: str | None
    """The timestamp as an ISO 8601 string when the ESI data will expire, if provided by 
    the ESI response."""

    @property
    def expires_at_instant(self) -> Instant | None:
        """The timestamp when the ESI data will expire as an Instant, if available."""
        return Instant.parse_iso(self.expires_at) if self.expires_at else None

    @property
    def received_at_instant(self) -> Instant:
        """The timestamp when the ESI data was fetched as an Instant."""
        return Instant.parse_iso(self.received_at)

    def serialize(self, indent: int | None = 2) -> str:
        """Serializes the ESI model to a JSON string."""
        raise NotImplementedError("Subclasses must implement the serialize method.")

    @classmethod
    def deserialize(cls, data: str) -> Self:
        """Deserializes a JSON string to an ESI model."""
        raise NotImplementedError("Subclasses must implement the deserialize method.")
