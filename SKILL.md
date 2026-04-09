---
name: ib-blade-mcp
description: Interactive Brokers operations — portfolio, market data, orders, scanners via Client Portal Gateway
version: "0.1.0"
permissions:
  read: [ib_status, ib_tickle, ib_accounts, ib_positions, ib_portfolio_summary, ib_cash_balances, ib_pnl, ib_contract_search, ib_contract_detail, ib_quote, ib_historical, ib_scanner_params, ib_scanner_run, ib_orders, ib_order_status, ib_trades]
  write: [ib_order_preview, ib_place_order, ib_confirm_order, ib_modify_order, ib_cancel_order]
---

# IB Blade MCP — Skill Guide

## Token Efficiency Rules (MANDATORY)

1. **Start with `ib_status`** — confirms gateway connection and write gate before other calls
2. **Use `ib_contract_search` before `ib_quote`** — you need conids for market data
3. **Call `ib_quote` twice for new conids** — first call subscribes, second returns full data
4. **Use `ib_order_preview` before `ib_place_order`** — always preview margin impact first
5. **Batch conids in `ib_quote`** — up to 50 conids per call, don't make individual calls
6. **Check `ib_positions` before trading** — know what you hold before placing orders
7. **Use appropriate historical periods** — don't request 5y of 1-minute bars

## Quick Start — 5 Most Common Operations

### 1. Check portfolio status
```
ib_status → ib_portfolio_summary → ib_positions
```

### 2. Get a stock quote
```
ib_contract_search(symbol="AAPL") → ib_quote(conids="265598") → ib_quote(conids="265598")
```
(Second call gets full data after subscription)

### 3. View P&L
```
ib_pnl → ib_positions
```

### 4. Preview an order (no execution)
```
ib_order_preview(conid=265598, side="BUY", quantity=100, order_type="LMT", price=170.0)
```

### 5. Place an order (requires write gate + confirm)
```
ib_order_preview(...) → ib_place_order(..., confirm=true)
```
If gateway returns CONFIRM prompt → `ib_confirm_order(reply_id=..., confirmed=true)`

## Tool Reference

### Read Tools (16)

| Tool | Purpose | Cost |
|------|---------|------|
| `ib_status` | Connection + auth check | Low |
| `ib_tickle` | Session keepalive | Low |
| `ib_accounts` | List accounts | Low |
| `ib_positions` | Open positions + P&L | Medium |
| `ib_portfolio_summary` | NAV, cash, margin | Low |
| `ib_cash_balances` | Cash by currency | Low |
| `ib_pnl` | Daily + unrealised P&L | Low |
| `ib_contract_search` | Find conid by symbol | Low |
| `ib_contract_detail` | Contract specs | Low |
| `ib_quote` | Live snapshot (batch) | Medium |
| `ib_historical` | OHLCV bars | High |
| `ib_scanner_params` | Scanner filter list | Medium |
| `ib_scanner_run` | Run scanner | High |
| `ib_orders` | Live orders | Low |
| `ib_order_status` | Single order detail | Low |
| `ib_trades` | Recent executions | Low |

### Write Tools (5) — Gated

| Tool | Gate | Purpose | Cost |
|------|------|---------|------|
| `ib_order_preview` | write | What-if preview | Medium |
| `ib_place_order` | write+confirm | Place order | High |
| `ib_confirm_order` | write | Reply to prompt | Low |
| `ib_modify_order` | write+confirm | Change order | High |
| `ib_cancel_order` | write | Cancel order | Low |

## Workflow Examples

### Morning portfolio check
```
ib_status
ib_portfolio_summary
ib_pnl
ib_positions
ib_orders  # check for any open orders from overnight
```

### Research a stock
```
ib_contract_search(symbol="BHP")        # find ASX listing
ib_contract_detail(conid=9579970)       # check exchange, currency
ib_quote(conids="9579970")              # subscribe
ib_quote(conids="9579970")              # full snapshot
ib_historical(conid=9579970, period="1m", bar="1d")  # monthly chart
```

### Place a limit buy (full safety flow)
```
ib_contract_search(symbol="AAPL")                    # get conid
ib_quote(conids="265598")                            # check current price
ib_order_preview(conid=265598, side="BUY",           # preview impact
                 quantity=100, order_type="LMT",
                 price=170.0)
ib_place_order(conid=265598, side="BUY",             # place order
               quantity=100, order_type="LMT",
               price=170.0, confirm=true)
# If CONFIRM prompt returned:
ib_confirm_order(reply_id="abc123", confirmed=true)
ib_order_status(order_id="5678")                     # verify
```

## IB-Specific Notes

- **Conids are the universal identifier.** Every market data and order tool uses contract IDs (conids). Use `ib_contract_search` to find them.
- **Market data subscription model.** The gateway subscribes to data on first request. The initial snapshot may be incomplete — a second call (after ~1 second) returns full data.
- **Order confirmation flow.** The gateway may return confirmation prompts (precautionary messages) that require `ib_confirm_order` to proceed. This is normal IB behaviour.
- **Self-signed certificates.** The CP Gateway uses a self-signed cert by default. Set `IB_SSL_VERIFY=false` for local development.
- **Session timeout.** Gateway sessions expire. Use `ib_tickle` periodically or `ib_status` to check.
