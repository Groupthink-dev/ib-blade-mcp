"""IB Blade MCP Server — portfolio, market data, orders, scanners.

Wraps the IB Client Portal Gateway REST API as MCP tools. Token-efficient by
default: compact pipe-delimited output, null-field omission, batch endpoints.
Write operations gated by IB_WRITE_ENABLED. Order placement requires explicit
confirm=true and returns a what-if preview first.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from ib_mcp.client import IBClient, IBError
from ib_mcp.formatters import (
    format_accounts,
    format_cancel_result,
    format_contract_info,
    format_contract_search,
    format_history,
    format_ledger,
    format_order_preview,
    format_order_reply,
    format_order_status,
    format_orders,
    format_pnl,
    format_portfolio_summary,
    format_positions,
    format_scanner_params,
    format_scanner_results,
    format_snapshot,
    format_status,
    format_trades,
)
from ib_mcp.models import (
    check_confirm_gate,
    check_write_gate,
    is_write_enabled,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------

TRANSPORT = os.environ.get("IB_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("IB_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("IB_MCP_PORT", "8790"))

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "IBBlade",
    instructions=(
        "Interactive Brokers operations via Client Portal Gateway: "
        "portfolio, positions, market data, orders, scanners, trades. "
        "Gateway must be running and authenticated. "
        "Write operations require IB_WRITE_ENABLED=true. "
        "Order placement requires confirm=true (real money)."
    ),
)

# Lazy-initialized client
_client: IBClient | None = None


def _get_client() -> IBClient:
    """Get or create the IBClient singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = IBClient()
    return _client


def _error(e: IBError) -> str:
    """Format a client error as a user-friendly string."""
    msg = f"Error: {e}"
    if e.details:
        msg += f" ({e.details})"
    return msg


# ===========================================================================
# SYSTEM TOOLS (2)
# ===========================================================================


# ---------------------------------------------------------------------------
# 1. ib_status
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_status() -> str:
    """Session status: auth state, account, write gate, rate limits, gateway version."""
    try:
        client = _get_client()
        auth = await client.check_auth()
        return format_status(
            authenticated=auth.get("authenticated", False),
            account_id=client.account_id,
            write_enabled=is_write_enabled(),
            rate_status=client.get_rate_status(),
            server_info=auth,
        )
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 2. ib_tickle
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_tickle() -> str:
    """Keep the gateway session alive (heartbeat). Call periodically to prevent timeout."""
    try:
        data = await _get_client().tickle()
        session_id = data.get("session", "?")
        return f"session={session_id} | tickled"
    except IBError as e:
        return _error(e)


# ===========================================================================
# PORTFOLIO TOOLS (5)
# ===========================================================================


# ---------------------------------------------------------------------------
# 3. ib_accounts
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_accounts() -> str:
    """List all brokerage accounts linked to this gateway session."""
    try:
        data = await _get_client().list_accounts()
        return format_accounts(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 4. ib_positions
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_positions(
    page: Annotated[int, Field(description="Page number (0-based, each page ~30 positions)")] = 0,
) -> str:
    """List open positions with P&L, market value, and cost basis."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_positions(page_id=page)
        return format_positions(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 5. ib_portfolio_summary
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_portfolio_summary() -> str:
    """Portfolio summary: NAV, cash, unrealised P&L, buying power, margin."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_portfolio_summary()
        return format_portfolio_summary(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 6. ib_cash_balances
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_cash_balances() -> str:
    """Cash balances by currency (settled, interest, dividends)."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_ledger()
        return format_ledger(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 7. ib_pnl
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_pnl() -> str:
    """Account-level P&L: daily, unrealised, NAV, market value."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_account_pnl()
        return format_pnl(data)
    except IBError as e:
        return _error(e)


# ===========================================================================
# MARKET DATA TOOLS (5)
# ===========================================================================


# ---------------------------------------------------------------------------
# 8. ib_contract_search
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_contract_search(
    symbol: Annotated[str, Field(description="Symbol or company name to search for")],
    sec_type: Annotated[
        str | None,
        Field(description="Security type filter: STK, OPT, FUT, CFD, WAR, FOP, etc."),
    ] = None,
) -> str:
    """Search for contracts by symbol or name. Returns conids needed for other tools."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().search_contracts(symbol=symbol, sec_type=sec_type)
        return format_contract_search(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 9. ib_contract_detail
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_contract_detail(
    conid: Annotated[int, Field(description="Contract ID (from ib_contract_search)")],
) -> str:
    """Get contract details: exchange, currency, type, multiplier, tick size."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_contract_info(conid)
        return format_contract_info(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 10. ib_quote
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_quote(
    conids: Annotated[str, Field(description="Comma-separated contract IDs (max 50)")],
) -> str:
    """Live market data snapshot: last, bid, ask, volume, change. First call subscribes — call twice for full data."""
    try:
        await _get_client()._ensure_session()
        id_list = [int(c.strip()) for c in conids.split(",") if c.strip()]
        data = await _get_client().get_snapshot(id_list)
        return format_snapshot(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 11. ib_historical
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_historical(
    conid: Annotated[int, Field(description="Contract ID")],
    period: Annotated[str, Field(description="Time period: 1d, 1w, 1m, 3m, 6m, 1y, 5y")] = "1d",
    bar: Annotated[str, Field(description="Bar size: 1min, 5min, 15min, 30min, 1h, 4h, 1d, 1w, 1m")] = "1h",
    outside_rth: Annotated[bool, Field(description="Include outside regular trading hours")] = False,
) -> str:
    """Historical OHLCV bars for charting and analysis."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_history(conid=conid, period=period, bar=bar, outside_rth=outside_rth)
        return format_history(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 12. ib_scanner_params
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_scanner_params() -> str:
    """List available market scanner types, instruments, and filters."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_scanner_params()
        return format_scanner_params(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 13. ib_scanner_run
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_scanner_run(
    scan_type: Annotated[str, Field(description="Scanner type code (from ib_scanner_params)")],
    instrument: Annotated[str, Field(description="Instrument type (e.g. 'STK', 'FUT.US')")] = "STK",
    location: Annotated[str, Field(description="Market location (e.g. 'STK.US.MAJOR', 'STK.AU')")] = "STK.US.MAJOR",
    max_results: Annotated[int, Field(description="Max results (1-50)")] = 25,
) -> str:
    """Run a market scanner (top gainers, most active, new highs, etc.)."""
    try:
        await _get_client()._ensure_session()
        params = {
            "instrument": instrument,
            "type": scan_type,
            "location": location,
            "filter": [],
        }
        data = await _get_client().run_scanner(params)
        return format_scanner_results(data[:max_results])
    except IBError as e:
        return _error(e)


# ===========================================================================
# ORDER QUERY TOOLS (3)
# ===========================================================================


# ---------------------------------------------------------------------------
# 14. ib_orders
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_orders(
    status_filter: Annotated[
        str | None,
        Field(description="Comma-separated status filters: Submitted, Filled, Cancelled, Inactive"),
    ] = None,
) -> str:
    """List live/recent orders with status, fills, and remaining quantity."""
    try:
        await _get_client()._ensure_session()
        filters = [f.strip() for f in status_filter.split(",")] if status_filter else None
        data = await _get_client().list_orders(filters=filters)
        return format_orders(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 15. ib_order_status
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_order_status(
    order_id: Annotated[str, Field(description="Order ID to query")],
) -> str:
    """Get detailed status of a specific order including fill info."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_order_status(order_id)
        return format_order_status(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 16. ib_trades
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_trades() -> str:
    """List recent trade executions (fills) with price, time, and exchange."""
    try:
        await _get_client()._ensure_session()
        data = await _get_client().get_trades()
        return format_trades(data)
    except IBError as e:
        return _error(e)


# ===========================================================================
# WRITE TOOLS (5 gated) — require IB_WRITE_ENABLED=true
# ===========================================================================


# ---------------------------------------------------------------------------
# 17. ib_order_preview [write gate]
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_order_preview(
    conid: Annotated[int, Field(description="Contract ID")],
    side: Annotated[str, Field(description="BUY or SELL")],
    quantity: Annotated[float, Field(description="Order quantity")],
    order_type: Annotated[str, Field(description="MKT, LMT, STP, STP_LMT, MIDPRICE")] = "LMT",
    price: Annotated[float | None, Field(description="Limit price (required for LMT/STP_LMT)")] = None,
    tif: Annotated[str, Field(description="Time-in-force: DAY, GTC, IOC, OPG")] = "DAY",
) -> str:
    """Preview order impact: margin, commission, equity change. Does NOT place. Requires IB_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        client = _get_client()
        await client._ensure_session()
        account_id = await client._ensure_account()
        order: dict = {
            "conid": conid,
            "side": side.upper(),
            "orderType": order_type.upper(),
            "quantity": quantity,
            "tif": tif.upper(),
        }
        if price is not None:
            order["price"] = price
        data = await client.preview_order(account_id, [order])
        return format_order_preview(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 18. ib_place_order [write gate + confirm gate]
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_place_order(
    conid: Annotated[int, Field(description="Contract ID")],
    side: Annotated[str, Field(description="BUY or SELL")],
    quantity: Annotated[float, Field(description="Order quantity")],
    order_type: Annotated[str, Field(description="MKT, LMT, STP, STP_LMT, MIDPRICE")] = "LMT",
    price: Annotated[float | None, Field(description="Limit price (required for LMT/STP_LMT)")] = None,
    tif: Annotated[str, Field(description="Time-in-force: DAY, GTC, IOC, OPG")] = "DAY",
    confirm: Annotated[bool, Field(description="Must be true — this places a REAL MONEY order")] = False,
) -> str:
    """Place an order. REAL MONEY. Requires IB_WRITE_ENABLED=true AND confirm=true.

    If the gateway returns a confirmation prompt, use ib_confirm_order with the reply_id.
    Run ib_order_preview first to check margin impact.
    """
    gate = check_write_gate()
    if gate:
        return gate
    conf = check_confirm_gate(confirm, "Place order")
    if conf:
        return conf
    try:
        client = _get_client()
        await client._ensure_session()
        account_id = await client._ensure_account()
        order: dict = {
            "conid": conid,
            "side": side.upper(),
            "orderType": order_type.upper(),
            "quantity": quantity,
            "tif": tif.upper(),
        }
        if price is not None:
            order["price"] = price
        data = await client.place_order(account_id, [order])
        return format_order_reply(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 19. ib_confirm_order [write gate]
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_confirm_order(
    reply_id: Annotated[str, Field(description="Reply ID from ib_place_order confirmation prompt")],
    confirmed: Annotated[bool, Field(description="true to confirm, false to reject")] = True,
) -> str:
    """Reply to an order confirmation prompt from the gateway. Requires IB_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        client = _get_client()
        data = await client.reply_to_order(reply_id, confirmed)
        return format_order_reply(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 20. ib_modify_order [write gate + confirm gate]
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_modify_order(
    order_id: Annotated[str, Field(description="Order ID to modify")],
    quantity: Annotated[float | None, Field(description="New quantity (omit to keep)")] = None,
    price: Annotated[float | None, Field(description="New limit price (omit to keep)")] = None,
    tif: Annotated[str | None, Field(description="New time-in-force (omit to keep)")] = None,
    confirm: Annotated[bool, Field(description="Must be true — modifies a real order")] = False,
) -> str:
    """Modify an existing order. Requires IB_WRITE_ENABLED=true AND confirm=true."""
    gate = check_write_gate()
    if gate:
        return gate
    conf = check_confirm_gate(confirm, "Modify order")
    if conf:
        return conf
    try:
        client = _get_client()
        await client._ensure_session()
        account_id = await client._ensure_account()
        order: dict = {}
        if quantity is not None:
            order["quantity"] = quantity
        if price is not None:
            order["price"] = price
        if tif is not None:
            order["tif"] = tif.upper()
        if not order:
            return "Error: No fields to modify. Specify quantity, price, or tif."
        data = await client.modify_order(account_id, order_id, order)
        return format_order_reply(data)
    except IBError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 21. ib_cancel_order [write gate]
# ---------------------------------------------------------------------------


@mcp.tool()
async def ib_cancel_order(
    order_id: Annotated[str, Field(description="Order ID to cancel")],
) -> str:
    """Cancel an open order. Requires IB_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        client = _get_client()
        await client._ensure_session()
        account_id = await client._ensure_account()
        data = await client.cancel_order(account_id, order_id)
        return format_cancel_result(data)
    except IBError as e:
        return _error(e)


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:
    """Run the MCP server."""
    if TRANSPORT == "http":
        from starlette.middleware import Middleware

        from ib_mcp.auth import BearerAuthMiddleware

        mcp.run(
            transport="streamable-http",
            host=HTTP_HOST,
            port=HTTP_PORT,
            middleware=[Middleware(BearerAuthMiddleware)],
        )
    else:
        mcp.run(transport="stdio")
