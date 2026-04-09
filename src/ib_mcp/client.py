"""IB Client Portal Gateway API client.

Wraps the CP Gateway REST API with session management, rate limiting,
credential scrubbing, typed exceptions, and automatic re-authentication.

The gateway must be running and authenticated (via browser or headless init)
before this client can operate. This client does NOT handle IB login — it
connects to an already-authenticated gateway instance.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx

from ib_mcp.models import (
    IBError,
    ProviderConfig,
    resolve_config,
    scrub_credentials,
)
from ib_mcp.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30.0
SESSION_CHECK_INTERVAL = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class AuthError(IBError):
    """Gateway session is not authenticated or has expired."""


class NotFoundError(IBError):
    """Requested resource not found (unknown conid, account, etc.)."""


class RateLimitError(IBError):
    """Too many requests to the gateway."""


class APIError(IBError):
    """Gateway returned an application-level error."""


class GatewayError(IBError):
    """Gateway is unreachable or returned an unexpected response."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class IBClient:
    """IB Client Portal Gateway API client.

    Handles session validation, rate limiting, and all REST API operations.
    The gateway must already be authenticated before use.
    """

    def __init__(self) -> None:
        self._config = resolve_config()
        self._http: httpx.AsyncClient | None = None
        self._rate_limiter = RateLimiter()
        self._session_valid: bool = False
        self._last_session_check: float = 0.0
        self._account_id: str | None = self._config.account_id
        self._accounts_cache: list[dict[str, Any]] | None = None

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def account_id(self) -> str | None:
        return self._account_id

    def _get_http(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                verify=self._config.ssl_verify,
            )
        return self._http

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def check_auth(self) -> dict[str, Any]:
        """Check gateway authentication status."""
        data = await self._get("/iserver/auth/status")
        self._session_valid = data.get("authenticated", False)
        self._last_session_check = time.time()
        return data

    async def tickle(self) -> dict[str, Any]:
        """Keep the gateway session alive (heartbeat)."""
        return await self._post("/tickle")

    async def reauthenticate(self) -> dict[str, Any]:
        """Trigger gateway re-authentication."""
        data = await self._post("/iserver/reauthenticate")
        # Give the gateway time to re-auth
        await asyncio.sleep(2)
        return data

    async def _ensure_session(self) -> None:
        """Ensure the gateway session is valid, checking periodically."""
        elapsed = time.time() - self._last_session_check
        if self._session_valid and elapsed < SESSION_CHECK_INTERVAL:
            return
        status = await self.check_auth()
        if not status.get("authenticated", False):
            # Try tickle first, then reauthenticate
            await self.tickle()
            await asyncio.sleep(1)
            status = await self.check_auth()
            if not status.get("authenticated", False):
                raise AuthError(
                    "Gateway session is not authenticated. "
                    "Open the Client Portal Gateway in a browser to log in."
                )

    async def _ensure_account(self) -> str:
        """Ensure we have a valid account ID, auto-detecting if needed."""
        if self._account_id:
            return self._account_id

        accounts = await self.list_accounts()
        if not accounts:
            raise IBError("No accounts found. Check your IB Gateway connection.")
        self._account_id = accounts[0].get("accountId", "")
        if not self._account_id:
            raise IBError("Account ID not found in gateway response.")
        logger.info("Auto-detected account: %s", self._account_id)
        return self._account_id

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _rate_limited(self):  # type: ignore[no-untyped-def]
        """Context manager for rate-limited requests."""
        await self._rate_limiter.acquire()
        try:
            yield
        finally:
            self._rate_limiter.release()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a GET request to the gateway."""
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, json_body: dict[str, Any] | list[Any] | None = None) -> Any:
        """Execute a POST request to the gateway."""
        return await self._request("POST", path, json_body=json_body)

    async def _put(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        """Execute a PUT request to the gateway."""
        return await self._request("PUT", path, json_body=json_body)

    async def _delete(self, path: str) -> Any:
        """Execute a DELETE request to the gateway."""
        return await self._request("DELETE", path)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        """Execute an HTTP request to the gateway."""
        url = f"{self._config.base_url}{path}"
        client = self._get_http()

        async with self._rate_limited():
            try:
                resp = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
            except httpx.TimeoutException as e:
                raise GatewayError(f"Gateway timeout: {e}") from e
            except httpx.ConnectError as e:
                raise GatewayError(
                    scrub_credentials(f"Cannot reach gateway at {self._config.gateway_url}: {e}", self._config)
                ) from e
            except httpx.HTTPError as e:
                raise GatewayError(scrub_credentials(f"HTTP error: {e}", self._config)) from e

        if resp.status_code == 401:
            self._session_valid = False
            raise AuthError("Gateway session expired. Re-authenticate in the browser.")

        if resp.status_code == 404:
            raise NotFoundError(f"Not found: {path}")

        if resp.status_code == 429:
            raise RateLimitError("Gateway rate limit exceeded — reduce request frequency.")

        if resp.status_code >= 400:
            text = resp.text[:500]
            raise APIError(
                f"{method} {path} returned HTTP {resp.status_code}",
                scrub_credentials(text, self._config),
            )

        # Some endpoints return empty body
        if not resp.content:
            return {}

        return resp.json()

    # ------------------------------------------------------------------
    # Portfolio API
    # ------------------------------------------------------------------

    async def list_accounts(self) -> list[dict[str, Any]]:
        """List brokerage accounts."""
        data = await self._get("/portfolio/accounts")
        if isinstance(data, list):
            self._accounts_cache = data
            return data
        return []

    async def get_positions(self, page_id: int = 0) -> list[dict[str, Any]]:
        """Get positions for the account."""
        account_id = await self._ensure_account()
        data = await self._get(f"/portfolio/{account_id}/positions/{page_id}")
        return data if isinstance(data, list) else []

    async def get_portfolio_summary(self) -> dict[str, Any]:
        """Get portfolio summary (NAV, cash, P&L, etc.)."""
        account_id = await self._ensure_account()
        return await self._get(f"/portfolio/{account_id}/summary")

    async def get_ledger(self) -> dict[str, Any]:
        """Get account ledger (cash balances by currency)."""
        account_id = await self._ensure_account()
        return await self._get(f"/portfolio/{account_id}/ledger")

    async def get_account_pnl(self) -> dict[str, Any]:
        """Get account-level P&L."""
        return await self._get("/iserver/account/pnl/partitioned")

    # ------------------------------------------------------------------
    # Market Data API
    # ------------------------------------------------------------------

    async def search_contracts(
        self,
        symbol: str,
        sec_type: str | None = None,
        name: bool = False,
    ) -> list[dict[str, Any]]:
        """Search for contracts by symbol or name."""
        body: dict[str, Any] = {"symbol": symbol, "name": name}
        if sec_type:
            body["secType"] = sec_type
        data = await self._post("/iserver/secdef/search", json_body=body)
        return data if isinstance(data, list) else []

    async def get_contract_info(self, conid: int) -> dict[str, Any]:
        """Get contract details by conid."""
        return await self._get(f"/iserver/contract/{conid}/info")

    async def get_snapshot(self, conids: list[int], fields: list[str] | None = None) -> list[dict[str, Any]]:
        """Get market data snapshot for conids.

        Note: First request for a conid subscribes to data. The initial response
        may be incomplete — a second call returns full data.
        """
        await self._rate_limiter.snapshot_throttle()
        params: dict[str, Any] = {"conids": ",".join(str(c) for c in conids)}
        if fields:
            params["fields"] = ",".join(fields)
        data = await self._get("/iserver/marketdata/snapshot", params=params)
        return data if isinstance(data, list) else []

    async def get_history(
        self,
        conid: int,
        period: str = "1d",
        bar: str = "1h",
        outside_rth: bool = False,
    ) -> dict[str, Any]:
        """Get historical market data bars."""
        params: dict[str, Any] = {
            "conid": conid,
            "period": period,
            "bar": bar,
            "outsideRth": outside_rth,
        }
        return await self._get("/iserver/marketdata/history", params=params)

    # ------------------------------------------------------------------
    # Order API — Read
    # ------------------------------------------------------------------

    async def list_orders(self, filters: list[str] | None = None) -> dict[str, Any]:
        """List live orders."""
        params: dict[str, Any] = {}
        if filters:
            params["filters"] = ",".join(filters)
        return await self._get("/iserver/account/orders", params=params)

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        """Get status of a specific order."""
        return await self._get(f"/iserver/account/order/status/{order_id}")

    async def get_trades(self) -> list[dict[str, Any]]:
        """Get recent trades/executions."""
        data = await self._get("/iserver/account/trades")
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Order API — Write
    # ------------------------------------------------------------------

    async def preview_order(
        self,
        account_id: str,
        orders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Preview order impact (what-if) without placing."""
        return await self._post(
            f"/iserver/account/{account_id}/orders/whatif",
            json_body={"orders": orders},
        )

    async def place_order(
        self,
        account_id: str,
        orders: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Place orders. May return confirmation prompts that need reply."""
        data = await self._post(
            f"/iserver/account/{account_id}/orders",
            json_body={"orders": orders},
        )
        return data if isinstance(data, list) else [data]

    async def reply_to_order(self, reply_id: str, confirmed: bool) -> list[dict[str, Any]]:
        """Reply to an order confirmation prompt."""
        data = await self._post(
            f"/iserver/reply/{reply_id}",
            json_body={"confirmed": confirmed},
        )
        return data if isinstance(data, list) else [data]

    async def modify_order(
        self,
        account_id: str,
        order_id: str,
        order: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Modify an existing order."""
        data = await self._post(
            f"/iserver/account/{account_id}/order/{order_id}",
            json_body=order,
        )
        return data if isinstance(data, list) else [data]

    async def cancel_order(self, account_id: str, order_id: str) -> dict[str, Any]:
        """Cancel an order."""
        return await self._delete(f"/iserver/account/{account_id}/order/{order_id}")

    # ------------------------------------------------------------------
    # Scanner API
    # ------------------------------------------------------------------

    async def get_scanner_params(self) -> dict[str, Any]:
        """Get available scanner parameters and filter options."""
        return await self._get("/iserver/scanner/params")

    async def run_scanner(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Run a market scanner."""
        data = await self._post("/iserver/scanner/run", json_body=params)
        return data if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # Rate limit status
    # ------------------------------------------------------------------

    def get_rate_status(self) -> str:
        """Return formatted rate limit status."""
        return self._rate_limiter.format_status()
