"""Tests for backend configuration helpers (``backend.config``)."""

import os
import uuid
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


# ── job_output_paths ─────────────────────────────────────────────────────────
# job_output_paths is the single validated choke point that turns a job_id
# into on-disk paths. Every consumer (including the destructive rmtree in
# _delete_job_outputs) relies on its containment check, so the escaping-job_id
# cases below are security-critical, not just input validation.


def test_job_output_paths_valid_job_id_builds_child_paths(tmp_path):
    """A clean job_id resolves to paths directly under JOB_OUTPUTS_PATH.

    Why this matters: the returned ``dir`` must be ``JOB_OUTPUTS_PATH/<job_id>``
    and the result/log files must live inside it using the shared filename
    constants, so the worker that writes them and the web container that reads
    them can never drift out of sync.
    """
    outputs_path = str(tmp_path / "job_outputs")
    job_id = str(uuid.uuid4())

    with patch.object(config, "JOB_OUTPUTS_PATH", outputs_path):
        paths = config.job_output_paths(job_id)

    expected_dir = os.path.join(outputs_path, job_id)
    assert paths.directory == expected_dir
    # Assert against the constants, not literal filenames, so the test tracks
    # any change to the single source of truth in config.py.
    assert paths.result == os.path.join(expected_dir, config.JOB_RESULT_FILENAME)
    assert paths.log == os.path.join(expected_dir, config.JOB_LOG_FILENAME)


@pytest.mark.parametrize(
    "job_id",
    [
        "../parent",
        "../../etc/passwd",
        "a/b",
        "",
        "/etc",
    ],
    ids=["parent-traversal", "deep-traversal", "nested-subdir", "empty", "absolute-path"],
)
def test_job_output_paths_rejects_escaping_job_id(tmp_path, job_id):
    """Any job_id that resolves outside JOB_OUTPUTS_PATH raises ValueError.

    Why this matters: a ``..`` sequence, a nested subdirectory, or an absolute
    path would let a malicious or buggy job_id point at data elsewhere on disk.
    The containment check must refuse anything that is not a direct child of
    the volume before a consumer can act on the path.
    """
    with patch.object(config, "JOB_OUTPUTS_PATH", str(tmp_path / "job_outputs")), pytest.raises(ValueError):
        config.job_output_paths(job_id)
