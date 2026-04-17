"""Compute function for the Timer tool — **canonical example** for new tools.

Sleeps for the requested number of seconds, then generates a random
DataFrame — useful for testing and demonstrating the backend job
scheduling pipeline and the results-viewing system.

How compute functions work
--------------------------
- Each tool exposes ``run(params: dict) → dict`` in ``compute.py``.
- ``params`` is the exact dict passed by the callback to
  ``scheduler.submit_job(params=...)``.  Its keys match the form
  fields from the modal.
- The returned dict **must be JSON-serialisable** (plain dicts, lists,
  strings, numbers, bools, ``None``).  No custom objects.  Pandas
  DataFrames must be serialised to ``{"columns": [...], "data": [...]}``.
- Large results (> 512 KB) are automatically offloaded to disk by the
  backend — tool authors just return a plain dict.

Special return-dict keys
~~~~~~~~~~~~~~~~~~~~~~~~
``_stat_cards`` : list[dict]
    A list of ``{"label": "...", "value": "..."}`` dicts rendered as
    stat cards at the top of the results page by
    ``build_result_stat_cards()`` in ``results_helpers.py``.  Every tool
    should include at least one or two timing/summary stats here.

``_params_exclude`` : list[str]
    Keys from ``params`` that should **not** appear in the "Input
    Parameters" table on the results page.  For example, a large
    SMILES string or a binary payload that would clutter the display.

All other keys are tool-specific and rendered by the tool's
``results.py`` (or the raw-JSON fallback if ``results.py`` is absent).
"""

import random
import time

import pandas as pd

from enzyme_tk_app.app.utils.columns import (
    COL_ACTIVITY_SCORE,
    COL_SAMPLE_ID,
    COL_STABILITY_SCORE,
    COL_TEMPERATURE_C,
    COL_YIELD_PCT,
)


def _generate_random_dataframe(n_rows: int = 20) -> pd.DataFrame:
    """Create a random DataFrame of simulated assay results.

    This is a **demo helper** — real tools would call an algorithm
    library (e.g. enzymetk, RDKit) instead of generating random data.

    Args:
        n_rows: Number of rows to generate.

    Returns:
        A ``pd.DataFrame`` with columns: sample_id, activity_score,
        stability_score, temperature_c, yield_pct.
    """
    # Row-ID prefixes used to populate the demo DataFrame.
    ids = ["ENZ", "MUT", "WT", "VAR"]
    data = {
        COL_SAMPLE_ID: [f"{random.choice(ids)}-{i:03d}" for i in range(1, n_rows + 1)],
        COL_ACTIVITY_SCORE: [round(random.uniform(0.5, 150.0), 2) for _ in range(n_rows)],
        COL_STABILITY_SCORE: [round(random.uniform(35.0, 85.0), 1) for _ in range(n_rows)],
        COL_TEMPERATURE_C: [random.randint(20, 80) for _ in range(n_rows)],
        COL_YIELD_PCT: [round(random.uniform(5.0, 98.0), 1) for _ in range(n_rows)],
    }
    return pd.DataFrame(data)


def run(params: dict) -> dict:
    """Sleep for the specified number of seconds, then return a random DataFrame.

    This is the **canonical example** of a ``compute.run()`` function.
    Study the return dict carefully — it shows how ``_stat_cards`` and
    ``_params_exclude`` are used by the results page.

    Args:
        params: Dictionary submitted by the modal callback.  Keys:
            - ``"seconds"`` (int): how long the task should run.
            - ``"simulate_failure"`` (bool, optional): if ``True``, raise
              an exception halfway through to test the failure path.

    Returns:
        A JSON-serializable dict with:
        - ``_stat_cards``: stat-card data rendered at the top of the results page.
        - ``_params_exclude``: params keys to hide from the "Input Parameters" table.
        - ``requested_seconds``, ``actual_elapsed``: plain
          scalar values accessible by ``results.py``.
        - ``dataframe``: ``{"columns": [...], "data": [...]}``.

    Raises:
        RuntimeError: When ``simulate_failure`` is ``True`` — thrown after
            sleeping for half the requested duration.
    """
    seconds = int(params["seconds"])
    simulate_failure = bool(params.get("simulate_failure", False))
    start = time.monotonic()

    # ── Failure simulation ──────────────────────────────────────────
    # Useful for testing the failure / error-details UI on the results
    # page.  Real tools should NOT include this — it is demo-only.
    if simulate_failure:
        time.sleep(seconds / 2)
        raise RuntimeError(
            f"Simulated failure after {round(time.monotonic() - start, 3)}s "
            f"(requested {seconds}s). This error was triggered intentionally "
            "via the 'Simulate failure' checkbox."
        )

    # ── Main work ───────────────────────────────────────────────────
    # In a real tool this would call an algorithm library.
    time.sleep(seconds)
    elapsed = time.monotonic() - start

    # Generate a random DataFrame to demonstrate tabular results.
    df = _generate_random_dataframe(n_rows=20)

    return {
        # ── _stat_cards: stat cards shown at the top of the results page ──
        # Each item is a dict with "label" (small uppercase text) and
        # "value" (large bold text).  The shared ``build_result_stat_cards``
        # helper renders these automatically — no custom code needed.
        "_stat_cards": [
            {"label": "Timer Set to", "value": f"{seconds}s"},
            {"label": "Actual Elapsed", "value": f"{round(elapsed, 3)}s"},
            {"label": "Rows Generated", "value": str(len(df))},
        ],
        # ── _params_exclude: hide noisy params from the results page ──
        # The "Input Parameters" table auto-renders every key from the
        # submitted ``params`` dict.  List keys here that should be
        # suppressed (e.g. large binary payloads, internal flags).
        # In this demo we hide ``simulate_failure`` — it is only useful
        # for developers, not end-users reviewing results.
        "_params_exclude": ["simulate_failure"],
        # ── Tabular data ────────────────────────────────────────────
        # Serialised as {"columns": [...], "data": [records]} so it
        # can be fed directly into ``dash_table.DataTable``.
        "dataframe": {
            "columns": df.columns.tolist(),
            "data": df.to_dict(orient="records"),
        },
    }
