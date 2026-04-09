"""Token-efficient output formatters for IB Blade MCP server.

All formatters return compact strings optimised for LLM consumption:
- One line per position/order/trade
- Pipe-delimited fields
- Null-field omission
- Compact money formatting ($1.2M, $3.5K)
- Percentages to 1dp
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _ts(iso: str | None) -> str:
    """Extract compact timestamp from ISO 8601."""
    if not iso:
        return "?"
    if "T" in iso:
        date_part = iso.split("T")[0]
        time_part = iso.split("T")[1][:5]
        return f"{date_part} {time_part}"
    return iso


def _usd(val: float | int | None) -> str:
    """Compact currency formatting."""
    if val is None:
        return "-"
    v = float(val)
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:+.2f}M" if v < 0 else f"${v / 1_000_000:.2f}M"
    if abs(v) >= 10_000:
        return f"${v / 1_000:+.1f}K" if v < 0 else f"${v / 1_000:.1f}K"
    return f"${v:+.2f}" if v < 0 else f"${v:.2f}"


def _price(val: float | int | None) -> str:
    """Format price."""
    if val is None:
        return "-"
    return f"{float(val):.2f}"


def _pct(val: float | int | None) -> str:
    """Format percentage."""
    if val is None:
        return "-"
    return f"{float(val):+.1f}%"


def _qty(val: float | int | None) -> str:
    """Format quantity."""
    if val is None:
        return "-"
    v = float(val)
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def format_status(
    authenticated: bool,
    account_id: str | None,
    write_enabled: bool,
    rate_status: str,
    server_info: dict[str, Any] | None = None,
) -> str:
    """Format session status summary."""
    parts = [
        f"authenticated={'yes' if authenticated else 'no'}",
        f"account={account_id or 'auto-detect'}",
        f"write_enabled={'yes' if write_enabled else 'no'}",
        rate_status,
    ]
    if server_info:
        if "serverVersion" in server_info:
            parts.append(f"server={server_info['serverVersion']}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def format_accounts(data: list[dict[str, Any]]) -> str:
    """Format portfolio/accounts response."""
    if not data:
        return "No accounts found"
    lines = ["account_id | type | currency | name"]
    for acct in data:
        lines.append(
            f"{acct.get('accountId', '?')} | {acct.get('type', '-')} | "
            f"{acct.get('currency', '-')} | {acct.get('accountTitle', '-')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


def format_positions(data: list[dict[str, Any]]) -> str:
    """Format positions response.

    Output: conid | symbol | pos | mkt_value | avg_cost | pnl | pnl_pct
    """
    if not data:
        return "No positions"
    lines = ["conid | symbol | pos | mkt_value | avg_cost | unrealised_pnl | pnl%"]
    for p in data:
        pnl_pct = None
        mkt_val = p.get("mktValue")
        avg_cost = p.get("avgCost")
        mkt_price = p.get("mktPrice")
        if avg_cost and mkt_price and avg_cost != 0:
            pnl_pct = ((float(mkt_price) - float(avg_cost)) / float(avg_cost)) * 100

        lines.append(
            f"{p.get('conid', '?')} | {p.get('contractDesc', p.get('ticker', '?'))} | "
            f"{_qty(p.get('position'))} | {_usd(mkt_val)} | "
            f"{_price(avg_cost)} | {_usd(p.get('unrealizedPnl'))} | "
            f"{_pct(pnl_pct)}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Portfolio summary
# ---------------------------------------------------------------------------


def format_portfolio_summary(data: dict[str, Any]) -> str:
    """Format portfolio summary response."""
    if not data:
        return "No summary data"
    parts: list[str] = []
    for key in [
        "netliquidation", "totalcashvalue", "unrealizedpnl",
        "realizedpnl", "grosspositionvalue", "availablefunds",
        "buyingpower", "maintmarginreq",
    ]:
        entry = data.get(key, {})
        if isinstance(entry, dict):
            val = entry.get("amount")
            if val is not None:
                parts.append(f"{key}={_usd(val)}")
    return " | ".join(parts) if parts else "No summary fields available"


# ---------------------------------------------------------------------------
# Cash balances (ledger)
# ---------------------------------------------------------------------------


def format_ledger(data: dict[str, Any]) -> str:
    """Format account ledger (cash balances by currency)."""
    if not data:
        return "No ledger data"
    lines = ["currency | cash | settled | interest | dividends"]
    for ccy, vals in data.items():
        if not isinstance(vals, dict):
            continue
        lines.append(
            f"{ccy} | {_usd(vals.get('cashbalance'))} | "
            f"{_usd(vals.get('settledcash'))} | {_usd(vals.get('interest'))} | "
            f"{_usd(vals.get('dividends'))}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# P&L
# ---------------------------------------------------------------------------


def format_pnl(data: dict[str, Any]) -> str:
    """Format account P&L response."""
    if not data:
        return "No P&L data"
    # The response nests P&L under account IDs
    parts: list[str] = []
    for acct_id, acct_data in data.items():
        if not isinstance(acct_data, dict):
            continue
        dpl = acct_data.get("dpl")
        upl = acct_data.get("upl")
        nl = acct_data.get("nl")
        mv = acct_data.get("mv")
        parts.append(
            f"{acct_id}: daily_pnl={_usd(dpl)} | unrealised={_usd(upl)} | "
            f"nav={_usd(nl)} | mkt_value={_usd(mv)}"
        )
    return "\n".join(parts) if parts else "No P&L entries"


# ---------------------------------------------------------------------------
# Contract search
# ---------------------------------------------------------------------------


def format_contract_search(data: list[dict[str, Any]]) -> str:
    """Format contract search results."""
    if not data:
        return "No contracts found"
    lines = ["conid | symbol | description | exchange | sec_type"]
    for c in data:
        # Search results may have nested sections
        conid = c.get("conid", "?")
        sections = c.get("sections", [])
        if sections:
            # Multi-section result (stock with options, etc.)
            for sec in sections:
                lines.append(
                    f"{conid} | {c.get('symbol', '?')} | "
                    f"{c.get('companyName', c.get('description', '-'))} | "
                    f"{sec.get('exchange', '-')} | {sec.get('secType', '-')}"
                )
        else:
            lines.append(
                f"{conid} | {c.get('symbol', '?')} | "
                f"{c.get('companyName', c.get('description', '-'))} | "
                f"{c.get('exchange', '-')} | {c.get('secType', '-')}"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Contract detail
# ---------------------------------------------------------------------------


def format_contract_info(data: dict[str, Any]) -> str:
    """Format contract info response."""
    if not data:
        return "No contract info"
    parts: list[str] = []
    for key in [
        "con_id", "symbol", "companyName", "exchange", "listingExchange",
        "secType", "currency", "category", "industry",
        "maturity_date", "multiplier", "min_tick",
    ]:
        val = data.get(key)
        if val is not None:
            parts.append(f"{key}={val}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Market data snapshot
# ---------------------------------------------------------------------------

# IB field ID to name mapping (common fields)
SNAPSHOT_FIELDS: dict[str, str] = {
    "31": "last",
    "55": "symbol",
    "58": "text",
    "70": "high",
    "71": "low",
    "73": "mkt_value",
    "74": "avg_price",
    "75": "unrealised_pnl",
    "76": "formatted_pos",
    "77": "formatted_val",
    "78": "unrealised_pnl_pct",
    "79": "change",
    "80": "junk",
    "82": "change_pct",
    "83": "bid",
    "84": "ask",
    "85": "volume",
    "86": "bid_size",
    "87": "ask_size",
    "88": "open",
    "6119": "close",
    "6509": "div_yield",
    "7219": "conid",
    "7220": "conidEx",
    "7221": "ticker",
    "7282": "pe_ratio",
    "7283": "eps",
    "7284": "mkt_cap",
    "7636": "52w_high",
    "7637": "52w_low",
}


def format_snapshot(data: list[dict[str, Any]]) -> str:
    """Format market data snapshot response."""
    if not data:
        return "No snapshot data"
    lines: list[str] = []
    for item in data:
        conid = item.get("conid", item.get("conidEx", "?"))
        parts = [f"conid={conid}"]
        for field_id, label in SNAPSHOT_FIELDS.items():
            val = item.get(field_id)
            if val is not None and label != "junk":
                parts.append(f"{label}={val}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Historical data
# ---------------------------------------------------------------------------


def format_history(data: dict[str, Any]) -> str:
    """Format historical market data bars.

    Output: time | open | high | low | close | volume
    """
    bars = data.get("data", [])
    if not bars:
        return f"No history data (symbol={data.get('symbol', '?')}, period={data.get('timePeriod', '?')})"
    symbol = data.get("symbol", "?")
    lines = [f"# {symbol} — {data.get('timePeriod', '?')} / {data.get('barLength', '?')}"]
    lines.append("time | open | high | low | close | volume")
    for bar in bars:
        t = bar.get("t", "?")
        # t is usually epoch millis
        if isinstance(t, (int, float)):
            import datetime

            t = datetime.datetime.fromtimestamp(t / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"{t} | {_price(bar.get('o'))} | {_price(bar.get('h'))} | "
            f"{_price(bar.get('l'))} | {_price(bar.get('c'))} | {_qty(bar.get('v'))}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def format_orders(data: dict[str, Any]) -> str:
    """Format live orders response.

    Output: order_id | symbol | side | type | qty | price | filled | status
    """
    orders = data.get("orders", [])
    if not orders:
        return "No live orders"
    lines = ["order_id | symbol | side | type | qty | price | filled | remaining | status"]
    for o in orders:
        lines.append(
            f"{o.get('orderId', '?')} | {o.get('ticker', o.get('symbol', '?'))} | "
            f"{o.get('side', '?')} | {o.get('orderType', '?')} | "
            f"{_qty(o.get('totalSize', o.get('quantity')))} | {_price(o.get('price'))} | "
            f"{_qty(o.get('filledQuantity'))} | {_qty(o.get('remainingQuantity'))} | "
            f"{o.get('status', '?')}"
        )
    return "\n".join(lines)


def format_order_status(data: dict[str, Any]) -> str:
    """Format single order status."""
    if not data:
        return "No order data"
    parts = []
    for key in [
        "orderId", "symbol", "side", "orderType", "price",
        "totalSize", "filledQuantity", "remainingQuantity",
        "status", "lastFillPrice", "avgFillPrice",
    ]:
        val = data.get(key)
        if val is not None:
            parts.append(f"{key}={val}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Order results
# ---------------------------------------------------------------------------


def format_order_reply(data: list[dict[str, Any]]) -> str:
    """Format order placement/modification response.

    IB may return confirmation prompts (with 'id' and 'message') or
    final results (with 'order_id' and 'order_status').
    """
    if not data:
        return "No response"
    lines: list[str] = []
    for item in data:
        if "id" in item and "message" in item:
            # Confirmation prompt
            msgs = item.get("message", [])
            if isinstance(msgs, list):
                msg_text = " | ".join(str(m) for m in msgs)
            else:
                msg_text = str(msgs)
            lines.append(f"CONFIRM reply_id={item['id']}: {msg_text}")
        elif "order_id" in item:
            lines.append(
                f"PLACED order_id={item['order_id']} | "
                f"status={item.get('order_status', '?')} | "
                f"message={item.get('text', '-')}"
            )
        else:
            # Unknown format — dump key fields
            parts = [f"{k}={v}" for k, v in item.items() if v is not None]
            lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_cancel_result(data: dict[str, Any]) -> str:
    """Format order cancellation result."""
    if not data:
        return "No cancel response"
    order_id = data.get("order_id", data.get("orderId", "?"))
    msg = data.get("msg", data.get("message", data.get("text", "cancelled")))
    return f"order_id={order_id} | {msg}"


# ---------------------------------------------------------------------------
# Order preview (whatif)
# ---------------------------------------------------------------------------


def format_order_preview(data: dict[str, Any]) -> str:
    """Format order what-if preview."""
    if not data:
        return "No preview data"
    parts: list[str] = ["ORDER PREVIEW"]
    # Amount section
    amount = data.get("amount", {})
    if amount:
        parts.append(f"equity={_usd(amount.get('equity'))}")
        parts.append(f"position={_usd(amount.get('position'))}")
        parts.append(f"commission={_usd(amount.get('commission'))}")
        parts.append(f"total={_usd(amount.get('total'))}")
    # Equity section
    equity = data.get("equity", {})
    if equity:
        parts.append(f"current_equity={_usd(equity.get('current'))}")
        parts.append(f"after_equity={_usd(equity.get('after'))}")
    # Warnings
    warns = data.get("warn", "")
    if warns:
        parts.append(f"WARNINGS: {warns}")
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


def format_trades(data: list[dict[str, Any]]) -> str:
    """Format recent trades/executions.

    Output: exec_id | symbol | side | qty | price | time | exchange
    """
    if not data:
        return "No recent trades"
    lines = ["exec_id | symbol | side | qty | price | time | exchange"]
    for t in data:
        lines.append(
            f"{t.get('execution_id', '?')} | {t.get('symbol', '?')} | "
            f"{t.get('side', '?')} | {_qty(t.get('size'))} | "
            f"{_price(t.get('price'))} | {_ts(t.get('trade_time'))} | "
            f"{t.get('exchange', '-')}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def format_scanner_params(data: dict[str, Any]) -> str:
    """Format scanner parameters (compact summary)."""
    if not data:
        return "No scanner params"
    parts: list[str] = []
    scan_types = data.get("scan_type_list", [])
    if scan_types:
        parts.append(f"scan_types ({len(scan_types)}):")
        for st in scan_types[:20]:
            code = st.get("code", "?")
            name = st.get("display_name", st.get("name", "?"))
            parts.append(f"  {code}: {name}")
        if len(scan_types) > 20:
            parts.append(f"  ... and {len(scan_types) - 20} more")
    instruments = data.get("instrument_list", [])
    if instruments:
        parts.append(f"\ninstruments ({len(instruments)}):")
        for inst in instruments[:10]:
            parts.append(f"  {inst.get('type', '?')}: {inst.get('display_name', '?')}")
    filters = data.get("filter_list", [])
    if filters:
        parts.append(f"\nfilters ({len(filters)}):")
        for f in filters[:10]:
            parts.append(f"  {f.get('code', '?')}: {f.get('display_name', '?')}")
    return "\n".join(parts) if parts else "Scanner params empty"


def format_scanner_results(data: list[dict[str, Any]]) -> str:
    """Format scanner run results."""
    if not data:
        return "No scanner results"
    lines = ["conid | symbol | last | change | volume"]
    for r in data:
        lines.append(
            f"{r.get('conid', r.get('con_id', '?'))} | {r.get('symbol', '?')} | "
            f"{_price(r.get('last_price', r.get('last')))} | "
            f"{_pct(r.get('change_pct', r.get('change')))} | "
            f"{_qty(r.get('volume'))}"
        )
    return "\n".join(lines)
