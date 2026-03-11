"""Compute function for the Timer tool.

Sleeps for the requested number of seconds, then generates a random
enzyme-activity DataFrame — useful for testing and demonstrating the
backend job scheduling pipeline and the results-viewing system.
"""

import random
import time

import pandas as pd

# Enzyme IDs used to populate the demo DataFrame.
_ENZYME_PREFIXES = ["ENZ", "MUT", "WT", "VAR"]


def _generate_enzyme_dataframe(n_rows: int = 20) -> pd.DataFrame:
    """Create a random DataFrame of simulated enzyme assay results.

    Args:
        n_rows: Number of rows to generate.

    Returns:
        A ``pd.DataFrame`` with columns: enzyme_id, activity_U_mg,
        stability_Tm_C, temperature_C, yield_pct.
    """
    data = {
        "enzyme_id": [f"{random.choice(_ENZYME_PREFIXES)}-{i:03d}" for i in range(1, n_rows + 1)],
        "activity_U_mg": [round(random.uniform(0.5, 150.0), 2) for _ in range(n_rows)],
        "stability_Tm_C": [round(random.uniform(35.0, 85.0), 1) for _ in range(n_rows)],
        "temperature_C": [random.randint(20, 80) for _ in range(n_rows)],
        "yield_pct": [round(random.uniform(5.0, 98.0), 1) for _ in range(n_rows)],
    }
    return pd.DataFrame(data)


def run(params: dict) -> dict:
    """Sleep for the specified number of seconds, then return a random DataFrame.

    Args:
        params: Dictionary with key ``"seconds"`` (int) indicating how
            long the task should run.

    Returns:
        A JSON-serializable dict with timing metadata and a ``"dataframe"``
        key containing ``{"columns": [...], "data": [...]}``.
    """
    seconds = int(params["seconds"])
    start = time.monotonic()
    time.sleep(seconds)
    elapsed = time.monotonic() - start

    df = _generate_enzyme_dataframe(n_rows=20)

    return {
        # this _meta data will be at the top of the job results page
        "_meta": [
            {"label": "Timer Set to", "value": f"{seconds}s"},
            {"label": "Actual Elapsed", "value": f"{round(elapsed, 3)}s"},
        ],
        "requested_seconds": seconds,
        "actual_elapsed": round(elapsed, 3),
        "status": "completed",
        "dataframe": {
            "columns": df.columns.tolist(),
            "data": df.to_dict(orient="records"),
        },
    }
