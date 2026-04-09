"""Shared constants, types, write-gate, and credential scrubbing for IB Blade MCP."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)

# Default limits for list operations (token efficiency)
DEFAULT_LIMIT = 25
MAX_SNAPSHOT_CONIDS = 50  # CP Gateway limit per snapshot request


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OrderSide(StrEnum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    """Order type."""

    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP_LMT"
    MIDPRICE = "MIDPRICE"


class TimeInForce(StrEnum):
    """Time-in-force (duration)."""

    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    OPG = "OPG"


class BarSize(StrEnum):
    """Historical data bar sizes."""

    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1m"


class Period(StrEnum):
    """Historical data periods."""

    SEC_30 = "30s"
    MIN_1 = "1min"
    MIN_5 = "5min"
    HOUR_1 = "1h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1m"
    YEAR_1 = "1y"


# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """Configuration for IB Client Portal Gateway access.

    The gateway runs locally (or via tunnel) and handles IB authentication.
    This MCP server connects to the gateway's REST API.
    """

    gateway_url: str
    account_id: str | None = None
    ssl_verify: bool = True

    @property
    def base_url(self) -> str:
        """Return the gateway API base URL."""
        return f"{self.gateway_url}/v1/api"


def resolve_config() -> ProviderConfig:
    """Parse IB configuration from environment variables.

    Required:
        IB_GATEWAY_URL — Client Portal Gateway URL (e.g. https://localhost:5000)

    Optional:
        IB_ACCOUNT_ID — default account ID (auto-detected if omitted)
        IB_SSL_VERIFY — verify SSL certs (default true; set false for self-signed gateway cert)
    """
    gateway_url = os.environ.get("IB_GATEWAY_URL", "").strip()
    if not gateway_url:
        raise ValueError(
            "IB Gateway URL not configured. Set IB_GATEWAY_URL "
            "(e.g. https://localhost:5000)"
        )

    # Strip trailing slash
    gateway_url = gateway_url.rstrip("/")

    account_id = os.environ.get("IB_ACCOUNT_ID", "").strip() or None
    ssl_verify = os.environ.get("IB_SSL_VERIFY", "true").strip().lower() != "false"

    return ProviderConfig(
        gateway_url=gateway_url,
        account_id=account_id,
        ssl_verify=ssl_verify,
    )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IBError(Exception):
    """Base exception for IB client errors."""

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.details = details


# ---------------------------------------------------------------------------
# Write / confirm gates
# ---------------------------------------------------------------------------


def is_write_enabled() -> bool:
    """Check if write operations are enabled via env var."""
    return os.environ.get("IB_WRITE_ENABLED", "").lower() == "true"


def check_write_gate() -> str | None:
    """Return an error message if writes are disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations are disabled. Set IB_WRITE_ENABLED=true to enable."
    return None


def check_confirm_gate(confirm: bool, action: str) -> str | None:
    """Return an error message if confirm is not set, else None."""
    if not confirm:
        return f"Error: {action} involves real money. Set confirm=true to proceed."
    return None


# ---------------------------------------------------------------------------
# Credential scrubbing
# ---------------------------------------------------------------------------


def scrub_credentials(text: str, config: ProviderConfig | None = None) -> str:
    """Remove tokens, session IDs, and sensitive data from error messages."""
    # Strip session tokens and cookies
    text = re.sub(r"(cookie[=:]\s*)\S+", r"\1****", text, flags=re.IGNORECASE)
    text = re.sub(r"(session[=:]\s*)\S+", r"\1****", text, flags=re.IGNORECASE)
    text = re.sub(r"(token[=:]\s*)\S+", r"\1****", text, flags=re.IGNORECASE)
    text = re.sub(r"(Authorization:\s*)\S+", r"\1****", text, flags=re.IGNORECASE)
    return text
