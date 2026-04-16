# AG Grid Table Agent

**Trigger:** When creating, modifying, or adding columns to an AG Grid results table (e.g., `results.py`).

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

### 2.4 — Column ordering convention

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
    "paginationPageSizeSelector": [10, 20, 50, 100],
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
**Verify Agent** core steps defined in [`.github/agents/verify.md`](verify.md)
(`tox run -e format` then `tox`). Fix any failures before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
