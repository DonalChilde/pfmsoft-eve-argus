"""Common models and protocols for the application."""

from dataclasses import dataclass
from typing import Protocol, Self

from whenever import Instant


class Serializable(Protocol):
    """Defines JSON serialization for report models."""

    def serialize(self, indent: int | None = 2) -> str:
        """Serialize the object to a JSON string."""
        raise NotImplementedError

    @classmethod
    def deserialize(cls, data: str) -> Self:
        """Deserialize the object from a JSON string."""
        raise NotImplementedError


@dataclass(slots=True, kw_only=True)
class TimeStamped:
    """Provides access to ESI response timestamps."""

    received_at: str
    expires_at: str | None

    @property
    def expires_at_instant(self) -> Instant | None:
        """Return the expiration timestamp, if available."""
        return Instant.parse_iso(self.expires_at) if self.expires_at else None

    @property
    def received_at_instant(self) -> Instant:
        """Return the timestamp when the ESI data was fetched."""
        return Instant.parse_iso(self.received_at)
