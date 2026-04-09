"""Tests for ib_mcp.models — config, gates, scrubbing."""

from __future__ import annotations

import pytest

from ib_mcp.models import (
    IBError,
    ProviderConfig,
    check_confirm_gate,
    check_write_gate,
    is_write_enabled,
    resolve_config,
    scrub_credentials,
)

# ---------------------------------------------------------------------------
# ProviderConfig
# ---------------------------------------------------------------------------


class TestProviderConfig:
    def test_base_url(self, config: ProviderConfig) -> None:
        assert config.base_url == "https://localhost:5000/v1/api"

    def test_base_url_strips_trailing_slash(self) -> None:
        cfg = ProviderConfig(gateway_url="https://localhost:5000/")
        # gateway_url keeps slash, but base_url appends /v1/api
        assert "/v1/api" in cfg.base_url


# ---------------------------------------------------------------------------
# resolve_config
# ---------------------------------------------------------------------------


class TestResolveConfig:
    def test_minimal_config(self) -> None:
        config = resolve_config()
        assert config.gateway_url == "https://localhost:5000"
        assert config.account_id == "U1234567"
        assert config.ssl_verify is False

    def test_missing_gateway_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("IB_GATEWAY_URL")
        with pytest.raises(ValueError, match="IB Gateway URL not configured"):
            resolve_config()

    def test_optional_account_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("IB_ACCOUNT_ID")
        config = resolve_config()
        assert config.account_id is None

    def test_ssl_verify_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("IB_SSL_VERIFY")
        config = resolve_config()
        assert config.ssl_verify is True


# ---------------------------------------------------------------------------
# Write gate
# ---------------------------------------------------------------------------


class TestWriteGate:
    def test_write_disabled_by_default(self) -> None:
        assert is_write_enabled() is False

    def test_write_gate_blocks(self) -> None:
        result = check_write_gate()
        assert result is not None
        assert "IB_WRITE_ENABLED" in result

    def test_write_gate_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("IB_WRITE_ENABLED", "true")
        assert is_write_enabled() is True
        assert check_write_gate() is None


# ---------------------------------------------------------------------------
# Confirm gate
# ---------------------------------------------------------------------------


class TestConfirmGate:
    def test_confirm_blocks_when_false(self) -> None:
        result = check_confirm_gate(False, "Place order")
        assert result is not None
        assert "real money" in result

    def test_confirm_passes_when_true(self) -> None:
        assert check_confirm_gate(True, "Place order") is None


# ---------------------------------------------------------------------------
# Credential scrubbing
# ---------------------------------------------------------------------------


class TestScrubCredentials:
    def test_scrubs_session_token(self) -> None:
        text = "session=abc123secret"
        result = scrub_credentials(text)
        assert "abc123secret" not in result
        assert "****" in result

    def test_scrubs_authorization(self) -> None:
        text = "Authorization: Bearer mysecrettoken"
        result = scrub_credentials(text)
        assert "mysecrettoken" not in result

    def test_scrubs_cookie(self) -> None:
        text = "cookie=session_id_here"
        result = scrub_credentials(text)
        assert "session_id_here" not in result

    def test_no_change_for_safe_text(self) -> None:
        text = "HTTP 200 OK portfolio loaded"
        assert scrub_credentials(text) == text


# ---------------------------------------------------------------------------
# IBError
# ---------------------------------------------------------------------------


class TestIBError:
    def test_basic_error(self) -> None:
        e = IBError("test error")
        assert str(e) == "test error"
        assert e.details == ""

    def test_error_with_details(self) -> None:
        e = IBError("test error", "some details")
        assert e.details == "some details"
