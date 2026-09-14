"""Tests for ``utils/smiles_validation.py``.

Real RDKit here, no stand-ins: whether RDKit itself can read the string is the
whole question.  Three tools share these two validators — Func-E and Reaction
Similarity take reactions, Substrate/Product Similarity takes one molecule — and
each calls them in three places (the form callback, the submit callback and
``run()``), so a string accepted here is a string the worker will be asked to
score.

The rejections matter more than the acceptances.  ``enzymetk``'s ``ReactionDist``
parses the query as SMARTS, which swallows ``">>"`` and ``"CCO>>"`` and returns a
full grid of meaningless scores; ``SubstrateDist`` hands an unparseable molecule
to ``mfpgen.GetFingerprint(None)`` and raises a C++ signature dump.  Neither
failure is legible to the user, which is why they are caught here instead.
"""

import pytest

from enzyme_tk_app.app.utils.smiles_validation import (
    split_reaction,
    validate_reaction_smiles,
    validate_smiles,
)

# ── Splitting a reaction ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("smiles", "expected"),
    [
        ("CCO>>CC=O", ("CCO", "CC=O")),
        # A multi-arrow string is a route, not a reaction: the last segment is the
        # product and everything between is intermediate.
        ("CCO>>CC=O>>CC(=O)O", ("CCO", "CC(=O)O")),
        ("  CCO >> CC=O\n", ("CCO", "CC=O")),
    ],
    ids=["one-arrow", "multi-arrow-keeps-the-last-product", "padded-with-whitespace"],
)
def test_split_reaction_returns_the_substrate_and_the_final_product(smiles, expected):
    """Whatever the user pasted, the two sides come back trimmed and in order."""
    assert split_reaction(smiles) == expected


# ── Validating a reaction ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "smiles",
    [
        "CCO>>CC=O",
        # A dot-joined side is one multi-component reaction, not two reactions —
        # it is embedded whole, so it must not be refused.
        "CCO.O>>CC(=O)O",
        # Pasted out of a paper, trailing newline and all.
        "  CCO>>CC=O \n",
    ],
    ids=["one-molecule-a-side", "dot-joined-multi-component", "padded-with-whitespace"],
)
def test_validate_reaction_smiles_accepts_a_usable_reaction(smiles):
    """A parseable substrate and product either side of ``>>`` is usable."""
    assert validate_reaction_smiles(smiles) is None


@pytest.mark.parametrize(
    ("smiles", "expected_fragment"),
    [
        # ``None`` as the fragment means any message will do — for these cases the
        # point is only that the string is refused, not how the refusal is worded.
        ("", None),
        ("   ", None),
        (None, None),
        ("CCO", "'>>'"),
        (">>CCO", None),
        ("CCO>>", None),
        # The SMARTS parser enzymetk uses reads this as a reaction with no
        # reactants and no products, then scores every row against it.
        (">>", None),
        # RDKit returns None rather than raising on these, so the check is easy to
        # lose; the message has to name the side the user must fix.
        ("XYZ>>CCO", "substrate"),
        ("CCO>>XYZ", "product"),
        # Five bonds on a carbon: MolFromSmiles refuses it, the SMARTS parser does not.
        ("C(C)(C)(C)(C)C>>CCO", "substrate"),
        # A lost ring-closure digit, the mistake that reads as no mistake at all.
        ("OC[C@H]1OC(O)[C@@H]O>>CCO", "unclosed ring"),
    ],
    ids=[
        "empty",
        "whitespace-only",
        "not-a-string",
        "no-arrow",
        "no-substrate",
        "no-product",
        "arrow-only",
        "unparseable-substrate",
        "unparseable-product",
        "hypervalent-carbon",
        "unclosed-ring-substrate",
    ],
)
def test_validate_reaction_smiles_rejects_what_cannot_be_scored(smiles, expected_fragment):
    """Every unusable string comes back as a message — never ``None``, never an exception."""
    message = validate_reaction_smiles(smiles)

    assert isinstance(message, str) and message.strip(), "An unusable reaction must be reported, not accepted"
    if expected_fragment:
        assert expected_fragment in message


# ── Validating a single molecule ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "smiles",
    [
        "CCO",
        "O=C(O)c1ccccc1",
        # Stereochemistry and charges are ordinary SMILES, not exotic input.
        "N[C@@H](C)C(=O)O",
        "O=[N+]([O-])c1ccccc1",
        "  CCO \n",
    ],
    ids=["ethanol", "benzoic-acid", "stereocentre", "charged", "padded-with-whitespace"],
)
def test_validate_smiles_accepts_a_usable_molecule(smiles):
    """Anything RDKit can build a molecule from is usable."""
    assert validate_smiles(smiles) is None


@pytest.mark.parametrize(
    ("smiles", "expected_fragment"),
    [
        ("", None),
        ("   ", None),
        (None, None),
        ("XYZ", "syntax error"),
        ("c1ccccc", "unclosed ring"),
        ("CC(C)(C)(C)C", "valence"),
        # A reaction in a single-molecule field is a specific mistake, so it gets a
        # specific message rather than the generic "not a valid SMILES".
        ("CCO>>CC=O", "'>>'"),
    ],
    ids=[
        "empty",
        "whitespace-only",
        "not-a-string",
        "unparseable",
        "unclosed-ring",
        "hypervalent-carbon",
        "reaction-in-a-molecule-field",
    ],
)
def test_validate_smiles_rejects_what_cannot_be_fingerprinted(smiles, expected_fragment):
    """Every unusable string comes back as a message — never ``None``, never an exception."""
    message = validate_smiles(smiles)

    assert isinstance(message, str) and message.strip(), "An unusable molecule must be reported, not accepted"
    if expected_fragment:
        assert expected_fragment in message


# ── The message says what is wrong, not what was typed ───────────────────────

# The shipped Substrate/Product example, and the two edits a user actually made to it.
_GLUCOSE = "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O"


@pytest.mark.parametrize(
    ("smiles", "is_usable"),
    [
        (_GLUCOSE, True),
        # Deleting the trailing "O" leaves the ring closed — still a molecule.
        (_GLUCOSE[:-1], True),
        # Losing the ring-closure "1" as well does not.  On screen the two differ by
        # one character in thirty-eight, which is why the message cannot just echo it.
        (_GLUCOSE[:-2] + "O", False),
    ],
    ids=["as-shipped", "trailing-O-deleted", "ring-digit-lost"],
)
def test_editing_the_glucose_example_is_judged_on_the_ring_not_the_length(smiles, is_usable):
    """Only the lost ring-closure digit makes the example unusable.

    Pinned because it was misread as a validation bug: the field looked unchanged,
    so a correct rejection looked like a stale one.  The two accepted strings here
    are the proof that the rejection tracks the chemistry, not the edit.
    """
    message = validate_smiles(smiles)

    if is_usable:
        assert message is None
    else:
        assert message == "Not a valid SMILES: unclosed ring", (
            "A missing ring-closure digit must be named, not echoed back as the whole string"
        )


def test_rejection_names_the_defect_rather_than_repeating_the_input():
    """The reason comes from RDKit; the string the user can already see does not.

    ``MolFromSmiles`` reports nothing to its caller, so this is the whole value of
    routing through ``CaptureErrorLog`` — drop it and the message silently decays
    back to echoing the input.
    """
    message = validate_smiles("c1ccccc")

    assert "unclosed ring" in message
    assert "c1ccccc" not in message, "The message must not echo the input back at the user"
