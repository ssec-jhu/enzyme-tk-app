---
name: create-ag-grid
description: Use PROACTIVELY when creating, modifying, or adding columns to an AG Grid results table (e.g. results.py) in the EnzymeTK app.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# AG Grid Table Agent

This agent defines the rules for building AG Grid tables in the app. All grids use the **Balham** theme (`ag-theme-balham`) and are constructed via the shared `build_ag_grid()` helper. The CSS overrides in `09-ag-grid.css` map the grid surfaces to the app's design tokens from `00-variables.css`.

---

## 1. Architecture Overview

| File | Responsibility |
|---|---|
| `components/results_helpers.py` | `shared_col_defs()` (shared columns), `build_ag_grid()` (grid factory) |
| `tools/<tool>/results.py` | Tool-specific column defs + `results_layout()` |
| `assets/09-ag-grid.css` | Theme overrides (header, rows, icons, pagination) |
| `assets/dashAgGridComponentFunctions.js` | Custom cell renderers (`SvgRenderer`, etc.) |

### How it fits together

```
tool results.py
  └─ _get_column_defs()          # tool-specific cols + shared_col_defs()
  └─ results_layout(job)         # calls build_ag_grid(col_defs, df_payload)
       └─ build_ag_grid()        # filters cols, sets tooltips, returns dag.AgGrid
            └─ defaultColDef      # global defaults (sort, filter, resize)
            └─ 09-ag-grid.css    # visual theme
```

---

## 2. Column Definition Rules

### 2.1 — Standard (text / numeric) columns

Use a **fixed row height** (Balham default ~28px). Do **not** set `autoHeight` or `wrapText`. Long content is truncated and accessible via hover tooltip (automatically set by `build_ag_grid()`).

```python
{"field": "database", "width": 120},
{"field": "TanimotoSimilarity", "width": 100, "filter": "agNumberColumnFilter"},
```

### 2.2 — SVG / image columns

Image columns **must** set `autoHeight: True` so the row expands to fit the image. Also set `filter: False` and `sortable: False` — images are not filterable or sortable.

```python
{
    "field": "reaction_svg",
    "cellRenderer": "SvgRenderer",
    "width": 450,
    "autoHeight": True,
    "filter": False,
    "sortable": False,
},
```

The `SvgRenderer` is defined in `dashAgGridComponentFunctions.js`. It:
- Renders a base64 `data:image/svg+xml;base64,...` URI as an `<img>` thumbnail (max-height 150px).
- Wraps it in a flex container for vertical centering.
- Opens a full-screen overlay on click (uses `.svg-overlay` CSS).

### 2.3 — Long text that must wrap (multi-line)

Only use `autoHeight: True` on columns where seeing the full text inline is essential (e.g., `unmapped` reaction SMILES). Pair it with a `cellClass` that enables wrapping:

```python
{
    "field": "unmapped",
    "width": 350,
    "cellClass": "cell-wrap-dash-ag-grid",
    "autoHeight": True,
},
```

The `cell-wrap-dash-ag-grid` CSS class is defined in `09-ag-grid.css`:
```css
.cell-wrap-dash-ag-grid {
    word-break: normal !important;
    white-space: normal !important;
    line-height: 120% !important;
    font-size: 10px !important;
}
```

Note the `font-size: 10px` — this class is tuned for dense chemical strings (SMILES), **not** for prose or biological sequences. Do not reach for it just because a column is long; see 2.4.

### 2.4 — Protein / amino-acid sequence columns

Sequence columns are **never** hand-styled. Always use the shared helper so every tool renders sequences identically:

```python
from enzyme_tk_app.app.components.results_helpers import sequence_col_def

sequence_col_def(col.COL_SEQUENCE)              # default width 300
sequence_col_def("Sequence", width=400)         # or override
sequence_col_def("Sequence", header="Target Sequence")
```

It applies the `ag-cell-sequence` class (`09-ag-grid.css`): monospace, `0.8rem`, single line with an ellipsis. Sequences run to hundreds of residues, so they are truncated rather than wrapped — this keeps row heights uniform, and `build_ag_grid()` already sets a `tooltipField` so the full sequence appears on hover (and stays selectable via `enableCellTextSelection`).

Do **not**:
- inline a `cellStyle` dict with `fontSize` / `whiteSpace` / `textOverflow` — that is what this helper replaced;
- use `cell-wrap-dash-ag-grid` on a sequence — its `font-size: 10px !important` is too small to read;
- set `autoHeight: True` on a sequence column — one long protein will blow up the row height for the whole table.

If a genuinely new kind of long-text column appears, add a class + helper rather than styling it at the call site.

### 2.5 — Numeric columns

Use the shared helper rather than hand-writing the filter and formatter:

```python
from enzyme_tk_app.app.components.results_helpers import numeric_col_def

numeric_col_def("alnlen", "Alignment Length", width=150)              # integer — no formatter
numeric_col_def("fident", "Frac. Identity", width=140, decimals=4)    # fraction  -> 0.8734
numeric_col_def("bits", "Bit Score", width=120, decimals=1)           # score     -> 445.0
numeric_col_def("evalue", "E-value", width=120, exponential=True)     # e-value   -> 3.09e-163
```

It always sets `agNumberColumnFilter`; formatting is **opt-in** because the app renders three distinct kinds of number and one rule does not fit them:

| Kind | Example values | Setting |
|---|---|---|
| Integers — counts, positions, lengths, masses | `269`, `10856` | **omit `decimals`** — formatting renders `269` as `269.0000` |
| Fractions | `0.1666666666666666` | `decimals=4` |
| Percentages | `100`, `87.5` | `decimals=2` — 4 dp is noise on a percentage |
| E-values | `3.09e-163` | `exponential=True` |

Pick the treatment from the **data**, not by habit: check the actual value range before choosing. `Polarity` is a fraction (needs 4 dp) while `temperature` next to it is a whole number 4–99 (needs none), and diamond's identity column is a percentage, not a fraction.

Do **not** inline `{"function": "params.value != null ? params.value.toFixed(N) : ''"}` at a call site — that string existed in two files before this helper and drifted.

### 2.6 — Header labels (`headerName`) — optional, and Func-E opts out

`headerName` is **optional**. Omit it and AG Grid humanises the field
(`camelCaseToHumanText`); the `header=` argument of `numeric_col_def` /
`sequence_col_def` just sets it. Most tools pass a friendly label
(`"Alignment Length"`, `"Frac. Identity"`) — keep doing that for new tools.

**`tools/funce/results.py` is a deliberate exception**: `_get_column_defs()` ends with
`[d | {"headerName": d["field"]} for d in defs]`, so every Func-E header is the raw
enzymetk column name (`Funce_prediction`, `Funce_substrates_MolWt_mean`, `database`).
Two reasons: a scientist must be able to trace a number back to the exact enzymetk
column, and AG Grid's humanisation *misreports* these names
(`Funce_substrates_MolWt_mean` → "Funce_substrates Mol Wt_mean").
Do not "fix" those headers, do not propagate the pattern to other tools, and keep the
guard tests in `enzyme_tk_app/app/tests/test_tools_funce.py` if you touch that function.

### 2.7 — Column ordering convention

Tool-specific columns come **first**, then append `shared_col_defs()`:

```python
def _get_column_defs():
    return [
        # tool-specific columns (SVG, SMILES, etc.)
        {...},
    ] + shared_col_defs()
```

---

## 3. `defaultColDef` — Global Defaults

The `build_ag_grid()` function sets these defaults. **Do not duplicate or override** them in individual column defs unless intentionally overriding a specific property:

```python
defaultColDef={
    "resizable": True,
    "sortable": True,
    "filter": True,
    "wrapHeaderText": True,
    "autoHeaderHeight": True,
    "filterParams": {
        "buttons": ["reset", "apply"],
        "closeOnApply": True,
    },
    "cellStyle": {"lineHeight": "1.4"},
},
```

Key points:
- **No global `autoHeight`** — only individual columns that need it (SVG, long-wrap text) should set `autoHeight: True`.
- **No global `wrapText`** — columns that don't explicitly need wrapping will truncate with an ellipsis; the tooltip shows the full value.
- `cellStyle: {"lineHeight": "1.4"}` — provides comfortable vertical spacing in fixed-height rows.

---

## 4. CSS Theme Rules (`09-ag-grid.css`)

All visual theming is done via CSS targeting `.ag-theme-balham`. **Never hardcode colours** — always use CSS variables from `00-variables.css`.

### 4.1 — Header

| Rule | Purpose |
|---|---|
| `.ag-header` | Navy background (`--primary-color`), dark bottom border (`--primary-dark`) |
| `.ag-header-cell` | White text, `font-weight: 600` |
| `.ag-header-cell:hover` | Lighter navy on hover (`--secondary-color`) |
| `.ag-header-icon .ag-icon` | White icons (sort, menu) |
| `.ag-sort-indicator-icon .ag-icon` | White sort arrows |
| `.ag-header-cell-menu-button .ag-icon` | White filter menu button |
| `.ag-header-cell-filtered .ag-icon` | **Amber** (`--accent-color`) when a filter is active |
| `.ag-header-cell-sorted-asc/desc` | Darker navy background (`--primary-dark`) on sorted columns |

### 4.2 — Rows

| Rule | Purpose |
|---|---|
| `.ag-row-odd` | Striped background (`--bg-body`) |
| `.ag-row-even` | White background (`--bg-surface`) |
| `.ag-row-hover` | Light blue tint (10% `--secondary-color` mixed with white) |
| `.ag-row-selected` | Slightly stronger blue tint (15%) |

### 4.3 — Cell alignment

| Rule | Purpose |
|---|---|
| `.ag-cell-wrapper { align-items: center }` | Vertically centers cell content in variable-height rows |

Text is **left-aligned** by default (no `text-align: center` globally). If a specific column needs centering, set it via `cellStyle` in the column def.

### 4.4 — Pagination

| Rule | Purpose |
|---|---|
| `.ag-paging-panel` | Secondary text colour, top border matches `--border-color` |

---

## 5. `dashGridOptions` Defaults

Set by `build_ag_grid()`:

```python
dashGridOptions={
    "pagination": True,
    "paginationPageSize": 20,
    "paginationPageSizeSelector": True,
    "domLayout": "autoHeight",
    "enableCellTextSelection": True,
    "ensureDomOrder": True,
},
```

- `domLayout: "autoHeight"` — the grid's outer container grows to fit all visible rows (no internal scroll).
- `enableCellTextSelection` + `ensureDomOrder` — lets users select and copy cell text.

---

## 6. Adding a New SVG / Image Renderer

1. Define the renderer function in `dashAgGridComponentFunctions.js` on `dagcomponentfuncs`.
2. The cell value must be a data URI string (`data:image/svg+xml;base64,...`).
3. Use the `_openSvgOverlay(src)` helper for click-to-enlarge behaviour.
4. In the column def, set `"cellRenderer": "YourRendererName"`, `"autoHeight": True`, `"filter": False`, `"sortable": False`.

---

## 7. Performance Notes

- **`autoHeight`** forces AG Grid to measure every cell to compute row heights. Only enable it on columns that truly need it (images, multi-line wrap).
- For tables with > 500 rows, consider whether `autoHeight` on any column is justified — fixed row heights are significantly faster.
- `domLayout: "autoHeight"` means pagination controls the visible set; the grid doesn't virtualise rows beyond the page.

---

## 8. Quick Reference — Column Def Cheat Sheet

| Column type | `autoHeight` | `wrapText` | `cellClass` / `cellStyle` | `cellRenderer` | `filter` |
|---|---|---|---|---|---|
| Short text / ID | — | — | — | — | `True` (default) |
| Number | — | — | — | — | `"agNumberColumnFilter"` |
| SVG image | `True` | — | — | `"SvgRenderer"` | `False` |
| Long text (truncate) | — | — | — | — | `True` (default) |
| Long text (must wrap) | `True` | — | `"cell-wrap-dash-ag-grid"` | — | `True` (default) |

---

## MANDATORY AFTER-CREATION WORKFLOW

After creating or modifying AG Grid table code, you **MUST** execute the
**`verify` subagent's** core steps (`tox run -e format` then `tox`). Fix any
failures before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
