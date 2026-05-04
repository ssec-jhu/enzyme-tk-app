"""Modal layout for the Sequence & Structure-Based Similarity tool.

This modal appears when the user clicks the Launch button on the
Sequence and Structure-Based Similarity tool card.  It collects
inputs needed to run a FoldSeek-based similarity search.

Layout rules (see ``.github/agents/create-modal.md``)
------------------------------------------------------
1. Top-level: ``dbc.Modal(size="lg", centered=True)``.
2. ``dbc.ModalBody`` gets ``className="p-4"``.
3. Each logical section is wrapped in
   ``html.Div(className="bg-light p-3 rounded mb-3")``.
4. Shared helpers from ``modal_helpers`` handle all repeated
   boilerplate — header, section headers, footer, and results
   placeholder.
5. Inputs use ``dbc.Row`` / ``dbc.Col`` for label / control alignment.
6. All interactive controls get ``className="... themed-control"`` for
   dark-mode-aware styling.

Key conventions
---------------
- All component IDs are f-strings of ``TOOL_DEF["slug"]`` — never
  hardcode the slug string.
- The modal ID **must** be ``f"id-modal-{TOOL_DEF['slug']}"``.
- Use ``dcc.Dropdown`` (not ``dbc.Select``) for dropdowns.
- Use ``themed-control`` on every form control.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from enzyme_tk_app.app.components.icons import ICON_MODAL_EXAMPLE, ICON_MODAL_UPLOAD
from enzyme_tk_app.app.components.modal_helpers import (
    create_modal_config_section_header,
    create_modal_footer,
    create_modal_header,
    create_modal_input_section_header,
    create_modal_submission_results,
)
from enzyme_tk_app.app.tools.sequence_structure_similarity import TOOL_DEF
from enzyme_tk_app.app.utils.data_loading import get_foldseek_database_options


def get_example_entries():
    """Return example entries for the FoldSeek similarity search.

    Each entry has an ``id`` (used as dropdown value), a display
    ``label``, the protein ``sequence``, and an optional
    ``structure_file`` name (relative to ``data/structures/``).

    Returns:
        List of dicts with keys: id, label, sequence, structure_file.
    """
    return [
        {
            "id": "A0A009IHW8-seq",
            "label": "A0A009IHW8 — DNA glycosylase (sequence only)",
            "sequence": (
                "MSLEQKKGADIISKILQIQNSIGKTTSPSTLKTKLSEISRKEQENARI"
                "QSKLSDLQKKKIDIDNKLLKEKQNLIKEEILERKKLEVLTKKQQKDEIEHQKKLKREIDAIKASTQYITDVSI"
                "SSYNNTIPETEPEYDLFISHASEDKEDFVRPLAETLQQLGVNVWYDEFTLKVGDSLRQKIDSGLRNSKYGTVV"
                "LSTDFIKKDWTNYELDGLVAREMNGHKMILPIWHKITKNDVLDYSPNLADKVALNTSVNSIEEIAHQLADVILNR"
            ),
            "structure_file": None,
        },
        {
            "id": "A0A009IHW8-struct",
            "label": "A0A009IHW8 — DNA glycosylase (sequence + structure)",
            "sequence": (
                "MSLEQKKGADIISKILQIQNSIGKTTSPSTLKTKLSEISRKEQENARI"
                "QSKLSDLQKKKIDIDNKLLKEKQNLIKEEILERKKLEVLTKKQQKDEIEHQKKLKREIDAIKASTQYITDVSI"
                "SSYNNTIPETEPEYDLFISHASEDKEDFVRPLAETLQQLGVNVWYDEFTLKVGDSLRQKIDSGLRNSKYGTVV"
                "LSTDFIKKDWTNYELDGLVAREMNGHKMILPIWHKITKNDVLDYSPNLADKVALNTSVNSIEEIAHQLADVILNR"
            ),
            "structure_file": "A0A009IHW8-chai.cif",
        },
        {
            "id": "A0A067CMC7-seq",
            "label": "A0A067CMC7 — Nuclease (sequence only)",
            "sequence": (
                "MLEVPVWIPILAFAVGLGLGLLIPHLQKPFQRFSTVNDIPKEFFEHERTLRGKVVS"
                "VTDGDTIRVRHVPWLANGDGDFKGKLTETTLQLRVAGVDCPETAKFGRTGQPFGEE"
                "AKAWLKGELQDQVVSFKLLMKDQYSRAVCLVYYGSWAAPMNVSEELLRHGYANIYR"
                "QSGAVYGGLLETFEALEAEAREKRVNIWSLDKRETPAQYKARK"
            ),
            "structure_file": None,
        },
        {
            "id": "1AKI-struct",
            "label": "1AKI — Lysozyme (sequence + structure)",
            "sequence": (
                "KVFGRCELAAAMKRHGLDNYRGYSLGNWVCAAKFESNFNTQATNRNTDGSTDYGILQINS"
                "RWWCNDGRTPGSRNLCNIPCSALLSSDITASVNCAKKIVSDGNGMNAWVAWRNRCKGTDVQ"
                "AWIRGCRL"
            ),
            "structure_file": "1AKI.cif",
        },
    ]


def modal():
    """Build the Sequence & Structure-Based Similarity modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Task name
        - Protein sequence (textarea)
        - Structure file upload (optional CIF/PDB)
        - Database selection (multi-select)
    """
    db_options = get_foldseek_database_options()
    # Default to all available databases.
    default_dbs = [opt["value"] for opt in db_options]

    return dbc.Modal(
        id=f"id-modal-{TOOL_DEF['slug']}",
        is_open=False,
        size="lg",
        centered=True,
        children=[
            # ── Header ───────────────────────────────────────────────
            create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"]),
            # ── Body ─────────────────────────────────────────────────
            dbc.ModalBody(
                className="p-4",
                children=[
                    # ── Section 1: Input Data ────────────────────────
                    html.Div(
                        className="bg-light p-3 rounded mb-3",
                        children=[
                            create_modal_input_section_header(),
                            # Task Name
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Task Name", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.Input(
                                            id=f"id-input-{TOOL_DEF['slug']}-task-name",
                                            type="text",
                                            placeholder="e.g. 'Lysozyme FoldSeek search'",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Protein Sequence
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Sequence", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Textarea(
                                                id=f"id-textarea-{TOOL_DEF['slug']}-sequence",
                                                placeholder=(
                                                    "Paste a protein amino-acid sequence "
                                                    "(e.g. KVFGRCELAAAMKRHGLDNYR...)"
                                                ),
                                                rows=4,
                                                className="themed-control",
                                                style={"fontFamily": "monospace", "fontSize": "0.9rem"},
                                            ),
                                            html.Div(
                                                className="mt-1",
                                                children=[
                                                    html.Small(
                                                        children=[
                                                            html.I(
                                                                className=ICON_MODAL_EXAMPLE,
                                                                style={
                                                                    "marginRight": "0.25rem",
                                                                    "color": "var(--accent-color)",
                                                                },
                                                            ),
                                                            "Try an example:",
                                                        ],
                                                        style={"color": "var(--text-tertiary)"},
                                                    ),
                                                    dcc.Dropdown(
                                                        id=f"id-dropdown-{TOOL_DEF['slug']}-example",
                                                        options=[
                                                            {"label": ex["label"], "value": ex["id"]}
                                                            for ex in get_example_entries()
                                                        ],
                                                        placeholder="Select an example sequence...",
                                                        className="mt-1 themed-control",
                                                        searchable=False,
                                                    ),
                                                ],
                                            ),
                                        ],
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                            ),
                            # Structure File Upload (optional)
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Structure File", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        [
                                            dcc.Upload(
                                                id=f"id-upload-{TOOL_DEF['slug']}-structure",
                                                children=html.Div(
                                                    [
                                                        html.I(
                                                            className=ICON_MODAL_UPLOAD,
                                                            style={
                                                                "marginRight": "0.5rem",
                                                                "color": "var(--primary-color)",
                                                            },
                                                        ),
                                                        "Drag & drop or click to upload a CIF / PDB file",
                                                    ],
                                                    style={
                                                        "textAlign": "center",
                                                        "padding": "0.75rem",
                                                        "color": "var(--text-secondary)",
                                                    },
                                                ),
                                                style={
                                                    "borderWidth": "1px",
                                                    "borderStyle": "dashed",
                                                    "borderRadius": "0.375rem",
                                                    "borderColor": "var(--border-color)",
                                                    "cursor": "pointer",
                                                },
                                                className="themed-control",
                                                multiple=False,
                                            ),
                                            html.Div(
                                                id=f"id-div-{TOOL_DEF['slug']}-upload-filename",
                                                className="mt-1",
                                            ),
                                            html.Small(
                                                "Optional — upload a CIF or PDB file to enable "
                                                "structure mode. Without a file, sequence-only "
                                                "mode (ProstT5) is used.",
                                                style={"color": "var(--text-tertiary)"},
                                            ),
                                        ],
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                            ),
                        ],
                    ),
                    # ── Section 2: Tool Configurations ───────────────
                    html.Div(
                        className="bg-light p-3 rounded mb-2",
                        children=[
                            create_modal_config_section_header(),
                            # Database Selection (multi-select)
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Databases", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id=f"id-dropdown-{TOOL_DEF['slug']}-databases",
                                            options=db_options,
                                            value=default_dbs,
                                            multi=True,
                                            placeholder="Select one or more FoldSeek databases...",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                        ],
                    ),
                    # ── Section 3: Status / job ID placeholder ───────
                    create_modal_submission_results(TOOL_DEF["slug"]),
                ],
            ),
            # ── Footer ───────────────────────────────────────────────
            create_modal_footer(TOOL_DEF["slug"]),
        ],
    )
