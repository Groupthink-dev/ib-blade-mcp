"""Shared pytest fixtures for IB Blade MCP tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from ib_mcp.models import ProviderConfig


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-set minimal env vars for all tests."""
    monkeypatch.setenv("IB_GATEWAY_URL", "https://localhost:5000")
    monkeypatch.setenv("IB_ACCOUNT_ID", "U1234567")
    monkeypatch.setenv("IB_WRITE_ENABLED", "false")
    monkeypatch.setenv("IB_SSL_VERIFY", "false")


@pytest.fixture
def config() -> ProviderConfig:
    """Return a test ProviderConfig."""
    return ProviderConfig(
        gateway_url="https://localhost:5000",
        account_id="U1234567",
        ssl_verify=False,
    )


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Return a mock IBClient with common methods stubbed."""
    from ib_mcp.client import IBClient

    client = IBClient()
    client._session_valid = True
    client._account_id = "U1234567"
    return client


# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_accounts() -> list[dict[str, Any]]:
    return [
        {
            "accountId": "U1234567",
            "type": "INDIVIDUAL",
            "currency": "AUD",
            "accountTitle": "Test Account",
        }
    ]


@pytest.fixture
def sample_positions() -> list[dict[str, Any]]:
    return [
        {
            "conid": 265598,
            "contractDesc": "AAPL",
            "position": 100,
            "mktValue": 17500.0,
            "avgCost": 150.0,
            "mktPrice": 175.0,
            "unrealizedPnl": 2500.0,
        },
        {
            "conid": 9579970,
            "contractDesc": "BHP.ASX",
            "position": 500,
            "mktValue": 22500.0,
            "avgCost": 42.0,
            "mktPrice": 45.0,
            "unrealizedPnl": 1500.0,
        },
    ]


@pytest.fixture
def sample_orders() -> dict[str, Any]:
    return {
        "orders": [
            {
                "orderId": "1234",
                "ticker": "AAPL",
                "side": "BUY",
                "orderType": "LMT",
                "totalSize": 50,
                "price": 170.0,
                "filledQuantity": 0,
                "remainingQuantity": 50,
                "status": "Submitted",
            }
        ]
    }


@pytest.fixture
def sample_trades() -> list[dict[str, Any]]:
    return [
        {
            "execution_id": "0001",
            "symbol": "AAPL",
            "side": "BOT",
            "size": 100,
            "price": 175.50,
            "trade_time": "2026-04-09T10:30:00",
            "exchange": "SMART",
        }
    ]


@pytest.fixture
def sample_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "conid": 265598,
            "55": "AAPL",
            "31": "175.50",
            "83": "175.40",
            "84": "175.60",
            "85": "45230000",
            "82": "+1.2%",
        }
    ]
