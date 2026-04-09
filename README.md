# IB Blade MCP

Interactive Brokers MCP server for Claude, Sidereal, and any MCP-compatible client. Portfolio monitoring, market data, order management, and market scanners — all through the IB Client Portal Gateway.

Built for the [Model Context Protocol](https://modelcontextprotocol.io).

## Why another IB MCP?

| | **ib-blade-mcp** | rcontesti/IB_MCP | code-rabi/interactive-brokers-mcp | Hellek1/ib-mcp |
|---|---|---|---|---|
| **Approach** | CP Gateway REST | CP Gateway REST | Bundled Gateway + JRE | TWS socket (ib_async) |
| **Headless** | Yes (gateway runs separately) | Yes | Bundles JRE + Gateway in npm | Requires running TWS/Gateway |
| **Order safety** | Triple gate: env var + confirm param + what-if preview | Basic | Basic confirm | Read-only by design |
| **Token efficiency** | Pipe-delimited, compact formatters, batch endpoints | JSON dumps | JSON dumps | JSON dumps |
| **Credential handling** | Gateway handles auth; MCP never sees IB passwords. Scrubbing on errors | Env var passwords | OAuth or env var passwords | Env var passwords |
| **Rate limiting** | Concurrency semaphore + snapshot throttle | None | None | None |
| **HTTP transport** | stdio + streamable-http with bearer auth | stdio only | stdio only | stdio only |
| **Security posture** | No bundled JRE, no IB credentials in MCP process, bearer auth for remote | Passwords in env | Ships a JRE | Passwords in env |
| **IB Australia** | Works with any IB entity (AU, US, UK, etc.) | Global only | Global only | Global only |
| **Tests** | pytest + mypy + ruff CI | Minimal | Minimal | Good (pytest) |

### Key design decisions

1. **Gateway separation.** This MCP server connects to an already-authenticated Client Portal Gateway. Your IB credentials never touch the MCP process. The gateway handles authentication, session management, and market data subscriptions.

2. **Triple order safety.** Three independent gates prevent accidental trades:
   - `IB_WRITE_ENABLED=true` environment variable (off by default)
   - `confirm=true` parameter on every order tool (off by default)
   - `ib_order_preview` returns margin impact and commission before you commit

3. **Token efficiency.** Every tool returns compact pipe-delimited output, not raw JSON. Positions, orders, and trades each fit in a few hundred tokens instead of thousands.

4. **No bundled infrastructure.** Unlike alternatives that bundle JRE and gateway binaries inside npm packages, this server is a lightweight Python process that talks to your existing gateway.

## What this covers

- **21 tools** across 6 categories
- Portfolio: accounts, positions, summary, cash balances, P&L
- Market data: contract search, quotes, batch snapshots, historical bars
- Orders: list, status, preview, place, modify, cancel, confirm
- Scanners: parameter discovery, scanner execution
- Trades: recent executions

## Quick start

### Prerequisites

1. **IB Client Portal Gateway** — download from [IB API page](https://www.interactivebrokers.com/en/trading/ib-api.php) and run it:
   ```bash
   cd clientportal-gw && bin/run.sh root/conf.yaml
   ```
2. Authenticate by opening `https://localhost:5000` in a browser
3. Python 3.12+

### Install

```bash
# From PyPI (when published)
uv pip install ib-blade-mcp

# From source
git clone https://github.com/groupthink-dev/ib-blade-mcp
cd ib-blade-mcp && uv sync
```

### Configure

```bash
# Required
export IB_GATEWAY_URL="https://localhost:5000"

# Optional
export IB_ACCOUNT_ID="U1234567"       # Auto-detected if omitted
export IB_SSL_VERIFY="false"           # For self-signed gateway certs
export IB_WRITE_ENABLED="false"        # Enable order placement
export IB_MCP_API_TOKEN=""             # Bearer token for HTTP transport
```

### Run

```bash
# stdio transport (default — for Claude Code, Sidereal, etc.)
ib-blade-mcp

# HTTP transport (for remote/tunnel access)
IB_MCP_TRANSPORT=http IB_MCP_PORT=8790 ib-blade-mcp
```

### Claude Code configuration

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "ib": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ib-blade-mcp", "ib-blade-mcp"],
      "env": {
        "IB_GATEWAY_URL": "https://localhost:5000",
        "IB_SSL_VERIFY": "false",
        "IB_WRITE_ENABLED": "false"
      }
    }
  }
}
```

## Tools

### System (2)

| Tool | Description |
|------|-------------|
| `ib_status` | Session status, auth state, write gate, rate limits |
| `ib_tickle` | Keep gateway session alive (heartbeat) |

### Portfolio (5)

| Tool | Description |
|------|-------------|
| `ib_accounts` | List linked brokerage accounts |
| `ib_positions` | Open positions with P&L, market value, cost basis |
| `ib_portfolio_summary` | NAV, cash, unrealised P&L, buying power, margin |
| `ib_cash_balances` | Cash balances by currency |
| `ib_pnl` | Daily and unrealised P&L |

### Market Data (6)

| Tool | Description |
|------|-------------|
| `ib_contract_search` | Find contracts by symbol or name → conid |
| `ib_contract_detail` | Contract info: exchange, currency, multiplier |
| `ib_quote` | Live snapshot: last, bid, ask, volume, change |
| `ib_historical` | Historical OHLCV bars |
| `ib_scanner_params` | Available scanner types and filters |
| `ib_scanner_run` | Run market scanner (gainers, most active, etc.) |

### Order Query (3)

| Tool | Description |
|------|-------------|
| `ib_orders` | Live/recent orders with fill status |
| `ib_order_status` | Detailed status of a specific order |
| `ib_trades` | Recent trade executions |

### Order Write (5) — gated

| Tool | Gate | Description |
|------|------|-------------|
| `ib_order_preview` | write | What-if preview: margin, commission, equity impact |
| `ib_place_order` | write + confirm | Place order (LMT, MKT, STP, STP_LMT, MIDPRICE) |
| `ib_confirm_order` | write | Reply to gateway confirmation prompts |
| `ib_modify_order` | write + confirm | Modify quantity, price, or TIF |
| `ib_cancel_order` | write | Cancel an open order |

## Output format

All tools return compact pipe-delimited text optimised for LLM token efficiency:

```
conid | symbol | pos | mkt_value | avg_cost | unrealised_pnl | pnl%
265598 | AAPL | 100 | $17.5K | 150.00 | $2500.00 | +16.7%
9579970 | BHP.ASX | 500 | $22.5K | 42.00 | $1500.00 | +7.1%
```

Money values use compact formatting: `$1.2M`, `$45.3K`, `$500.00`.

## Security model

- **Gateway isolation.** IB credentials are managed by the Client Portal Gateway, not this MCP server. The MCP process never sees your IB username or password.
- **Write gating.** All order operations require `IB_WRITE_ENABLED=true`. Order placement additionally requires `confirm=true` per call.
- **Credential scrubbing.** Session tokens, cookies, and auth headers are stripped from error messages before returning to the LLM.
- **Bearer auth.** HTTP transport optionally requires `Authorization: Bearer <token>` with timing-safe comparison.
- **No bundled binaries.** Unlike some alternatives, this server doesn't ship JRE, gateway, or other large dependencies.

## IB Australia

This server works with any Interactive Brokers entity. IB Australia (ABN 98 166 929 568, AFSL 453554) accounts use the same Client Portal Gateway as any other region. The account ID determines jurisdiction — no code-level configuration needed.

AUD base currency is handled natively in formatters.

## Architecture

```
┌──────────────┐     stdio/HTTP      ┌──────────────┐    REST/JSON    ┌──────────────┐
│  MCP Client  │ ◄──────────────────► │ ib-blade-mcp │ ◄────────────► │  IB Gateway   │
│ (Claude, etc)│                      │  (FastMCP)   │                │ (CP Gateway)  │
└──────────────┘                      └──────────────┘                └──────┬───────┘
                                                                             │
                                                                    IB Auth + Market Data
                                                                             │
                                                                      ┌──────▼───────┐
                                                                      │   IB Servers  │
                                                                      └──────────────┘
```

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IB_GATEWAY_URL` | Yes | — | Client Portal Gateway URL |
| `IB_ACCOUNT_ID` | No | auto-detect | Default account ID |
| `IB_SSL_VERIFY` | No | `true` | Verify SSL certs (set `false` for self-signed) |
| `IB_WRITE_ENABLED` | No | `false` | Enable order operations |
| `IB_MCP_TRANSPORT` | No | `stdio` | Transport: `stdio` or `http` |
| `IB_MCP_HOST` | No | `127.0.0.1` | HTTP bind address |
| `IB_MCP_PORT` | No | `8790` | HTTP port |
| `IB_MCP_API_TOKEN` | No | — | Bearer token for HTTP transport |

## Development

```bash
make install-dev    # Install with dev + test deps
make test           # Run unit tests
make test-cov       # Run with coverage
make check          # Lint + format + typecheck
make run            # Start the server
```

## Roadmap

- [ ] **WebSocket order streaming** — subscribe to order status changes via gateway WebSocket for real-time fill notifications
- [ ] **OAuth 2.0 Web API** — direct IB Web API access with `private_key_jwt`, eliminating the gateway dependency
- [ ] **Flex Queries** — historical trade reports and statements via IB Flex Query system
- [ ] **Watchlist management** — create and manage watchlists through the gateway
- [ ] **Sidereal marketplace** — publish as a certified Sidereal pack

## License

MIT
