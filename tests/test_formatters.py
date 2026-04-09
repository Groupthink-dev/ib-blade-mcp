"""Tests for ib_mcp.formatters — token-efficient output formatting."""

from __future__ import annotations

from typing import Any

from ib_mcp.formatters import (
    format_accounts,
    format_cancel_result,
    format_contract_info,
    format_contract_search,
    format_history,
    format_ledger,
    format_order_reply,
    format_order_status,
    format_orders,
    format_pnl,
    format_portfolio_summary,
    format_positions,
    format_snapshot,
    format_trades,
)

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


class TestFormatAccounts:
    def test_formats_accounts(self, sample_accounts: list[dict[str, Any]]) -> None:
        result = format_accounts(sample_accounts)
        assert "U1234567" in result
        assert "AUD" in result

    def test_empty_accounts(self) -> None:
        assert "No accounts" in format_accounts([])


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


class TestFormatPositions:
    def test_formats_positions(self, sample_positions: list[dict[str, Any]]) -> None:
        result = format_positions(sample_positions)
        assert "AAPL" in result
        assert "BHP.ASX" in result
        assert "265598" in result

    def test_empty_positions(self) -> None:
        assert "No positions" in format_positions([])


# ---------------------------------------------------------------------------
# Portfolio summary
# ---------------------------------------------------------------------------


class TestFormatPortfolioSummary:
    def test_formats_summary(self) -> None:
        data = {
            "netliquidation": {"amount": 150000.0},
            "totalcashvalue": {"amount": 25000.0},
            "unrealizedpnl": {"amount": 3500.0},
        }
        result = format_portfolio_summary(data)
        assert "netliquidation" in result
        assert "$" in result

    def test_empty_summary(self) -> None:
        assert "No summary" in format_portfolio_summary({})


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class TestFormatOrders:
    def test_formats_orders(self, sample_orders: dict[str, Any]) -> None:
        result = format_orders(sample_orders)
        assert "1234" in result
        assert "AAPL" in result
        assert "Submitted" in result

    def test_empty_orders(self) -> None:
        assert "No live orders" in format_orders({"orders": []})


# ---------------------------------------------------------------------------
# Order reply
# ---------------------------------------------------------------------------


class TestFormatOrderReply:
    def test_confirmation_prompt(self) -> None:
        data = [{"id": "abc123", "message": ["Are you sure?"]}]
        result = format_order_reply(data)
        assert "CONFIRM" in result
        assert "abc123" in result

    def test_placed_order(self) -> None:
        data = [{"order_id": "5678", "order_status": "Submitted"}]
        result = format_order_reply(data)
        assert "PLACED" in result
        assert "5678" in result

    def test_empty_reply(self) -> None:
        assert "No response" in format_order_reply([])


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


class TestFormatTrades:
    def test_formats_trades(self, sample_trades: list[dict[str, Any]]) -> None:
        result = format_trades(sample_trades)
        assert "AAPL" in result
        assert "175.50" in result
        assert "SMART" in result

    def test_empty_trades(self) -> None:
        assert "No recent trades" in format_trades([])


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


class TestFormatSnapshot:
    def test_formats_snapshot(self, sample_snapshot: list[dict[str, Any]]) -> None:
        result = format_snapshot(sample_snapshot)
        assert "265598" in result
        assert "AAPL" in result

    def test_empty_snapshot(self) -> None:
        assert "No snapshot" in format_snapshot([])


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class TestFormatHistory:
    def test_formats_history(self) -> None:
        data = {
            "symbol": "AAPL",
            "timePeriod": "1d",
            "barLength": "1h",
            "data": [
                {"t": 1712650800000, "o": 170.0, "h": 175.0, "l": 169.5, "c": 174.0, "v": 1500000},
            ],
        }
        result = format_history(data)
        assert "AAPL" in result
        assert "170.00" in result

    def test_empty_history(self) -> None:
        result = format_history({"data": [], "symbol": "AAPL", "timePeriod": "1d"})
        assert "No history" in result


# ---------------------------------------------------------------------------
# Contract search / info
# ---------------------------------------------------------------------------


class TestFormatContractSearch:
    def test_formats_search(self) -> None:
        data = [{"conid": 265598, "symbol": "AAPL", "companyName": "Apple Inc", "sections": []}]
        result = format_contract_search(data)
        assert "AAPL" in result
        assert "Apple" in result

    def test_empty_search(self) -> None:
        assert "No contracts" in format_contract_search([])


class TestFormatContractInfo:
    def test_formats_info(self) -> None:
        data = {"con_id": 265598, "symbol": "AAPL", "companyName": "Apple Inc", "currency": "USD"}
        result = format_contract_info(data)
        assert "AAPL" in result
        assert "USD" in result

    def test_empty_info(self) -> None:
        assert "No contract" in format_contract_info({})


# ---------------------------------------------------------------------------
# P&L
# ---------------------------------------------------------------------------


class TestFormatPnl:
    def test_formats_pnl(self) -> None:
        data = {"U1234567": {"dpl": 500.0, "upl": 3500.0, "nl": 150000.0, "mv": 125000.0}}
        result = format_pnl(data)
        assert "U1234567" in result
        assert "$500.00" in result

    def test_empty_pnl(self) -> None:
        assert "No P&L" in format_pnl({})


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


class TestFormatLedger:
    def test_formats_ledger(self) -> None:
        data = {"AUD": {"cashbalance": 25000.0, "settledcash": 25000.0, "interest": 10.0, "dividends": 150.0}}
        result = format_ledger(data)
        assert "AUD" in result
        assert "$25.0K" in result

    def test_empty_ledger(self) -> None:
        assert "No ledger" in format_ledger({})


# ---------------------------------------------------------------------------
# Cancel result
# ---------------------------------------------------------------------------


class TestFormatCancelResult:
    def test_formats_cancel(self) -> None:
        data = {"order_id": "1234", "msg": "Order cancelled"}
        result = format_cancel_result(data)
        assert "1234" in result
        assert "cancelled" in result

    def test_empty_cancel(self) -> None:
        assert "No cancel" in format_cancel_result({})


# ---------------------------------------------------------------------------
# Order status
# ---------------------------------------------------------------------------


class TestFormatOrderStatus:
    def test_formats_status(self) -> None:
        data = {"orderId": "1234", "symbol": "AAPL", "status": "Filled", "avgFillPrice": 175.0}
        result = format_order_status(data)
        assert "1234" in result
        assert "Filled" in result

    def test_empty_status(self) -> None:
        assert "No order" in format_order_status({})
