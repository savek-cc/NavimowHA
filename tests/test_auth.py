"""Tests for auth helpers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.navimow.auth import async_get_oauth_token

from .const import MOCK_TOKEN


# ---------------------------------------------------------------------------
# async_get_oauth_token
# ---------------------------------------------------------------------------


class TestAsyncGetOAuthToken:
    """Tests for the async_get_oauth_token helper."""

    async def test_uses_ensure_token_valid(self) -> None:
        """Prefers async_ensure_token_valid when available."""
        session = MagicMock()
        session.async_ensure_token_valid = AsyncMock()
        session.token = dict(MOCK_TOKEN)

        result = await async_get_oauth_token(session)
        session.async_ensure_token_valid.assert_awaited_once()
        assert result == MOCK_TOKEN

    async def test_uses_get_valid_token(self) -> None:
        """Falls back to async_get_valid_token when ensure is missing."""
        session = MagicMock(spec=[])  # empty spec
        session.async_get_valid_token = AsyncMock(return_value=dict(MOCK_TOKEN))
        # Remove async_ensure_token_valid
        del session.async_ensure_token_valid

        # async_get_oauth_token checks hasattr, so we need to be precise
        session_obj = MagicMock()
        # Remove async_ensure_token_valid
        type(session_obj).async_ensure_token_valid = PropertyMock(
            side_effect=AttributeError
        )

        # Use a simpler approach: create a minimal object
        class FakeSession:
            async def async_get_valid_token(self):
                return dict(MOCK_TOKEN)

        result = await async_get_oauth_token(FakeSession())
        assert result is not None
        assert result["access_token"] == MOCK_TOKEN["access_token"]

    async def test_fallback_to_cached_token(self) -> None:
        """Falls back to .token attribute when no methods available."""

        class BareSession:
            token = dict(MOCK_TOKEN)

        result = await async_get_oauth_token(BareSession())
        assert result is not None
        assert result["access_token"] == MOCK_TOKEN["access_token"]

    async def test_returns_none_when_no_token(self) -> None:
        """Returns None when no token available at all."""

        class EmptySession:
            pass

        result = await async_get_oauth_token(EmptySession())
        assert result is None


# ---------------------------------------------------------------------------
# NavimowOAuth2Implementation
# ---------------------------------------------------------------------------


class TestNavimowOAuth2Implementation:
    """Tests for NavimowOAuth2Implementation."""

    async def test_name_property(self, hass) -> None:
        """Implementation has correct name."""
        from custom_components.navimow.auth import NavimowOAuth2Implementation

        impl = NavimowOAuth2Implementation(
            hass=hass,
            domain="navimow",
            client_id="test-id",
            client_secret="test-secret",
        )
        assert impl.name == "Navimow"

    async def test_refresh_token_missing_raises_auth_failed(self, hass) -> None:
        """No refresh_token in token dict -> ConfigEntryAuthFailed."""
        from custom_components.navimow.auth import NavimowOAuth2Implementation

        impl = NavimowOAuth2Implementation(
            hass=hass,
            domain="navimow",
            client_id="test-id",
            client_secret="test-secret",
        )

        with pytest.raises(ConfigEntryAuthFailed, match="no refresh token"):
            await impl._async_refresh_token({"access_token": "old"})

    async def test_refresh_token_auth_rejection_raises_auth_failed(
        self, hass
    ) -> None:
        """Server 401/403 during refresh -> ConfigEntryAuthFailed."""
        from custom_components.navimow.auth import NavimowOAuth2Implementation

        impl = NavimowOAuth2Implementation(
            hass=hass,
            domain="navimow",
            client_id="test-id",
            client_secret="test-secret",
        )

        with pytest.raises(ConfigEntryAuthFailed, match="expired"):
            # Simulate super()._async_refresh_token raising a generic error with 401
            with MagicMock() as mock_parent:
                # We patch the parent class method
                from unittest.mock import patch

                with patch(
                    "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation._async_refresh_token",
                    side_effect=Exception("401 Unauthorized"),
                ):
                    await impl._async_refresh_token(
                        {"access_token": "old", "refresh_token": "expired-rt"}
                    )

    async def test_refresh_token_transient_error_propagates(self, hass) -> None:
        """Transient error (network) is not wrapped in ConfigEntryAuthFailed."""
        from custom_components.navimow.auth import NavimowOAuth2Implementation

        impl = NavimowOAuth2Implementation(
            hass=hass,
            domain="navimow",
            client_id="test-id",
            client_secret="test-secret",
        )

        from unittest.mock import patch

        with patch(
            "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation._async_refresh_token",
            side_effect=ConnectionError("DNS resolution failed"),
        ):
            with pytest.raises(ConnectionError, match="DNS"):
                await impl._async_refresh_token(
                    {"access_token": "old", "refresh_token": "valid-rt"}
                )

    async def test_generate_authorize_url_appends_channel(self, hass) -> None:
        """async_generate_authorize_url appends channel=homeassistant."""
        from custom_components.navimow.auth import NavimowOAuth2Implementation

        impl = NavimowOAuth2Implementation(
            hass=hass,
            domain="navimow",
            client_id="test-id",
            client_secret="test-secret",
        )

        from unittest.mock import patch

        with patch(
            "homeassistant.helpers.config_entry_oauth2_flow.LocalOAuth2Implementation.async_generate_authorize_url",
            new_callable=AsyncMock,
            return_value="https://example.com/auth?client_id=test",
        ):
            url = await impl.async_generate_authorize_url("redirect_uri")
            assert "channel=homeassistant" in url
