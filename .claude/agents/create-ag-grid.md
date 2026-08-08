---
name: create-ag-grid
description: Use PROACTIVELY when creating, modifying, or adding columns to an AG Grid results table (e.g. results.py) in the EnzymeTK app, or when changing its shared CSV-export toolbar.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# AG Grid Table Agent

This agent defines the rules for building AG Grid tables in the app. All grids use the **Balham** theme (`ag-theme-balham`) and are constructed via the shared `build_ag_grid()` helper. The CSS overrides in `09-ag-grid.css` map the grid surfaces to the app's design tokens from `00-variables.css`.

---

## 1. Architecture Overview

| File | Responsibility |
|---|---|
| `components/results_helpers.py` | `shared_col_defs()` (shared columns), `build_ag_grid()` (grid factory), `_build_export_toolbar()` + `download_results_csv` (CSV export) |
| `tools/<tool>/results.py` | Tool-specific column defs + `results_layout()` |
| `assets/09-ag-grid.css` | Theme overrides (header, rows, icons, pagination) |
| `assets/08-jobs.css` | `.btn-toolbar` (download button) and `.jobs-toolbar-radios` (export-scope radios) |
| `assets/dashAgGridComponentFunctions.js` | Custom cell renderers (`SvgRenderer`, etc.) |

### How it fits together

```
tool results.py
  └─ _get_column_defs()          # tool-specific cols + shared_col_defs()
  └─ results_layout(job)         # calls build_ag_grid(col_defs, df_payload)
       └─ build_ag_grid()        # filters cols, sets tooltips, returns html.Div
            ├─ _build_export_toolbar()      # Download CSV button + scope radios
            └─ dag.AgGrid(id=GRID_ID)
                 └─ defaultColDef           # global defaults (sort, filter, resize)
                 └─ 09-ag-grid.css          # visual theme
```

### 1.1 — What `build_ag_grid()` returns

**`build_ag_grid(column_defs, df_payload)` returns an `html.Div`, not a `dag.AgGrid`** — the
Div wraps the shared CSV-export toolbar and the grid. The signature is unchanged, so a
`results.py` that does `results_table = build_ag_grid(column_defs, df_payload)` needs no
edit; just do not annotate or assert the return as `dag.AgGrid`.

Every tool therefore gets the download control for free. **Never add a per-tool export
button, `csvExportParams`, or `dcc.Download`** to a `results.py` — put the change in
`build_ag_grid()` so all tools move together.

| Piece | Detail |
|---|---|
| Grid id | `GRID_ID = "id-grid-results"` — set by `build_ag_grid()`, static |
| Toolbar | `STYLE_RESULTS_TOOLBAR` flex row: `html.Button` (`className="btn-toolbar"`, `ICON_RESULTS_DOWNLOAD`, "Download CSV") on the left, inline `dbc.RadioItems` (`className="jobs-toolbar-radios"`) beside it |
| Scopes | `SCOPE_FILTERED` ("Filtered", the default) → `exportedRows: "filteredAndSorted"`; `SCOPE_ALL` ("Unfiltered") → `exportedRows: "all"`. Each radio label is an `html.Span` with a native `title` tooltip |
| File name | `enzymetk-<job_id[:6]>-<scope>.csv`, from `_csv_export_params()` — the same 6-char prefix the My Tasks table shows |
| Job id source | `State(JOB_ID_SPAN_ID, "title")` — `my_tasks_view_results._build_job_info_header()` puts `id=JOB_ID_SPAN_ID` on the task-id span whose `title` is the bare job id. **A page↔component contract**: renaming or dropping that `title` breaks the download filename (guarded by a test in `test_my_tasks.py`) |

**One results grid per page.** `GRID_ID` and the toolbar ids are static because
`my_tasks_view_results` renders exactly one tool's `results_layout()`. Do not call
`build_ag_grid()` twice on one page. If a page ever needs two grids, the upgrade path is:
give `build_ag_grid()` an `id` argument and move `download_results_csv` to `MATCH`
pattern-matching ids.

**SVG columns are excluded from the export.** `_csv_export_params()` builds `columnKeys`
from every column def with a `field` **except** those whose def has
`cellRenderer == "SvgRenderer"` — each of those cells holds a ~20 KB base64 data URI that
would bloat the CSV into uselessness. The SMILES the picture was drawn from is exported
instead, so the images stay reproducible. See §2.2 and §6.

---

## 2. Column Definition Rules

### 2.1 — Standard (text / numeric) columns

Use a **fixed row height** (Balham default ~28px). Do **not** set `autoHeight` or `wrapText`. Long content is truncated and accessible via hover tooltip (automatically set by `build_ag_grid()`).

```python
column_defs = [
    {"field": "database", "width": 120},
    {"field": "TanimotoSimilarity", "width": 100, "filter": "agNumberColumnFilter"},
]
```

**Give every column a `width`; leave `minWidth` and `flex` alone.** `build_ag_grid()` copies
each `width` into `minWidth` and sets `columnSize="responsiveSizeToFit"`, so the columns
share out whatever width a short table leaves over and the table ends flush with the page
instead of against a grey gutter. Because every column is already at its floor, a table
wider than the page cannot shrink — it keeps its widths and scrolls, unchanged. Read
`width` as "at least this wide". A column that must never grow needs an explicit
`maxWidth`; one that may go narrower than its start needs an explicit `minWidth`.

How wide a table ends up is decided by the *data*, not by this list — §1 drops any def
whose field the payload lacks, so Reaction Similarity declares 32 defs and renders the 7
`ReactionDist` actually returns (1340px, well inside the page).

**Do not reach for `flex`.** It is the obvious way to do this and it does not work:
dash-ag-grid 35.3.0 records `flex` in the column state and never applies it, leaving the
column at its `minWidth` while `getHorizontalPixelRange()` reports the space it should
have taken.

### 2.2 — SVG / image columns

Image columns **must** set `autoHeight: True` so the row expands to fit the image. Also set `filter: False` and `sortable: False` — images are not filterable or sortable.

```python
column_defs = [
    {
        "field": "reaction_svg",
        "cellRenderer": "SvgRenderer",
        # Captions this row's structure in the compare lightbox.
        "cellRendererParams": {"smilesField": "unmapped"},
        "width": 450,
        "autoHeight": True,
        "filter": False,
        "sortable": False,
    },
]
```

The `SvgRenderer` is defined in `dashAgGridComponentFunctions.js`. It:
- Renders a base64 `data:image/svg+xml;base64,...` URI as an `<img>` thumbnail (max-height 150px).
- Wraps it in a flex container for vertical centering.
- Opens a **compare lightbox** on click (`.svg-overlay` + `.svg-compare*` CSS): the job's query
  structure and this row's, each labelled and captioned with its SMILES — side by side for a
  compact structure, stacked query-over-result for a wide one (see below). Closes on backdrop
  click, the `×` or Escape — but **not** on a click inside the panels, so the SMILES stay
  selectable.

The query panel is **read out of the page**, not plumbed through `columnDefs`:
`_openSvgOverlay` does `querySelector("img.jobs-params-preview")` and reads the SMILES off
that image's `data-smiles` attribute. Both anchors are `QUERY_PREVIEW_CLASS` /
`QUERY_SMILES_ATTR` in `components/results_helpers.py`, written by `_render_smiles_preview()`
and pinned from both sides by `test_query_preview_anchors_match_the_compare_lightbox` in
`tests/test_smiles_rendering.py` — rename either and the JS must change in the same edit.
**A new tool needs no wiring for this**: any tool storing a `smiles` param already gets the
query image, so the query panel appears for free. A tool with no query image degrades to the
old single-image lightbox.

**Orientation follows the structure's shape, not the viewport.** `_stackWideImages()` measures
each panel's `naturalWidth / naturalHeight` and adds `.svg-compare-stacked` when one exceeds
`_STACK_ASPECT_RATIO = 2.5`; stacked panels are capped at `88vw` instead of `46vw`, which is
what makes a reaction legible (644 px wide side by side, 1232 px stacked at 1400x900) while
molecules keep the two-column layout. A `data:` URI has no `naturalWidth` until it decodes, so
the measurement also re-runs on each image's `load`. The constant sits in the gap between the
only two canvases this app draws — molecules 500x300 (**1.67**), the narrowest real reaction
750x200 (**3.75**, from `max(400, n_templates * 250)` x 200) — so **it is only correct while
reactions are drawn 200 px high**: a taller reaction canvas drops a one-reactant/one-product
reaction below 2.5 and it silently stops stacking.
`test_stack_threshold_separates_reactions_from_molecules` in `tests/test_smiles_rendering.py`
reads the constant out of the JS and re-renders both canvases, so change a canvas size and
move the constant in the same edit. Below 768 px the `@media` block in `09-ag-grid.css` still
stacks everything — the JS never adds the class for a 1.67 molecule, so that case stays CSS's.

`cellRendererParams.smilesField` names the row column holding this structure's SMILES —
`props.data` is the full row, so that column need not be one of the grid's visible columns.
Omit it and only the caption is lost.

`cellRenderer: "SvgRenderer"` also **drives CSV-export exclusion** — `_csv_export_params()`
drops any column carrying that exact renderer name from `columnKeys`, keeping ~20 KB of
base64 per cell out of the download. Set it on every image column, and keep a text column
with the source SMILES in the grid so the picture stays reproducible from the CSV.

### 2.3 — Long text that must wrap (multi-line)

Only use `autoHeight: True` on columns where seeing the full text inline is essential (e.g., `unmapped` reaction SMILES). Pair it with a `cellClass` that enables wrapping:

```python
column_defs = [
    {
        "field": "unmapped",
        "width": 350,
        "cellClass": "cell-wrap-dash-ag-grid",
        "autoHeight": True,
    },
]
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

sequence_col_def(col.COL_SEQUENCE)  # default width 300
sequence_col_def("Sequence", width=400)  # or override
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

numeric_col_def("alnlen", "Alignment Length", width=150)  # integer — no formatter
numeric_col_def("fident", "Frac. Identity", width=140, decimals=4)  # fraction  -> 0.8734
numeric_col_def("bits", "Bit Score", width=120, decimals=1)  # score     -> 445.0
numeric_col_def("evalue", "E-value", width=120, exponential=True)  # e-value   -> 3.09e-163
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

### 2.6 — Write every column out in full

`_get_column_defs()` is the **one place a developer can see what the table contains**. Give every column its own visible line with its field name spelled out literally. Group them with banner comments (`# ── Identity ───`, `# ── BLAST score columns ───`) — see `tools/sequence_similarity/results.py` for the reference shape.

**Never synthesise a field name.** No loop, comprehension, or f-string that builds `field` from some other list:

```python
# WRONG — 26 columns invisible at the call site, and PREDICTED_FEATURES is a
# hand-copy of a library constant that will drift from the actual data.
for feature in PREDICTED_FEATURES:
    defs.append(numeric_col_def(f"{PREFIX}_{feature}_mean", decimals=4))

# RIGHT — one line per column, name as it arrives in the dataframe.
defs = [
    numeric_col_def("Funce_substrates_MolWt_mean", decimals=4),
    numeric_col_def("Funce_substrates_MolWt_std", decimals=4),
]
```

A generated name hides the column *and* silently drops it: `build_ag_grid()` renders only fields that have a def, so a column the generating list fails to name never appears — no error, no log. Repetition here is the feature; it is what makes the drift visible in review.

This is a rule about generating **names**, not about sharing **rules**. Reuse is still expected everywhere it applies: `numeric_col_def`, `sequence_col_def`, `shared_col_defs()`, `col.COL_*` constants from `utils/columns.py`, and a shared `cellClass` for a recurring column type. Factor out styling and behaviour; spell out identity.

Use `col.COL_*` for any column shared across tools (`col.COL_ENTRY`, `col.COL_DATABASE`, `col.COL_SEQUENCE`). Use a bare literal only when the name is one specific library's output contract — Func-E's `Funce_*` columns are named by `enzymetk`, not by this app, so writing them literally is what keeps them traceable.

A module constant holding **one** whole column name is fine and is not synthesis — `funce/results.py` uses `PRED_COL` (`"Funce_prediction"`, imported from `compute.py`) because `compute.py` sorts on the same column and the two must not drift. The line still names exactly one column. What §2.6 forbids is a constant that a loop expands into *many* names.

**When the payload can carry columns nobody can list up front, append the remainder — never loop over a guessed list.** `_get_column_defs()` is then the *styled* layer (widths, decimals, the sequence truncation class), and `results_layout()` adds a bare def for every payload column it does not name:

```python
defs = _get_column_defs()
known = {d["field"] for d in defs}
defs += [{"field": c, "headerName": c} for c in df_payload["columns"] if c not in known]
```

This is not synthesis: no name is invented, they are read off the payload — so an unexpected column is unstyled but never invisible. Two tools need it and both do it identically. `tools/funce/results.py`: a newer `enzymetk` may emit new `Funce_*` columns. `tools/sequence_similarity/results.py`: a sequence database only has to carry `Entry`, `Sequence` and `EC number` (`create-tool` §3b.9), every other column is metadata this app never enumerates, and a real `enzymes.tsv` search brings 17 of them (`Organism`, `Protein names`, `Catalytic activity`, `Cofactor`, …). Curated defs lead, the appended tail comes last; if you extend the curated list, leave the append in place.

### 2.7 — Header labels (`headerName`) — optional, and Func-E opts out

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

The bare `{"field": c, "headerName": c}` its `results_layout()` appends for unnamed payload
columns is the §2.6 remainder pattern, not part of this exception — `sequence_similarity`
appends the same defs while keeping friendly headers on its curated ones.

Do not "fix" those headers, do not propagate the pattern to other tools, and keep the
guard tests in `enzyme_tk_app/app/tests/test_tools_funce.py` if you touch that function.

### 2.8 — Column ordering convention

Tool-specific columns come **first**, then append `shared_col_defs()`:

```python
def _get_column_defs():
    return [
        # tool-specific columns (SVG, SMILES, etc.)
        {...},
    ] + shared_col_defs()
```

**Omit `shared_col_defs()` when the payload provably carries none of those fields.**
`build_ag_grid()` drops every def whose field is absent from `df_payload["columns"]`, so
appending it to a table of unrelated columns is ~35 lines of guaranteed no-op.
`tools/timer_tool_template/results.py` is the one such case: its demo dataframe
(`sample_id`, `activity_score`, `stability_score`, `temperature_c`, `yield_pct`) shares no
column with the science tools, and it is the file new tools are copied from, so the noise
would propagate. Say so in a comment at the call site. This is a narrow exception — any tool
whose payload *might* carry a shared column still appends it.

---

## 3. `defaultColDef` — Global Defaults

The `build_ag_grid()` function sets these defaults. **Do not duplicate or override** them in individual column defs unless intentionally overriding a specific property:

```python
dag.AgGrid(
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
)
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
dag.AgGrid(
    dashGridOptions={
        "pagination": True,
        "paginationPageSize": 20,
        "paginationPageSizeSelector": True,
        "domLayout": "autoHeight",
        "enableCellTextSelection": True,
        "ensureDomOrder": True,
    },
)
```

- `domLayout: "autoHeight"` — the grid's outer container grows to fit all visible rows (no internal scroll).
- `enableCellTextSelection` + `ensureDomOrder` — lets users select and copy cell text.

---

## 6. Adding a New SVG / Image Renderer

1. Define the renderer function in `dashAgGridComponentFunctions.js` on `dagcomponentfuncs`.
2. The cell value must be a data URI string (`data:image/svg+xml;base64,...`).
3. Use the `_openSvgOverlay(src, smiles)` helper for the compare lightbox. Pass the row's
   SMILES as the second argument (read it from `props.data[props.smilesField]`) so the panel
   is captioned; `""` renders the image with no caption. Going through the helper also gets
   the aspect-ratio stacking for free — but if your renderer draws a canvas shaped like
   neither of the current two, check it against `_STACK_ASPECT_RATIO` (§2.2) before assuming
   the layout it lands in is the right one.
4. In the column def, set `"cellRenderer": "YourRendererName"`, `"autoHeight": True`, `"filter": False`, `"sortable": False`.
5. **Prefer reusing `SvgRenderer` over naming a new renderer.** The CSV-export exclusion in
   `_csv_export_params()` matches the literal string `"SvgRenderer"`, so a column using
   `"MyStructureRenderer"` would export its base64 data URIs. If a genuinely different
   renderer is needed, widen that check in `results_helpers._csv_export_params()` in the
   same change (e.g. a set of image renderer names) — do not leave it keyed on one name.

---

## 7. Performance Notes

- **`autoHeight`** forces AG Grid to measure every cell to compute row heights. Only enable it on columns that truly need it (images, multi-line wrap).
- For tables with > 500 rows, consider whether `autoHeight` on any column is justified — fixed row heights are significantly faster.
- `domLayout: "autoHeight"` means pagination controls the visible set; the grid doesn't virtualise rows beyond the page.

---

## 8. Quick Reference — Column Def Cheat Sheet

| Column type | `autoHeight` | `wrapText` | `cellClass` / `cellStyle` | `cellRenderer` | `filter` | In CSV export |
|---|---|---|---|---|---|---|
| Short text / ID | — | — | — | — | `True` (default) | yes |
| Number | — | — | — | — | `"agNumberColumnFilter"` | yes |
| SVG image | `True` | — | — | `"SvgRenderer"` | `False` | **no** (§1.1) |
| Long text (truncate) | — | — | — | — | `True` (default) | yes |
| Long text (must wrap) | `True` | — | `"cell-wrap-dash-ag-grid"` | — | `True` (default) | yes |

---

## MANDATORY AFTER-CREATION WORKFLOW

After creating or modifying AG Grid table code, you **MUST** execute the
**`verify` subagent's** core steps (`tox run -e format` then `tox`). Fix any
failures before concluding.

*Do not rely on the user to run these commands.*
*Do not just summarize what to do.*
*You must execute them yourself, wait for the results, and fix any failures
before concluding your task.*
