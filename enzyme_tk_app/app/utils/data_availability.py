"""Whether a tool has the data it needs — the one answer the card and the modal share.

A tool reports its data through up to two callables in its own ``check_data.py``
(see ``tools/__init__.py``): ``check_data()`` names what it **needs and does not
have**, ``check_data_warnings()`` names what is **present but unusable** while it
still runs.  The split matters: ``data/sequences/`` holding one good database
beside one malformed file is a tool that works, not a tool to switch off.

Two consumers read this module, and they must never disagree about what
"missing" means — the card would warn about a tool that submits fine, or say
nothing about one whose Run button is dead:

- ``components/data_warning.py`` renders the card's badge, tooltip and note.
- every tool's ``callbacks.py`` disables Run, explains why in the modal, and
  re-checks on submit.

Why ``validate_tool_data`` is checked in three places per tool rather than one:
the ``disabled`` on Run is a client gate and a browser can ignore it, and a page
left open while the data mount changes underneath it keeps a stale enabled Run.
That is the same reasoning ``utils/smiles_validation.py`` already carries.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Named once: the message, the card note and the docs must all point at the same script.
DOWNLOAD_SCRIPT = "scripts/db_build/download_data.py"

# What a check that raised contributes, in place of the labels it did not return.
# Treated as blocking: the badge has always degraded to this, and a gate that
# disagreed with the badge would wave through exactly the job that cannot run.
CHECK_FAILED_LABEL = "Data check failed"

# Shown instead of the "Requires ..." sentence when the check itself broke: there
# is no path to name, and downloading data would not fix a raising check anyway.
CHECK_FAILED_MESSAGE = "This tool's data check failed, so it cannot be run — see the server log."

# A check label reads "Func-E ensemble checkpoints (data/funce_models/)" — a human
# name plus the path on disk.  The card note and the modal message want the path
# alone; the full label stays in the badge's tooltip.
_DATA_PATH = re.compile(r"\(([^)]*\bdata/[^)]*)\)")


def missing_data_paths(labels: list[str]) -> list[str]:
    """Return each label's ``data/...`` fragment, or the whole label when it has none.

    Falling back rather than dropping the label: a future tool may word its check
    without a parenthetical path, and saying too much beats saying nothing.
    """
    return [match.group(1) if (match := _DATA_PATH.search(label)) else label for label in labels]


def _run_check(check_map: dict, slug: str) -> list[str]:
    """Run ``check_map[slug]`` defensively, returning its labels (empty when unregistered).

    A buggy check must never break the home page or a modal, so an exception is
    logged and reported as :data:`CHECK_FAILED_LABEL` instead of propagating.
    """
    check_fn = check_map.get(slug)
    if check_fn is None:
        return []
    try:
        return check_fn()
    except Exception:
        logger.warning("data check raised for tool %s", slug, exc_info=True)
        return [CHECK_FAILED_LABEL]


def check_tool_data(slug: str) -> tuple[list[str], list[str]]:
    """Return ``(blocking, warnings)`` for *slug*, running each registered check once.

    Args:
        slug: Tool slug.  One with no registered check has no data dependencies
            and gets ``([], [])``.

    Returns:
        *blocking* are labels for data the tool cannot run without; *warnings*
        are labels for data that is present but unusable while it still runs.
    """
    # Imported here, not at module scope: ``tools/__init__`` imports every
    # tool's callbacks.py during discovery, and those import this module — a
    # module-level ``from ... import CHECK_DATA`` would only work by accident of
    # the statement order in that file.
    from enzyme_tk_app.app.tools import CHECK_DATA, CHECK_DATA_WARNINGS  # noqa: PLC0415

    return _run_check(CHECK_DATA, slug), _run_check(CHECK_DATA_WARNINGS, slug)


def validate_tool_data(slug: str) -> str | None:
    """Return an error message when *slug* is missing data it needs, else ``None``.

    Message-or-``None``, like ``validate_db_names`` / ``validate_top_n`` /
    ``validate_active_job_limit``, so it reads identically to the validators it
    sits beside in every submit callback.  Returning rather than raising is
    required: the app installs no Dash ``on_error`` handler, so an exception
    would surface as an HTTP 500 on ``/_dash-update-component`` instead of as
    text in the modal.

    Advisory items are deliberately ignored here — they are the card's business.
    A tool with one unusable file beside a usable one still runs.

    Args:
        slug: Tool slug.

    Returns:
        A terse message naming the missing paths and the script that fetches
        them, or ``None`` when the tool can run.
    """
    blocking, _warnings = check_tool_data(slug)
    if not blocking:
        return None
    if CHECK_FAILED_LABEL in blocking:
        return CHECK_FAILED_MESSAGE
    return f"Requires {', '.join(missing_data_paths(blocking))}. Download using {DOWNLOAD_SCRIPT}."
