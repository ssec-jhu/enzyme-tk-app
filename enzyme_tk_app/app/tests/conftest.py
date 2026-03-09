"""Shared fixtures for EnzymeTK app tests.

Backend fixtures use the ``fakeredis`` package, which faithfully
implements the Redis protocol in pure Python.  This catches
incompatibilities when ``redis-py`` or the server protocol is upgraded,
without requiring a running Redis instance for unit tests.
"""

import fakeredis
import pytest

from enzyme_tk_app.app.components.footer import Footer
from enzyme_tk_app.app.components.hero import Hero
from enzyme_tk_app.app.components.navbar import Navbar
from enzyme_tk_app.app.components.tool_cards import ToolCard, ToolGrid

# ── UI component fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def navbar():
    return Navbar()


@pytest.fixture()
def footer():
    return Footer()


@pytest.fixture()
def hero():
    return Hero()


@pytest.fixture()
def tool_grid():
    return ToolGrid()


@pytest.fixture()
def sample_tool_card():
    return ToolCard(
        slug="test-tool",
        title="Test Tool",
        description="A test description",
        icon_class="fa-solid fa-wrench",
        libraries=["numpy", "pandas"],
    )


@pytest.fixture()
def sample_tool_card_no_libs():
    return ToolCard(
        slug="bare-tool",
        title="Bare Tool",
        description="No libraries",
        icon_class="fa-solid fa-gear",
    )


# ── Backend fixtures ─────────────────────────────────────────────────────────
# Uses the ``fakeredis`` package — a protocol-faithful, pure-Python Redis
# implementation that tracks real ``redis-py`` releases.  If a new version
# of ``redis-py`` changes a command's return type or adds a required kwarg,
# the fakeredis tests will break here rather than silently passing.


@pytest.fixture()
def fake_redis():
    """Fresh fakeredis instance — empty database, no network."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def task_scheduler_celery_service(fake_redis):
    """CeleryTaskScheduler wired to fakeredis (no real Redis or Celery)."""
    from enzyme_tk_app.app.backend.task_scheduler_celery import CeleryTaskScheduler  # noqa: PLC0415

    svc = CeleryTaskScheduler.__new__(CeleryTaskScheduler)
    svc._redis = fake_redis
    return svc


def write_job_into_fake_redis(fake_redis, job_id, session_id, status="PENDING", **extra):
    """Write a job hash and session-set entry into fakeredis.

    Use this in tests to set up pre-existing jobs before calling
    scheduler methods like ``get_job``, ``delete_job``, etc.

    Args:
        fake_redis: The fakeredis instance (from the ``fake_redis`` fixture).
        job_id: Arbitrary job ID string.
        session_id: Session that "owns" the job.
        status: Initial ``JobStatus`` value string (default ``"PENDING"``).
        **extra: Additional hash fields to merge (e.g. ``result='{"k":1}'``).
    """
    mapping = {
        "job_id": job_id,
        "tool_slug": "test-tool",
        "status": status,
        "session_id": session_id,
        "submitted_at": "2025-01-01T00:00:00+00:00",
        "params": "{}",
        "output_log": "",
        **extra,
    }
    fake_redis.hset(f"job:{job_id}", mapping=mapping)
    fake_redis.sadd(f"session:{session_id}:jobs", job_id)


def find_components(component, target_type, results=None):
    """Recursively find all Dash components of a given type in a component tree.

    Args:
        component: Root Dash component to search.
        target_type: The component class to find (e.g., html.A, html.Img).
        results: Accumulator list (internal).

    Returns:
        List of matching components.
    """
    if results is None:
        results = []
    if isinstance(component, target_type):
        results.append(component)
    children = getattr(component, "children", None)
    if isinstance(children, list):
        for child in children:
            find_components(child, target_type, results)
    elif children is not None:
        find_components(children, target_type, results)
    return results


def get_text(component):
    """Extract concatenated text content from a Dash component tree.

    Args:
        component: Root Dash component.

    Returns:
        A string with all text content joined by spaces.
    """
    if isinstance(component, str):
        return component
    parts = []
    children = getattr(component, "children", None)
    if isinstance(children, str):
        parts.append(children)
    elif isinstance(children, list):
        for child in children:
            parts.append(get_text(child))
    return " ".join(parts).strip()
