"""SMILES-to-SVG rendering utilities.

Shared helpers for generating SVG images from molecule and reaction
SMILES strings using RDKit's ``rdMolDraw2D`` drawing API.  These
functions are pure (no Dash dependency) and can be called from compute
modules, results layouts, or anywhere else that needs a visual
representation of a chemical structure.

Usage::

    from enzyme_tk_app.app.utils.smiles_rendering import (
        smiles_to_svg_data_uri,
        reaction_to_svg_data_uri,
    )

    mol_uri = smiles_to_svg_data_uri("CCO")              # base64 data URI for <img>
    rxn_uri = reaction_to_svg_data_uri("CC(=O)O.CCO>>CC(=O)OCC")
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd


def _svg_to_data_uri(svg: str) -> str:
    """Encode an SVG string as a base64 data URI.

    This is a shared helper.

    Args:
        svg: A raw SVG string (may be empty).

    Returns:
        A ``data:image/svg+xml;base64,...`` string, or an empty string
        if *svg* is empty.
    """
    import base64  # noqa: PLC0415

    if not svg:
        return ""
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def smiles_to_svg_data_uri(smiles: str, width: int = 300, height: int = 200) -> str:
    """Render a molecule SMILES as a base64-encoded SVG data URI.

    Returns a ``data:image/svg+xml;base64,...`` string that can be used
    directly as the ``src`` attribute of an ``<img>`` tag.  This is the
    preferred format for embedding molecule images in AG Grid cells
    because it avoids ``dangerouslySetInnerHTML`` issues.

    Args:
        smiles: A valid molecule SMILES string.
        width: SVG canvas width in pixels.
        height: SVG canvas height in pixels.

    Returns:
        A data URI string, or an empty string on parse failure.
    """
    from rdkit.Chem import MolFromSmiles  # noqa: PLC0415
    from rdkit.Chem.Draw import rdMolDraw2D  # noqa: PLC0415

    if not smiles or not smiles.strip():
        return ""

    mol = MolFromSmiles(smiles.strip())
    if mol is None:
        return ""

    # RDKit's MolDraw2D produces SVG output by default when using
    # the MolDraw2DSVG drawer.
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    return _svg_to_data_uri(svg) if isinstance(svg, str) else ""


def reaction_to_svg_data_uri(reaction_smiles: str, height: int = 200) -> str:
    """Render a reaction SMILES as a base64-encoded SVG data URI.

    Returns a ``data:image/svg+xml;base64,...`` string that can be used
    directly as the ``src`` attribute of an ``<img>`` tag.  The canvas
    width is computed adaptively so that each sub-image (reactant,
    product, plus the arrow) gets enough space.

    The reaction SMILES must use ``>>`` to separate substrates from
    products (e.g. ``"A.B>>C.D"``).  Individual reactants and products
    are separated by ``.``.

    Args:
        reaction_smiles: A valid reaction SMILES string.
        height: SVG canvas height in pixels.

    Returns:
        A data URI string, or an empty string on parse failure.
    """
    from rdkit.Chem import rdChemReactions  # noqa: PLC0415
    from rdkit.Chem.Draw import rdMolDraw2D  # noqa: PLC0415

    if not reaction_smiles or not reaction_smiles.strip():
        return ""

    # Parse the reaction SMILES into an RDKit Reaction object.
    try:
        rxn = rdChemReactions.ReactionFromSmarts(reaction_smiles.strip(), useSmiles=True)
    except ValueError:
        return ""
    if rxn is None:
        return ""

    # Adaptive width: allocate ~250 px per template (reactants + products + arrow).
    # RDKit internally divides the total width by (num_templates + 1).
    n_templates = rxn.GetNumReactantTemplates() + rxn.GetNumProductTemplates() + 1
    width = max(400, n_templates * 250)

    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    opts = drawer.drawOptions()

    # Reduce padding from the default 0.05 to keep multi-template images compact.
    opts.padding = 0.01
    drawer.DrawReaction(rxn)
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    return _svg_to_data_uri(svg) if isinstance(svg, str) else ""


def generate_cached_svg_uris(
    smiles_series: pd.Series,
    render_fn: Callable[..., str],
    **render_kwargs: Any,
) -> list[str]:
    """Render SMILES strings to SVG data URIs with deduplication caching.

    Iterates over *smiles_series*, calling *render_fn* once per unique
    SMILES value and caching the result so duplicate SMILES (e.g. the
    same reaction appearing in multiple databases) are only rendered
    once.

    Args:
        smiles_series: A pandas Series of SMILES strings.
        render_fn: A callable that accepts a SMILES string as its first
            positional argument (plus any *render_kwargs*) and returns a
            data-URI string.
        **render_kwargs: Additional keyword arguments forwarded to
            *render_fn* (e.g. ``width=500``, ``height=300``).

    Returns:
        A list of data-URI strings, one per element in *smiles_series*,
        in the same order.
    """
    cache: dict[str, str] = {}
    uris: list[str] = []
    for smi in smiles_series:
        if smi not in cache:
            cache[smi] = render_fn(smi, **render_kwargs)
        uris.append(cache[smi])
    return uris
