"""Modal layout for the Sequence Similarity tool.

This modal appears when the user clicks the Launch button on the Sequence
Similarity tool card.  It collects inputs needed to run a BLAST-based
sequence similarity search against a protein database.

Layout rules  (see ``.github/agents/create-modal.md``)
------------------------------------------------------
1. Top-level: ``dbc.Modal(size="lg", centered=True)``.
2. ``dbc.ModalBody`` gets ``className="p-4"``.
3. Each logical section is wrapped in
   ``html.Div(className="bg-light p-3 rounded mb-3")``.
4. Shared helpers from ``modal_helpers`` handle all repeated
   boilerplate — header, section headers, footer, and results
   placeholder.
5. Inputs use ``dbc.Row`` / ``dbc.Col`` for label ↔ control alignment.
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

from enzyme_tk_app.app.components.icons import ICON_MODAL_EXAMPLE
from enzyme_tk_app.app.components.modal_helpers import (
    create_modal_config_section_header,
    create_modal_databases_label,
    create_modal_footer,
    create_modal_header,
    create_modal_input_section_header,
    create_modal_submission_results,
)
from enzyme_tk_app.app.tools.sequence_similarity import TOOL_DEF
from enzyme_tk_app.app.utils.data_loading import get_sequence_database_options


def _get_example_sequences():
    """Return a list of example protein sequences from the protein database.

    These are real entries from ``protein.csv`` covering diverse EC classes.
    """
    return [
        {
            "label": "A0A009IHW8 — DNA glycosylase (EC 3.2.2.-)",
            "value": (
                "MSLEQKKGADIISKILQIQNSIGKTTSPSTLKTKLSEISRKEQENARI"
                "QSKLSDLQKKKIDIDNKLLKEKQNLIKEEILERKKLEVLTKKQQKDEIEHQKKLKREIDAIKASTQYITDVSI"
                "SSYNNTIPETEPEYDLFISHASEDKEDFVRPLAETLQQLGVNVWYDEFTLKVGDSLRQKIDSGLRNSKYGTVV"
                "LSTDFIKKDWTNYELDGLVAREMNGHKMILPIWHKITKNDVLDYSPNLADKVALNTSVNSIEEIAHQLADVILNR"
            ),
        },
        {
            "label": "A0A024SC78 — Esterase (EC 3.1.1.74)",
            "value": (
                "MRSLAILTTLLAGHAFAYPKPAPQSVNRRDWPSINEFLSELAKVMPIGDTITAACD"
                "LISDGEDAAASLFGISETENDPCGDVTVLFARGTCDPGNVGVLVGPWFFDSLQTALGSRTLGVKGVPYPASVQ"
                "DFLSGSVQNGINMANQIKSVLQSCPNTKLVLGGYSQGSMVVHNAASNLDAATMSKISAVVLFGDPYYGKPVAN"
                "FDAAKTLVVCHDGDNICQGGDIILLPHLTYAEDADTAAAFVVPLVS"
            ),
        },
        {
            "label": "A0A059TC02 — Cinnamyl-alcohol dehydrogenase (EC 1.2.1.44)",
            "value": (
                "MRSVSGQVVCVTGAGGFIASWLVKILLEKGYTVRGTVRNPDDPKNGHLRELEGAKE"
                "RLTLCKADLLDYQSLREAINGCDGVFHTASPVTDDPEQMVEPAVIGTKNVINAAAEANVRRVVFTSSIGAVYM"
                "DPNRDPETVVDETCWSDPDFCKNTKNWYCYGKMVAEQAAWEEAKEKGVDLVVINPVLVQGPLLQTTVNASVLH"
                "ILKYLTGSAKTYANSVQAYVDVKDVALAHILLYETPEASGRYLCAESVLHRGDVVEILSKFFPEYPIPTKCSDV"
                "TKPRVKPYKFSNQKLKDLGLEFTPVKQCLYETVKSLQEKGHLPIPTQKDEPIIRIQP"
            ),
        },
        {
            "label": "A0A067CMC7 — Nuclease (EC 3.1.31.-)",
            "value": (
                "MLEVPVWIPILAFAVGLGLGLLIPHLQKPFQRFSTVNDIPKEFFEHERTLRGKVVS"
                "VTDGDTIRVRHVPWLANGDGDFKGKLTETTLQLRVAGVDCPETAKFGRTGQPFGEEAKAWLKGELQDQVVSF"
                "KLLMKDQYSRAVCLVYYGSWAAPMNVSEELLRHGYANIYRQSGAVYGGLLETFEALEAEAREKRVNIWSLDKRE"
                "TPAQYKARK"
            ),
        },
        {
            "label": "A0A075D5I4 — Methyltransferase (EC 2.1.1.-)",
            "value": (
                "MAEKQQAVAEFYDNSTGAWEVFFGDHLHDGFYDPGTTATIAGSRAAVVRMIDEALRF"
                "ANISDDPAKKPKTMLDVGCGIGGTCLHVAKKYGIQCKGITISSEQVKCAQGFAEEQGLEKKVSFDVGDALDMP"
                "YKDGTFDLVFTIQCIEHIQDKEKFIREMVRVAAPGAPIVIVSYAHRNLSPSEGSLKPEEKKVLKKICDNIVLS"
                "WVCSSADYVRWLTPLPVEDIKAADWTQNITPFYPLLMKEAFTWKGFTSLLMKGGWSAIKVVLAVRMMAKAADDG"
                "VLKFVAVTCRKSK"
            ),
        },
    ]


def modal():
    """Build the Sequence Similarity modal component.

    Returns:
        A ``dbc.Modal`` component with inputs for:
        - Task name
        - Protein sequence (textarea)
        - Database selection (multi-select, all pre-selected)
        - EC number filter (multi-select, dynamically populated)
        - Cofactor filter (multi-select, disabled placeholder)
        - Top-N results limit
        - Predict catalytic residues checkbox
    """
    db_options = get_sequence_database_options()

    # Pre-select every database — hits from all of them are merged and ranked
    # together, so the default is the broadest search.
    all_db_values = [opt["value"] for opt in db_options]

    return dbc.Modal(
        # Modal ID follows the convention: id-modal-<slug>
        id=f"id-modal-{TOOL_DEF['slug']}",
        is_open=False,
        size="lg",
        centered=True,
        children=[
            # ------------------------------------------------
            # MODAL Header
            # ------------------------------------------------
            create_modal_header(TOOL_DEF["icon"], TOOL_DEF["title"]),
            # ------------------------------------------------
            # MODAL BODY
            # ------------------------------------------------
            dbc.ModalBody(
                className="p-4",
                children=[
                    # ------------------------------------------------
                    # Section 1: Input Data
                    # ------------------------------------------------
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
                                            placeholder="e.g. 'Kinase BLAST search'",
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
                                                    "Paste a protein amino-acid sequence (e.g. MKTIIALSYIFCLVFA...)"
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
                                                            {"label": ex["label"], "value": ex["value"]}
                                                            for ex in _get_example_sequences()
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
                        ],
                    ),
                    # ------------------------------------------------
                    # Section 2: Tool Configurations
                    # ------------------------------------------------
                    html.Div(
                        className="bg-light p-3 rounded mb-2",
                        children=[
                            create_modal_config_section_header(),
                            # Database Selection (multi-select, all pre-selected)
                            dbc.Row(
                                [
                                    create_modal_databases_label(
                                        TOOL_DEF["slug"],
                                        "Entry, Sequence and EC number columns, plus any metadata the file carries.",
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id=f"id-dropdown-{TOOL_DEF['slug']}-databases",
                                            options=db_options,
                                            value=all_db_values,
                                            multi=True,
                                            placeholder="Select one or more sequence databases...",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # EC Number Filter (multi-select, dynamically populated)
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("EC Number", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id=f"id-dropdown-{TOOL_DEF['slug']}-ec-filter",
                                            options=[],
                                            value=[],
                                            multi=True,
                                            placeholder="Filter by EC number (optional)...",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Cofactor Filter (multi-select, disabled — coming soon)
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Cofactor", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dcc.Dropdown(
                                            id=f"id-dropdown-{TOOL_DEF['slug']}-cofactor-filter",
                                            options=[],
                                            value=[],
                                            multi=True,
                                            placeholder="Coming soon — no cofactor data loaded",
                                            disabled=True,
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Top-N Results
                            dbc.Row(
                                [
                                    dbc.Col(
                                        dbc.Label("Top N Results", className="col-form-label fw-bold"),
                                        width=3,
                                    ),
                                    dbc.Col(
                                        dbc.Input(
                                            id=f"id-input-{TOOL_DEF['slug']}-top-n",
                                            type="number",
                                            value=10,
                                            min=1,
                                            max=500,
                                            step=1,
                                            placeholder="Number of top results",
                                            className="themed-control",
                                        ),
                                        width=9,
                                    ),
                                ],
                                className="mb-2",
                                align="center",
                            ),
                            # Predict Catalytic Residues
                            dbc.Row(
                                [
                                    dbc.Col(width=3),
                                    dbc.Col(
                                        dbc.Checkbox(
                                            id=f"id-check-{TOOL_DEF['slug']}-predict-catalytic",
                                            label="Predict catalytic residues",
                                            value=False,
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
                    # ------------------------------------------------
                    # Section 3: Status / job ID placeholder
                    # ------------------------------------------------
                    create_modal_submission_results(TOOL_DEF["slug"]),
                ],
            ),
            # ------------------------------------------------
            # Footer: Cancel (outline) + Submit (primary)
            # ------------------------------------------------
            create_modal_footer(TOOL_DEF["slug"]),
        ],
    )
