"""Shared fixtures for EnzymeTK app tests.

Backend fixtures use the ``fakeredis`` package, which faithfully
implements the Redis protocol in pure Python.  This catches
incompatibilities when ``redis-py`` or the server protocol is upgraded,
without requiring a running Redis instance for unit tests.
"""

from pathlib import Path

import fakeredis
import pandas as pd
import pytest
from dash import html

from enzyme_tk_app.app.backend.models import JobInfo, JobStatus
from enzyme_tk_app.app.components.footer import footer as create_footer
from enzyme_tk_app.app.components.hero import hero as create_hero
from enzyme_tk_app.app.components.navbar import navbar as create_navbar
from enzyme_tk_app.app.components.tool_cards import tool_card as create_tool_card
from enzyme_tk_app.app.components.tool_cards import tool_grid as create_tool_grid
from enzyme_tk_app.app.paths import REACTIONS_DIR, SEQUENCES_DIR
from enzyme_tk_app.app.utils import captcha, submission_limits


@pytest.fixture(autouse=True)
def _submission_limit_off(monkeypatch):
    """Pin the submission cap OFF for every test unless a test opts in.

    ``tox.ini`` sets ``passenv = *``, so a developer with ``APP_IN_PRODUCTION_MODE=1``
    exported would otherwise run the whole suite with the cap live — and every submit
    callback would reach for the real scheduler at ``redis://localhost:6379/0``.

    ``monkeypatch.setattr`` is required, not ``setenv``: the constants bind at import
    time, so changing the environment afterwards cannot flip them (the same reason
    ``test_backend_config.py`` patches ``config``'s globals directly).
    """
    monkeypatch.setattr(submission_limits, "PRODUCTION_MODE", False)
    # Pinned too, so the suite's expected messages do not move if the policy constant does.
    monkeypatch.setattr(submission_limits, "MAX_ACTIVE_JOBS_PER_SESSION", 3)


@pytest.fixture(autouse=True)
def _captcha_off(monkeypatch):
    """Pin the submission captcha OFF for every test unless a test opts in.

    A separate fixture from ``_submission_limit_off`` because it pins a separate binding:
    ``captcha.PRODUCTION_MODE`` and ``submission_limits.PRODUCTION_MODE`` are two module-level
    reads of the same ``APP_IN_PRODUCTION_MODE``, and patching one does nothing to the other.
    Without this, a developer with the switch exported (``tox.ini`` sets ``passenv = *``) would
    see every submit-callback test fail on a missing captcha payload.

    ``monkeypatch.setattr``, not ``setenv``: the constant binds at import.
    """
    monkeypatch.setattr(captcha, "PRODUCTION_MODE", False)


@pytest.fixture(autouse=True)
def _tool_data_checks_clean(monkeypatch):
    """Pin every tool's data checks to "nothing to report" for the whole suite.

    Third switch in the same family as the two fixtures above, and pinned for the
    same reason: ``data/`` is git-ignored apart from the demo sets, so what a given
    machine happens to have downloaded would otherwise decide test outcomes.
    ``validate_tool_data`` is OR'd into every tool's ``validate_*`` callback and is
    the first guard in every ``submit_*``, so without this pin a developer missing
    the Func-E checkpoints — and CI, which downloads nothing — sees Run disabled
    and every submit refused, for a reason that has nothing to do with the code
    under test.

    The registries on ``enzyme_tk_app.app.tools`` are what get replaced, because
    ``check_tool_data`` imports them *inside* the function on every call — so this
    single patch reaches the card badge, the Run gate and the submit guard alike.
    A test that wants a check to report something calls :func:`patch_tool_checks`,
    whose ``monkeypatch`` calls run after this one and therefore win.
    """
    monkeypatch.setattr("enzyme_tk_app.app.tools.CHECK_DATA", {})
    monkeypatch.setattr("enzyme_tk_app.app.tools.CHECK_DATA_WARNINGS", {})


def patch_tool_checks(monkeypatch, slug, blocking=(), warnings=()):
    """Register data checks for *slug* that report exactly the given labels.

    Patches the two registries on ``enzyme_tk_app.app.tools`` rather than any
    consumer's own binding: ``data_warning`` imports ``check_tool_data`` at module
    import time and every tool's callbacks import ``validate_tool_data`` the same
    way, so the registries are the one place that reaches all of them at once —
    and patching there is what makes the card and the modal provably agree.

    Every other tool is left unregistered while this is in force, which is exactly
    what a tool with no ``check_data.py`` looks like — so passing a slug the code
    under test does not use is how a test says "this tool has no data dependencies".

    Args:
        monkeypatch: The test's ``monkeypatch`` fixture.
        slug: Tool slug the checks are registered under.
        blocking: Labels for data the tool cannot run without — or a
            zero-argument callable, to register a check that raises.
        warnings: Labels for data that is present but unusable while the tool
            still runs; same two forms.
    """
    monkeypatch.setattr("enzyme_tk_app.app.tools.CHECK_DATA", {slug: _check_reporting(blocking)})
    monkeypatch.setattr("enzyme_tk_app.app.tools.CHECK_DATA_WARNINGS", {slug: _check_reporting(warnings)})


def _check_reporting(labels):
    """Return a ``check_data``-shaped callable reporting *labels* (a callable passes through)."""
    if callable(labels):
        return labels
    return lambda: list(labels)


# Directory containing test data files (CSV fixtures, etc.).
TEST_DATA_DIR = Path(__file__).parent / "data"

# Small 20-row reaction CSV extracted from the production database.
# Used by substrate/product similarity tests to run real enzymetk
# computations without needing the full (large) data files.
TEST_REACTIONS_CSV = TEST_DATA_DIR / "test_reactions_20.csv"

# Small 22-row sequence CSV extracted from the production database
# (20 valid rows from protein.csv + 2 invalid rows appended for testing).
TEST_SEQUENCES_CSV = TEST_DATA_DIR / "test_sequences_20.csv"


# ── Database dropdown helpers ────────────────────────────────────────────────


def offered_databases(*names):
    """Build the dropdown option list a tool's ``get_*_database_options()`` would return.

    ``validate_db_names`` checks the submitted names against exactly this list,
    so a callback test that submits an invented database name patches its
    tool's option builder with ``return_value=offered_databases(...)`` to say
    "the dropdown is offering these".
    """
    return [{"label": name, "value": name} for name in names]


# ── Reaction data helpers ────────────────────────────────────────────────────


def make_reaction_df(reactions: list[str]) -> pd.DataFrame:
    """Build a minimal DataFrame with ``id`` and ``unmapped`` columns."""
    return pd.DataFrame(
        {
            "id": list(range(len(reactions))),
            "unmapped": reactions,
        }
    )


@pytest.fixture()
def _patch_reactions_dir(reactions_dir, monkeypatch):
    """Patch ``REACTIONS_DIR`` so ``run()`` reads the 20-row test fixture.

    Both copies of the constant are patched: ``compute`` uses it to build the
    file path, and ``data_loading`` uses it to build the dropdown options that
    ``validate_db_names`` now checks membership against.
    """
    patched_dir = reactions_dir / REACTIONS_DIR.name
    monkeypatch.setattr(
        "enzyme_tk_app.app.tools.substrate_product_similarity.compute.REACTIONS_DIR",
        patched_dir,
    )
    monkeypatch.setattr("enzyme_tk_app.app.utils.data_loading.REACTIONS_DIR", patched_dir)


@pytest.fixture()
def reactions_dir(tmp_path):
    """Copy the 20-row test CSV into a ``tmp_path/<REACTIONS_DIR.name>/`` directory.

    Returns ``tmp_path`` so ``_patch_*`` fixtures can derive the
    reactions subdirectory from it.
    """
    import shutil  # noqa: PLC0415

    dest = tmp_path / REACTIONS_DIR.name
    dest.mkdir()
    shutil.copy(TEST_REACTIONS_CSV, dest / "test_reactions_20.csv")
    return tmp_path


@pytest.fixture()
def csv_molecules():
    """Extract unique substrate and product SMILES from the 20-row test CSV.

    Parses the ``unmapped`` column of ``test_reactions_20.csv``, splits
    each reaction on ``>>``, then splits each side on ``.`` to collect
    individual molecule SMILES.  Trivial molecules (water, H+, Cl) and
    very long cofactors (CoA, NADPH) are excluded.

    Returns:
        Dict with ``"substrates"`` and ``"products"`` keys, each mapping
        to a sorted list of unique SMILES strings.
    """
    df = pd.read_csv(TEST_REACTIONS_CSV)
    substrates: set[str] = set()
    products: set[str] = set()

    # Trivial molecules excluded from exact-match testing — too simple for
    # meaningful fingerprint comparison or not real "target" molecules.
    _TRIVIAL_SMILES = {"O", "[H+]", "Cl"}

    # Maximum SMILES length for exact-match testing — excludes huge cofactors
    # (CoA, NADPH) that would slow tests without adding coverage value.
    _MAX_SMILES_LEN = 100

    for unmapped in df["unmapped"].dropna():
        if ">>" not in unmapped:
            continue
        left, right = unmapped.split(">>", 1)
        for smi in left.split("."):
            smi = smi.strip()
            if smi and smi not in _TRIVIAL_SMILES and len(smi) <= _MAX_SMILES_LEN:
                substrates.add(smi)
        for smi in right.split("."):
            smi = smi.strip()
            if smi and smi not in _TRIVIAL_SMILES and len(smi) <= _MAX_SMILES_LEN:
                products.add(smi)

    return {"substrates": sorted(substrates), "products": sorted(products)}


@pytest.fixture()
def csv_molecules_known_scores():
    """Molecules with hardcoded expected similarity scores for regression testing.

    Each entry specifies a query SMILES, the role to search, and the
    expected top-result scores for all three algorithms.  If
    ``expected_top_smiles`` is set, the SMILES of the top-ranked result
    is also verified.

    These values were obtained from a known-good run of the tool and
    pinned here to catch any change in the underlying enzymetk or RDKit
    fingerprint calculation.
    """
    return [
        {
            "query": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            "role": "product",
            "expected_top_smiles": None,
            "expected_tanimoto": 1.0,
            "expected_cosine": 1.0,
            "expected_russell": 0.0083,
        },
        {
            "query": "[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            "role": "substrate",
            "expected_top_smiles": "O[C@@H]1[C@@H](O)[C@H](O)OC[C@H]1O",
            "expected_tanimoto": 0.2917,
            "expected_cosine": 0.4518,
            "expected_russell": 0.0034,
        },
    ]


@pytest.fixture()
def sequences_dir(tmp_path):
    """Copy the 20-row test sequence CSV into a ``tmp_path/<SEQUENCES_DIR.name>/`` directory.

    Returns ``tmp_path`` so ``_patch_*`` fixtures can derive the
    sequences subdirectory from it.
    """
    import shutil  # noqa: PLC0415

    dest = tmp_path / SEQUENCES_DIR.name
    dest.mkdir()
    shutil.copy(TEST_SEQUENCES_CSV, dest / "test_sequences_20.csv")
    return tmp_path


@pytest.fixture()
def sequence_csv(tmp_path):
    """Copy the 20-row test sequence CSV for testing data loader filters.

    Contains valid sequences, NaN sequences, and whitespace sequences.
    """
    import shutil  # noqa: PLC0415

    csv_file = tmp_path / "test_sequences_20.csv"
    shutil.copy(TEST_SEQUENCES_CSV, csv_file)
    return csv_file


# ── UI component fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def navbar():
    return create_navbar()


@pytest.fixture()
def footer():
    return create_footer()


@pytest.fixture()
def hero():
    return create_hero()


@pytest.fixture()
def tool_grid():
    return create_tool_grid()


@pytest.fixture()
def sample_tool_card():
    return create_tool_card(
        slug="test-tool",
        title="Test Tool",
        description="A test description",
        icon_class="fa-solid fa-wrench",
        libraries=["numpy", "pandas"],
    )


@pytest.fixture()
def sample_tool_card_no_libs():
    return create_tool_card(
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
        **extra,
    }
    fake_redis.hset(f"job:{job_id}", mapping=mapping)
    fake_redis.sadd(f"session:{session_id}:jobs", job_id)


def make_job(*, params=None, result=None, **overrides) -> JobInfo:
    """Create a minimal ``JobInfo`` for testing.

    Sensible defaults are provided for all identity fields so tests
    only need to specify the fields they care about.

    Args:
        params: Job parameters dict (default empty).
        result: Job result dict (default ``None``).
        **overrides: Any ``JobInfo`` field to override (e.g.
            ``status=JobStatus.FAILURE``, ``session_id="other"``).
    """
    defaults = {
        "job_id": "test-id",
        "tool_slug": "test-tool",
        "status": JobStatus.SUCCESS,
        "session_id": "sess-1",
        "submitted_at": "2025-01-01T00:00:00+00:00",
        "params": params or {},
        "result": result,
    }
    defaults.update(overrides)
    return JobInfo(**defaults)


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
    # If children is a single component (not a string or list),
    # we recursively extract its text content
    # this will allow it to reach tools like dbc.Badge which have a
    # single child that is the text we want to extract
    elif children is not None:
        parts.append(get_text(children))
    return " ".join(parts).strip()


def submitted_job_id(result):
    """Return the full job id from a submission success block's tooltip.

    ``build_submission_success`` shows only the ``truncate_id`` prefix on screen and
    keeps the full id in the id span's ``title`` — so a substring assertion against
    the rendered text cannot see the whole id.  This reads the value the tooltip
    actually carries, which is the contract worth asserting.

    Args:
        result: The component returned by a tool's ``submit_*`` callback.

    Returns:
        The full job id string.
    """
    spans = [s for s in find_components(result, html.Span) if getattr(s, "title", None)]
    assert len(spans) == 1, f"Expected exactly one tooltipped id span, found {len(spans)}"
    return spans[0].title


def submission_error_text(result):
    """Return the message from a submission error block, asserting its shape first.

    Both submit outcomes are components sharing the ``modal-submission-row``
    base class and differing by their own class, so a test that only reads the
    text cannot tell an error from a success.  This pins that the caller really
    got an error row — not a success row, and not a bare string, which would
    render with no box and no icon — then hands back the text for substring
    assertions.

    Args:
        result: The component returned by a tool's ``submit_*`` callback.

    Returns:
        The rendered text of the error row.
    """
    assert not isinstance(result, str), "A submit error must be the shared error block, not a bare string"
    classes = (getattr(result, "className", "") or "").split()
    assert "modal-submission-error" in classes, f"Expected a modal-submission-error row, got {classes!r}"
    text = get_text(result)
    assert text.strip(), "The error block carries no message"
    return text
