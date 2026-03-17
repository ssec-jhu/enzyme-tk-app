"""Tests for the tools auto-discovery system, ToolDef validation, and tool modals.

These tests are resilient to tools being added or removed — they scan the
``tools/`` directory at runtime instead of hard-coding tool names.

How it works
------------
Each tool lives in its own folder under ``enzyme_tk_app/app/tools/``.
The discovery system (``tools/__init__.py``) imports every sub-folder that
exports a ``TOOL_DEF`` dictionary and collects it into the ``TOOLS`` list.
Optional ``modal.py`` and ``callbacks.py`` files are also picked up.

These tests verify:
1. Every tool folder on disk is correctly discovered.
2. Every ``TOOL_DEF`` has the right shape (required keys, valid slug, etc.).
3. Modals and callbacks load without errors.
4. Adding or removing a tool folder doesn't break the system.
"""

import importlib
import logging
import pkgutil
import re
from unittest.mock import MagicMock, patch

import dash_bootstrap_components as dbc
from dash import html

from enzyme_tk_app.app.tools import TOOLS, ToolDef, _discover_tools, _modal_funcs, tool_modals

# ---------------------------------------------------------------------------
# Helpers — find tool folders on disk
# ---------------------------------------------------------------------------

# Get the filesystem path of the tools package so we can list sub-folders.
_tools_package = importlib.import_module("enzyme_tk_app.app.tools")

# List every sub-folder name inside tools/ (e.g. "reaction_similarity").
_tool_folder_names = [
    folder_name for _, folder_name, is_package in pkgutil.iter_modules(_tools_package.__path__) if is_package
]


def _load_tool_folder(folder_name):
    """Import and return the Python package for a tool folder.

    Example: _load_tool_folder("reaction_similarity") imports
    enzyme_tk_app.app.tools.reaction_similarity
    """
    return importlib.import_module(f"enzyme_tk_app.app.tools.{folder_name}")


# ---------------------------------------------------------------------------
# 1. Discovery — is every tool folder picked up correctly?
# ---------------------------------------------------------------------------


def test_at_least_one_tool_is_discovered():
    """The TOOLS list must not be empty."""
    assert len(TOOLS) >= 1


def test_every_folder_with_tool_def_appears_in_tools():
    """If a folder exports TOOL_DEF, it must show up in the TOOLS list."""
    all_slugs = {tool["slug"] for tool in TOOLS}

    for folder_name in _tool_folder_names:
        package = _load_tool_folder(folder_name)
        tool_def = getattr(package, "TOOL_DEF", None)

        if tool_def is not None:
            assert tool_def["slug"] in all_slugs, (
                f"Folder '{folder_name}' has a TOOL_DEF (slug='{tool_def['slug']}') but it was not found in TOOLS"
            )


def test_folder_without_tool_def_is_skipped():
    """If a folder does NOT export TOOL_DEF, it must not appear in TOOLS."""
    all_slugs = {tool["slug"] for tool in TOOLS}

    for folder_name in _tool_folder_names:
        package = _load_tool_folder(folder_name)

        if getattr(package, "TOOL_DEF", None) is None:
            # Folder names use underscores, slugs use hyphens.
            slug_form = folder_name.replace("_", "-")
            assert slug_form not in all_slugs, f"Folder '{folder_name}' has no TOOL_DEF but somehow appears in TOOLS"


def test_tools_count_matches_folders_on_disk():
    """The number of TOOLS entries must equal the number of folders that have a TOOL_DEF."""
    folders_with_tool_def = 0
    for folder_name in _tool_folder_names:
        package = _load_tool_folder(folder_name)
        if getattr(package, "TOOL_DEF", None) is not None:
            folders_with_tool_def += 1

    assert len(TOOLS) == folders_with_tool_def


def test_no_duplicate_slugs():
    """Every tool must have a unique slug."""
    slugs = [tool["slug"] for tool in TOOLS]
    assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {slugs}"


# ---------------------------------------------------------------------------
# 2. ToolDef shape — does each tool have the right fields?
# ---------------------------------------------------------------------------


def test_required_keys_present():
    """Every tool must have all keys marked as required in ToolDef."""
    # Use the same source of truth as the production code so this test
    # stays in sync automatically when fields are added or removed.
    required_keys = ToolDef.__required_keys__

    for tool in TOOLS:
        missing = required_keys - tool.keys()
        assert not missing, f"Tool '{tool.get('title', '?')}' is missing: {missing}"


def test_no_unknown_keys():
    """Tools should only use recognised keys defined in ToolDef."""
    allowed_keys = {"slug", "title", "desc", "icon", "order", "libraries", "max_duration"}

    for tool in TOOLS:
        extra = set(tool.keys()) - allowed_keys
        assert not extra, f"Tool '{tool['title']}' has unexpected keys: {extra}"


def test_slug_format():
    """Slugs must be lowercase words joined by hyphens (e.g. 'reaction-similarity')."""
    pattern = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

    for tool in TOOLS:
        assert pattern.match(tool["slug"]), (
            f"Slug '{tool['slug']}' is not valid — use lowercase letters, numbers, and hyphens only"
        )


def test_slug_matches_folder_name():
    """A tool's slug must match its folder name with underscores replaced by hyphens."""
    for folder_name in _tool_folder_names:
        package = _load_tool_folder(folder_name)
        tool_def = getattr(package, "TOOL_DEF", None)
        if tool_def is None:
            continue

        expected_slug = folder_name.replace("_", "-")
        assert tool_def["slug"] == expected_slug, (
            f"Folder '{folder_name}' → expected slug '{expected_slug}', got '{tool_def['slug']}'"
        )


def test_title_is_non_empty():
    """Every tool title must be a non-empty string."""
    for tool in TOOLS:
        assert isinstance(tool["title"], str) and tool["title"].strip()


def test_description_is_non_empty():
    """Every tool description must be a non-empty string."""
    for tool in TOOLS:
        assert isinstance(tool["desc"], str) and tool["desc"].strip()


def test_icon_is_fontawesome():
    """Every tool icon must be a FontAwesome class (starts with 'fa-')."""
    for tool in TOOLS:
        assert tool["icon"].startswith("fa-"), f"Tool '{tool['title']}' icon is not FontAwesome"


def test_libraries_are_list_of_strings():
    """If a tool has 'libraries', it must be a list of non-empty strings."""
    for tool in TOOLS:
        libraries = tool.get("libraries")
        if libraries is None:
            continue  # libraries is optional

        assert isinstance(libraries, list)
        for lib in libraries:
            assert isinstance(lib, str) and lib.strip(), (
                f"Tool '{tool['title']}' has an empty or non-string library entry"
            )


# ---------------------------------------------------------------------------
# 3. Modals — do modal dialogs load correctly?
# ---------------------------------------------------------------------------


def test_modal_count_matches_modal_files_on_disk():
    """The number of discovered modals must equal the number of modal.py files."""
    expected_count = 0
    for folder_name in _tool_folder_names:
        package = _load_tool_folder(folder_name)
        if getattr(package, "TOOL_DEF", None) is None:
            continue
        try:
            modal_module = importlib.import_module(f"enzyme_tk_app.app.tools.{folder_name}.modal")
            if hasattr(modal_module, "modal"):
                expected_count += 1
        except ModuleNotFoundError:
            pass  # No modal.py file — that's fine

    assert len(_modal_funcs) == expected_count


def test_tool_modals_returns_a_div():
    """tool_modals() must return an html.Div container."""
    container = tool_modals()
    assert isinstance(container, html.Div)


def test_tool_modals_contains_only_dbc_modals():
    """Every child inside the tool_modals container must be a dbc.Modal."""
    container = tool_modals()
    children = container.children or []

    for child in children:
        assert isinstance(child, dbc.Modal), f"Expected dbc.Modal, got {type(child).__name__}"


def test_tool_modals_count():
    """tool_modals() must produce one modal per discovered modal factory."""
    container = tool_modals()
    children = container.children or []
    assert len(children) == len(_modal_funcs)


def test_every_modal_has_an_id():
    """Each modal component must have a Dash id attribute."""
    container = tool_modals()
    children = container.children or []

    for modal in children:
        modal_id = getattr(modal, "id", None)
        assert modal_id, "A modal is missing its 'id' attribute"


def test_modal_ids_follow_naming_convention():
    """Modal ids must follow the pattern 'id-modal-<slug>'."""
    pattern = re.compile(r"^id-modal-[a-z0-9-]+$")
    container = tool_modals()
    children = container.children or []

    for modal in children:
        modal_id = getattr(modal, "id", "")
        assert pattern.match(modal_id), f"Modal id '{modal_id}' doesn't match the expected pattern 'id-modal-<slug>'"


# ---------------------------------------------------------------------------
# 4. Callbacks — do callback modules load without errors?
# ---------------------------------------------------------------------------


def test_callbacks_importable():
    """If a tool folder has callbacks.py, importing it must not raise errors."""
    for folder_name in _tool_folder_names:
        package = _load_tool_folder(folder_name)
        if getattr(package, "TOOL_DEF", None) is None:
            continue
        try:
            importlib.import_module(f"enzyme_tk_app.app.tools.{folder_name}.callbacks")
        except ModuleNotFoundError:
            pass  # No callbacks.py — that's fine


# ---------------------------------------------------------------------------
# 5. Regression guards — protect against common mistakes
# ---------------------------------------------------------------------------


def test_reimport_does_not_duplicate_tools():
    """Importing the tools package a second time must not add duplicate entries."""
    count_before = len(TOOLS)
    importlib.import_module("enzyme_tk_app.app.tools")
    assert len(TOOLS) == count_before


def test_tool_def_type_has_expected_fields():
    """The ToolDef TypedDict must declare slug, title, desc, icon, order, and libraries."""
    fields = ToolDef.__annotations__
    for key in ("slug", "title", "desc", "icon", "order", "libraries"):
        assert key in fields, f"ToolDef is missing the '{key}' field"


# ---------------------------------------------------------------------------
# 6. Discovery error paths — does _discover_tools handle failures gracefully?
# ---------------------------------------------------------------------------
# These tests call ``_discover_tools()`` directly with mocked sub-packages
# to exercise the error/warning branches that never fire when all real tools
# are well-formed.  Each test:
#   1. Saves the current TOOLS/_modal_funcs lists.
#   2. Clears them and patches ``pkgutil.iter_modules`` to return a fake tool.
#   3. Asserts that the broken tool is skipped and a warning is logged.
#   4. Restores the original lists so other tests are unaffected.


def _run_discover_with_fake_tool(fake_module, monkeypatch):
    """Run ``_discover_tools`` with a single fake sub-package.

    Args:
        fake_module: A mock object returned by ``importlib.import_module``.
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        Tuple of (TOOLS snapshot, _modal_funcs snapshot) after discovery.
    """
    import enzyme_tk_app.app.tools as tools_pkg

    # Save originals and start with empty lists.
    original_tools = list(TOOLS)
    original_modals = list(_modal_funcs)
    TOOLS.clear()
    _modal_funcs.clear()

    # Pretend there is one sub-package called "fake_tool".
    monkeypatch.setattr(
        tools_pkg,
        "__path__",
        tools_pkg.__path__,
    )

    with patch("enzyme_tk_app.app.tools.pkgutil.iter_modules", return_value=[(None, "fake_tool", True)]):
        with patch("enzyme_tk_app.app.tools.importlib.import_module", side_effect=fake_module):
            _discover_tools()

    result_tools = list(TOOLS)
    result_modals = list(_modal_funcs)

    # Restore originals so later tests are unaffected.
    TOOLS.clear()
    TOOLS.extend(original_tools)
    _modal_funcs.clear()
    _modal_funcs.extend(original_modals)

    return result_tools, result_modals


def test_discover_skips_tool_when_import_fails(monkeypatch, caplog):
    """A tool whose __init__.py raises an exception must be skipped with a warning."""

    def _raise_on_import(name):
        raise RuntimeError("broken tool")

    with caplog.at_level(logging.WARNING, logger="enzyme_tk_app.app.tools"):
        tools, _ = _run_discover_with_fake_tool(_raise_on_import, monkeypatch)

    assert len(tools) == 0, "Broken tool should not appear in TOOLS"
    assert any("Failed to import tool package" in msg for msg in caplog.messages)


def test_discover_skips_tool_without_tool_def(monkeypatch, caplog):
    """A sub-package that exists but has no TOOL_DEF must be skipped."""
    # Return a mock module with no TOOL_DEF attribute.
    empty_module = MagicMock(spec=[])

    def _import_empty(name):
        if name.endswith(".fake_tool"):
            return empty_module
        raise ModuleNotFoundError(name=name)

    with caplog.at_level(logging.WARNING, logger="enzyme_tk_app.app.tools"):
        tools, _ = _run_discover_with_fake_tool(_import_empty, monkeypatch)

    assert len(tools) == 0, "Tool without TOOL_DEF should not appear in TOOLS"
    assert any("has no TOOL_DEF" in msg for msg in caplog.messages)


def test_discover_skips_tool_with_missing_required_keys(monkeypatch, caplog):
    """A TOOL_DEF missing required keys must be skipped with a warning."""
    # Provide a TOOL_DEF that is missing 'icon' and 'desc'.
    incomplete_module = MagicMock()
    incomplete_module.TOOL_DEF = {"slug": "fake-tool", "title": "Fake"}

    def _import_incomplete(name):
        if name.endswith(".fake_tool"):
            return incomplete_module
        raise ModuleNotFoundError(name=name)

    with caplog.at_level(logging.WARNING, logger="enzyme_tk_app.app.tools"):
        tools, _ = _run_discover_with_fake_tool(_import_incomplete, monkeypatch)

    assert len(tools) == 0, "Tool with missing keys should not appear in TOOLS"
    assert any("missing required key(s)" in msg for msg in caplog.messages)


def test_discover_accepts_tool_with_all_required_keys(monkeypatch):
    """A well-formed TOOL_DEF must be accepted into TOOLS."""
    good_module = MagicMock()
    good_module.TOOL_DEF = {
        "slug": "fake-tool",
        "title": "Fake Tool",
        "desc": "A fake tool for testing.",
        "icon": "fa-solid fa-flask",
        "order": 99,
    }

    def _import_good(name):
        if name.endswith(".fake_tool"):
            return good_module
        # callbacks.py and modal.py are absent — that's fine.
        raise ModuleNotFoundError(name=name)

    tools, _ = _run_discover_with_fake_tool(_import_good, monkeypatch)

    assert len(tools) == 1
    assert tools[0]["slug"] == "fake-tool"


def test_discover_logs_warning_for_callbacks_dependency_error(monkeypatch, caplog):
    """If callbacks.py exists but has a missing dependency, a warning must be logged."""
    good_module = MagicMock()
    good_module.TOOL_DEF = {
        "slug": "fake-tool",
        "title": "Fake Tool",
        "desc": "A fake tool for testing.",
        "icon": "fa-solid fa-flask",
        "order": 99,
    }

    def _import_with_bad_callbacks(name):
        if name.endswith(".fake_tool"):
            return good_module
        if name.endswith(".callbacks"):
            # Simulate callbacks.py importing a missing third-party package.
            raise ModuleNotFoundError(name="some_missing_lib")
        # modal.py is absent.
        raise ModuleNotFoundError(name=name)

    with caplog.at_level(logging.WARNING, logger="enzyme_tk_app.app.tools"):
        tools, _ = _run_discover_with_fake_tool(_import_with_bad_callbacks, monkeypatch)

    # The tool itself should still be added (only callbacks failed).
    assert len(tools) == 1
    assert any("missing dependency" in msg for msg in caplog.messages)


def test_discover_logs_warning_for_modal_dependency_error(monkeypatch, caplog):
    """If modal.py exists but has a missing dependency, a warning must be logged."""
    good_module = MagicMock()
    good_module.TOOL_DEF = {
        "slug": "fake-tool",
        "title": "Fake Tool",
        "desc": "A fake tool for testing.",
        "icon": "fa-solid fa-flask",
        "order": 99,
    }

    def _import_with_bad_modal(name):
        if name.endswith(".fake_tool"):
            return good_module
        if name.endswith(".callbacks"):
            raise ModuleNotFoundError(name=name)
        if name.endswith(".modal"):
            # Simulate modal.py importing a missing third-party package.
            raise ModuleNotFoundError(name="another_missing_lib")
        raise ModuleNotFoundError(name=name)

    with caplog.at_level(logging.WARNING, logger="enzyme_tk_app.app.tools"):
        tools, modals = _run_discover_with_fake_tool(_import_with_bad_modal, monkeypatch)

    assert len(tools) == 1
    assert len(modals) == 0, "Modal with broken dependency should not be collected"
    assert any("missing dependency" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# 7. Callback logic — do the callback functions behave correctly?
# ---------------------------------------------------------------------------
# These tests call the *functions* defined in ``callbacks.py`` directly,
# mocking ``dash.ctx`` where needed.  They do not require a running Dash app.


def test_toggle_modal_opens_on_launch_click():
    """The modal must open when the launch button triggers the callback."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import toggle_reaction_similarity_modal

    with patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-launch-reaction-similarity"
        result = toggle_reaction_similarity_modal(1, 0, 0)

    assert result is True


def test_toggle_modal_closes_on_cancel_click():
    """The modal must close when the cancel button triggers the callback."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import toggle_reaction_similarity_modal

    with patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-reaction-cancel"
        result = toggle_reaction_similarity_modal(0, 1, 0)

    assert result is False


def test_toggle_modal_closes_on_submit_click():
    """The modal must close when the submit button triggers the callback."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import toggle_reaction_similarity_modal

    with patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-reaction-submit"
        result = toggle_reaction_similarity_modal(0, 0, 1)

    assert result is False


def test_populate_example_returns_value():
    """Selecting an example must populate the textarea with its SMILES."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import populate_example_reaction

    smiles = "CC(=O)O.CCO>>CC(=O)OCC.O"
    assert populate_example_reaction(smiles) == smiles


def test_populate_example_returns_empty_for_none():
    """Clearing the example dropdown must return an empty string."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import populate_example_reaction

    assert populate_example_reaction(None) == ""


def test_validate_form_disabled_when_both_empty():
    """Submit must be disabled when both fields are empty."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

    assert validate_reaction_form("", "") is True
    assert validate_reaction_form(None, None) is True


def test_validate_form_disabled_when_name_missing():
    """Submit must be disabled when query name is empty."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

    assert validate_reaction_form("", "CC>>CC") is True


def test_validate_form_disabled_when_smiles_missing():
    """Submit must be disabled when SMILES is empty."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

    assert validate_reaction_form("My Query", "") is True


def test_validate_form_enabled_when_both_filled():
    """Submit must be enabled when both fields have content."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

    assert validate_reaction_form("My Query", "CC>>CC") is False


def test_validate_form_disabled_when_whitespace_only():
    """Submit must be disabled when fields contain only whitespace."""
    from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

    assert validate_reaction_form("   ", "   ") is True


# ---------------------------------------------------------------------------
# 8. Substrate/Product Similarity callbacks
# ---------------------------------------------------------------------------


def test_subprod_toggle_modal_opens_on_launch_click():
    """The substrate/product modal must open when the launch button is clicked."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import (
        toggle_substrate_product_similarity_modal,
    )

    with patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-launch-substrate-product-similarity"
        result = toggle_substrate_product_similarity_modal(1, 0, 0)

    assert result is True


def test_subprod_toggle_modal_closes_on_cancel_click():
    """The substrate/product modal must close when the cancel button is clicked."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import (
        toggle_substrate_product_similarity_modal,
    )

    with patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-subprod-cancel"
        result = toggle_substrate_product_similarity_modal(0, 1, 0)

    assert result is False


def test_subprod_toggle_modal_closes_on_submit_click():
    """The substrate/product modal must close when the submit button is clicked."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import (
        toggle_substrate_product_similarity_modal,
    )

    with patch("enzyme_tk_app.app.tools.substrate_product_similarity.callbacks.ctx") as mock_ctx:
        mock_ctx.triggered_id = "id-btn-subprod-submit"
        result = toggle_substrate_product_similarity_modal(0, 0, 1)

    assert result is False


def test_subprod_populate_example_sets_smiles_and_role():
    """Selecting an example must populate both the SMILES field and the role selector."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    # Encoded as "role||smiles"
    smiles, role = populate_example_smiles("substrate||OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O")

    assert smiles == "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O"
    assert role == "substrate"


def test_subprod_populate_example_sets_product_role():
    """A product example must set the role to 'product'."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    smiles, role = populate_example_smiles("product||CCO")

    assert smiles == "CCO"
    assert role == "product"


def test_subprod_populate_example_returns_defaults_for_none():
    """Clearing the example dropdown must return empty SMILES and default role."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    smiles, role = populate_example_smiles(None)

    assert smiles == ""
    assert role == "substrate"


def test_subprod_populate_example_returns_defaults_for_invalid_value():
    """A value without the '||' separator must return empty SMILES and default role."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import populate_example_smiles

    smiles, role = populate_example_smiles("no-separator-here")

    assert smiles == ""
    assert role == "substrate"


def test_subprod_validate_form_disabled_when_both_empty():
    """Submit must be disabled when both fields are empty."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import validate_substrate_product_form

    assert validate_substrate_product_form("", "") is True
    assert validate_substrate_product_form(None, None) is True


def test_subprod_validate_form_disabled_when_name_missing():
    """Submit must be disabled when query name is empty."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import validate_substrate_product_form

    assert validate_substrate_product_form("", "CCO") is True


def test_subprod_validate_form_disabled_when_smiles_missing():
    """Submit must be disabled when SMILES is empty."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import validate_substrate_product_form

    assert validate_substrate_product_form("My Query", "") is True


def test_subprod_validate_form_enabled_when_both_filled():
    """Submit must be enabled when both fields have content."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import validate_substrate_product_form

    assert validate_substrate_product_form("Glucose search", "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O") is False


def test_subprod_validate_form_disabled_when_whitespace_only():
    """Submit must be disabled when fields contain only whitespace."""
    from enzyme_tk_app.app.tools.substrate_product_similarity.callbacks import validate_substrate_product_form

    assert validate_substrate_product_form("   ", "   ") is True
