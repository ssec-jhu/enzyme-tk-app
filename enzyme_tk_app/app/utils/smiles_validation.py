"""Validation for user-typed SMILES strings.

Every tool that takes a structure from the user validates it here, in three
places: the form callback (so the Run button stays disabled and the field turns
red), the submit callback (the client gate is bypassable), and ``run()`` (a
replayed job never touches the modal).

Both validators return **a message or ``None``**, matching ``validate_db_names``
in :mod:`~enzyme_tk_app.app.utils.data_loading` and ``validate_top_n`` in
:mod:`~enzyme_tk_app.app.utils.formatting`, so a callback consumes all three the
same way.

Deliberately stricter than the parsers downstream
-------------------------------------------------
``validate_reaction_smiles`` requires ``>>`` and requires each side to parse as a
*molecule*.  ``enzymetk``'s ``ReactionDist`` is looser — it calls
``rdChemReactions.ReactionFromSmarts(...)`` without ``useSmiles=True``, so as
SMARTS it happily accepts ``">>"``, ``"CCO>>"`` and hypervalent atoms and returns
a full grid of meaningless similarity scores.  Rejecting those up front is the
point of this module.

The cost of that strictness is the three-part ``reactants>agents>products`` form,
which is rejected.  That is consistent with the rest of the app: ``>>`` is what
every modal placeholder, every shipped example, and
``reaction_to_svg_data_uri``'s documented contract assume — a three-part reaction
would lose its query preview on the results page anyway.

rdkit is imported inside the functions, never at module scope, so ``callbacks.py``
modules can import this one without pulling rdkit into the web process at start-up.

A rejection carries **RDKit's own diagnosis** — "unclosed ring", not a copy of the
string the user is looking at.  A lost ring-closure digit in a 38-character SMILES
is invisible, and echoing the input back says nothing the field does not already
show; see :func:`_parse_failure`.
"""

import re


def _tidy(messages: str) -> str:
    """Reduce RDKit's captured log to the one phrase worth showing the user.

    A raw message looks like::

        [20:02:29] SMILES Parse Error: unclosed ring for input: 'OC[C@H]1...'

    Three parts of that are noise: the timestamp, the ``SMILES Parse Error:``
    prefix (the caller's sentence already says the string is not valid), and the
    echo of the input, which is sitting in the field the message appears under.
    Only the first line survives — a syntax error adds a caret diagram across
    three more lines that does not fit a form-feedback line.
    """
    first = messages.strip().splitlines()[0] if messages.strip() else ""
    first = re.sub(r"^\[[\d:]+\]\s*", "", first)
    first = re.sub(r"^SMILES Parse Error:\s*", "", first)
    # "unclosed ring for input: 'CCO'" -> "unclosed ring".
    first = re.split(r"\s+for input:\s*", first)[0]
    # "syntax error while parsing: XYZ" -> the tail is the input echoed a second time.
    first = re.sub(r"^(syntax error while parsing):.*$", r"\1", first)
    return first.strip().rstrip(":")


def _parse_failure(smiles: str) -> str | None:
    """Return RDKit's own reason for refusing *smiles*, or ``None`` if it parses.

    ``MolFromSmiles`` reports nothing to its caller — it returns ``None`` and
    writes the diagnosis to RDKit's error log — so without this the user is told
    only that the string they can already see is wrong.  ``CaptureErrorLog`` is
    scoped and nestable, unlike redirecting ``sys.stderr``, which matters because
    gunicorn serves this app with ``--threads 4``.
    """
    from rdkit import rdBase  # noqa: PLC0415
    from rdkit.Chem import MolFromSmiles  # noqa: PLC0415

    with rdBase.CaptureErrorLog() as captured:
        molecule = MolFromSmiles(smiles)

    if molecule is not None:
        return None
    # RDKit is silent for a few refusals, so never return an empty reason.
    return _tidy(captured.messages) or "could not be parsed"


def split_reaction(smiles: str) -> tuple[str, str]:
    """Split a reaction SMILES into ``(substrate, product)`` on ``>>``.

    The product is the *last* segment, so a multi-arrow string like ``A>>B>>C``
    yields ``(A, C)``.  Each side may be dot-joined (``A.B>>C``); it is embedded
    whole, exactly as the reference example does.
    """
    parts = smiles.strip().split(">>")
    return parts[0].strip(), parts[-1].strip()


def validate_reaction_smiles(smiles: object) -> str | None:
    """Return an error message for an unusable reaction SMILES, or ``None``.

    Args:
        smiles: The reaction SMILES from the modal.

    Returns:
        A human-readable error message, or ``None`` when *smiles* is usable.
    """
    if not isinstance(smiles, str) or not smiles.strip():
        return "Enter a reaction SMILES."

    if ">>" not in smiles:
        return "Reaction SMILES must separate substrate from product with '>>'."

    substrate, product = split_reaction(smiles)
    if not substrate or not product:
        return "Reaction SMILES needs a substrate before '>>' and a product after it."

    # Name the side *and* what is wrong with it — a missing ring-closure digit is
    # invisible in a long string, and echoing the string back does not reveal it.
    for label, side in (("substrate", substrate), ("product", product)):
        reason = _parse_failure(side)
        if reason:
            return f"The {label} is not a valid SMILES: {reason}"

    return None


def validate_smiles(smiles: object) -> str | None:
    """Return an error message for an unusable single-molecule SMILES, or ``None``.

    The single-molecule sibling of :func:`validate_reaction_smiles`, for fields
    that take one structure rather than a reaction.  A reaction pasted into such
    a field is named as the mistake it is, rather than failing as "not a valid
    SMILES" and leaving the user to spot the ``>>``.

    Args:
        smiles: The molecule SMILES from the modal.

    Returns:
        A human-readable error message, or ``None`` when *smiles* is usable.
    """
    if not isinstance(smiles, str) or not smiles.strip():
        return "Enter a SMILES string."

    molecule = smiles.strip()
    if ">>" in molecule:
        return "Enter a single molecule, not a reaction — remove the '>>' and everything after it."

    # Say what is wrong, not what the user typed — they can see what they typed.
    reason = _parse_failure(molecule)
    if reason:
        return f"Not a valid SMILES: {reason}"

    return None
