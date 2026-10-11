from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Generic, TypeVar


class ProviderStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"
    AUTH_ERROR = "auth_error"
    PARSE_ERROR = "parse_error"
    UNAVAILABLE = "unavailable"


class Capability(str, Enum):
    LIVE_PRICES = "live_prices"
    MULTI_CITY = "multi_city"
    FLEXIBLE_DATES = "flexible_dates"
    FILTERS = "filters"
    BOOKING_LINKS = "booking_links"


@dataclass(frozen=True)
class ProviderCapabilities:
    values: frozenset[Capability] = field(default_factory=frozenset)

    def supports(self, capability: Capability) -> bool:
        return capability in self.values


T = TypeVar("T")


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    provider: str
    status: ProviderStatus
    data: T | None = None
    retrieved_at: str = field(
        default_factory=lambda: (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
    )
    warning: str | None = None
    request_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {ProviderStatus.OK, ProviderStatus.EMPTY}

    @property
    def items(self) -> list[Any]:
        if isinstance(self.data, list):
            return self.data
        return []


class ProviderError(RuntimeError):
    status = ProviderStatus.UNAVAILABLE


class ProviderConfigurationError(ProviderError):
    """Missing credentials or an intentionally disabled integration."""


class ExperimentalProviderDisabled(ProviderConfigurationError):
    pass


class ProviderAuthError(ProviderError):
    status = ProviderStatus.AUTH_ERROR


class ProviderRateLimitError(ProviderError):
    status = ProviderStatus.RATE_LIMITED


class ProviderTimeoutError(ProviderError):
    status = ProviderStatus.TIMEOUT


class ProviderParseError(ProviderError):
    status = ProviderStatus.PARSE_ERROR


class ProviderBlockedError(ProviderError):
    status = ProviderStatus.BLOCKED


class ProviderUnavailableError(ProviderError):
    status = ProviderStatus.UNAVAILABLE
