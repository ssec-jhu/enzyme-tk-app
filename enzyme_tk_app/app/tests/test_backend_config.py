"""Tests for backend configuration helpers (``backend.config``)."""

from unittest.mock import patch

import pytest

from enzyme_tk_app.app.backend import config

# admin_enabled reads these two module-level globals, so the tests patch them
# directly rather than re-importing the module with different environment vars.
ADMIN_TOKEN_PATH = "enzyme_tk_app.app.backend.config.ADMIN_TOKEN"
SECRET_KEY_PATH = "enzyme_tk_app.app.backend.config.SECRET_KEY"


# ── admin_enabled ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("token", "secret", "expected"),
    [
        ("a-token", "a-secret", True),  # both set → enabled
        ("a-token", "", False),  # secret missing → disabled
        ("", "a-secret", False),  # token missing → disabled
        ("", "", False),  # neither set → disabled (fail-closed default)
    ],
    ids=["both-set", "no-secret", "no-token", "neither-set"],
)
def test_admin_enabled_requires_both_token_and_secret(token, secret, expected):
    """admin_enabled() must be True only when BOTH the token and secret are set."""
    with patch(ADMIN_TOKEN_PATH, token), patch(SECRET_KEY_PATH, secret):
        assert config.admin_enabled() is expected
