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
from dash import dcc, html

from enzyme_tk_app.app.tools import TOOLS, ToolDef, _discover_tools, _modal_funcs, tool_modals

from .conftest import find_components, get_text

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
# Discovery — is every tool folder picked up correctly?
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
# ToolDef shape — does each tool have the right fields?
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
# Modals — do modal dialogs load correctly?
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


def test_every_databases_dropdown_has_an_info_tooltip():
    """A Databases dropdown must ship an info tooltip describing its contents."""
    for modal in tool_modals().children or []:
        slug = str(getattr(modal, "id", "")).removeprefix("id-modal-")
        dropdowns = [str(d.id) for d in find_components(modal, dcc.Dropdown) if getattr(d, "id", None)]
        if not any(d.endswith("-databases") for d in dropdowns):
            continue  # Not a database-backed tool (e.g. the timer template).

        target = f"id-icon-{slug}-databases-info"
        tooltips = [t for t in find_components(modal, dbc.Tooltip) if t.target == target]
        assert len(tooltips) == 1, f"{slug}: Databases row has no info tooltip"
        assert get_text(tooltips[0]).strip(), f"{slug}: Databases info tooltip is empty"


# ---------------------------------------------------------------------------
# Callbacks — do callback modules load without errors?
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


def test_every_example_prefills_a_task_name():
    """Selecting any example must prefill a non-blank Task Name.

    Task Name is the one field that blocks submit, so an example that leaves it
    blank is not runnable in one click — the whole point of the example picker.
    Walking the live dropdowns rather than listing the example dicts here means
    a newly added example, or a whole new tool, is checked the moment it shows
    up.  Every ``populate_example_*`` callback returns the Task Name last.

    The name carries no tool prefix — the My Tasks table already has a Tool
    column beside Task Name — so there is no shape to assert beyond non-blank.
    """
    for modal in tool_modals().children or []:
        slug = str(getattr(modal, "id", "")).removeprefix("id-modal-")
        dropdowns = [d for d in find_components(modal, dcc.Dropdown) if str(getattr(d, "id", "")).endswith("-example")]
        if not dropdowns:
            continue  # Tool ships no examples.

        module = importlib.import_module(f"enzyme_tk_app.app.tools.{slug.replace('-', '_')}.callbacks")
        populate = next(fn for name, fn in vars(module).items() if name.startswith("populate_example"))

        for option in dropdowns[0].options:
            task_name = populate(option["value"])[-1]
            label = option["label"]
            assert isinstance(task_name, str), f"{slug}: example '{label}' prefilled no Task Name"
            assert task_name.strip(), f"{slug}: example '{label}' prefilled a blank Task Name"


def _smiles_tools():
    """Yield ``(slug, modal, callbacks module)`` for every tool that takes a structure.

    A SMILES tool is one whose modal carries an ``id-textarea-<slug>-smiles``;
    the sequence tools use ``-sequence``, so they are skipped and their protein
    examples are never handed to a SMILES parser.
    """
    for modal in tool_modals().children or []:
        slug = str(getattr(modal, "id", "")).removeprefix("id-modal-")
        textareas = [t for t in find_components(modal, dbc.Textarea) if str(getattr(t, "id", "")).endswith("-smiles")]
        if not textareas:
            continue

        yield slug, modal, importlib.import_module(f"enzyme_tk_app.app.tools.{slug.replace('-', '_')}.callbacks")


def _tools_with_callbacks():
    """Yield ``(slug, callbacks module)`` for every discovered tool that has callbacks."""
    for tool in TOOLS:
        slug = tool["slug"]
        try:
            yield slug, importlib.import_module(f"enzyme_tk_app.app.tools.{slug.replace('-', '_')}.callbacks")
        except ModuleNotFoundError:
            continue


def test_every_tool_checks_its_data_before_running():
    """Every tool's callbacks must import the data-availability guard.

    A tool that skips it is a submission endpoint that accepts jobs it cannot run:
    Run stays enabled, the job is queued, and the failure surfaces minutes later in
    the worker as a stack trace about a missing file — instead of one line in the
    modal, before anything is submitted.  Walking the live registry means tool #7
    is held to this the moment it appears.

    An import check has teeth here because ``tox run -e format`` removes unused
    imports (F401), so the symbol cannot survive as decoration — but it cannot see
    *where* the guard is called.  That half is covered behaviourally in
    ``test_tools_timer.py``.
    """
    checked = 0
    for slug, module in _tools_with_callbacks():
        assert getattr(module, "validate_tool_data", None) is not None, (
            f"{slug}: callbacks.py does not import validate_tool_data from "
            "utils.data_availability — this tool accepts jobs it has no data to run"
        )
        checked += 1

    assert checked, "No tool with callbacks was found — discovery must have changed"


def test_every_tool_enforces_the_active_job_limit():
    """Every tool's submit path must import the per-session job cap.

    The cap is only as good as its weakest tool: one tool that skips it is an
    unlimited submission endpoint, and nothing else in the app would notice.
    Walking the live registry means tool #7 is held to this the moment it appears.

    An import check has teeth here because ``tox run -e format`` removes unused
    imports (F401), so the symbol cannot survive as decoration — but it cannot tell
    a guard placed before ``submit_job`` from one placed after it.  That half is
    covered behaviourally in ``test_tools_timer.py``.
    """
    checked = 0
    for slug, module in _tools_with_callbacks():
        assert getattr(module, "validate_active_job_limit", None) is not None, (
            f"{slug}: callbacks.py does not import validate_active_job_limit from "
            "utils.submission_limits — this tool is an uncapped submission endpoint"
        )
        checked += 1

    assert checked, "No tool with callbacks was found — discovery must have changed"


def test_every_tool_verifies_the_captcha():
    """Every tool's submit path must import the production captcha guard.

    Same reasoning as the job cap above, one bypass further out.  The cap is keyed on a session
    cookie the client can simply discard; the captcha is what makes discarding it cost a proof
    of work.  A tool that skips it is exactly the endpoint the cap was trying to close.

    An import check has teeth because ``tox run -e format`` removes unused imports (F401), so
    the symbol cannot survive as decoration — but it cannot tell a guard placed before
    ``submit_job`` from one placed after it.  That half is covered behaviourally in
    ``test_tools_timer.py``.
    """
    checked = 0
    for slug, module in _tools_with_callbacks():
        assert getattr(module, "validate_captcha", None) is not None, (
            f"{slug}: callbacks.py does not import validate_captcha from utils.captcha — "
            "this tool can be submitted by a bot that discards its session cookie"
        )
        checked += 1

    assert checked, "No tool with callbacks was found — discovery must have changed"


def test_every_modal_carries_a_captcha_store():
    """Every tool modal must render the Store its submit callback reads as State.

    The guard above is only reachable if the modal actually supplies a payload.  A tool that
    imports ``validate_captcha`` but renders no Store would pass the import walk and then, in
    production, refuse every submission forever — and in *local* mode it is worse than that: a
    ``State`` pointing at a component absent from the layout stops the callback firing at all,
    so Run would be dead for everyone.  That is why the Store is rendered unconditionally while
    the widget holder is production-only.
    """
    checked = 0
    for modal in tool_modals().children or []:
        slug = str(getattr(modal, "id", "")).removeprefix("id-modal-")
        stores = [
            s for s in find_components(modal, dcc.Store) if str(getattr(s, "id", "")) == f"id-store-{slug}-captcha"
        ]
        assert len(stores) == 1, f"{slug}: modal must render exactly one id-store-{slug}-captcha, found {len(stores)}"
        checked += 1

    assert checked, "No tool modal was found — discovery must have changed"


def test_every_tool_links_to_my_tasks_on_success():
    """Every tool's submit path must import the shared success block.

    The job ID alone is a dead end: the modal stays open after Run, so without
    the block's My Tasks link nothing on screen tells a first-time user their
    job is now tracked anywhere.  Walking the live registry means tool #7 is
    held to this the moment it appears.

    An import check has teeth here because ``tox run -e format`` removes unused
    imports (F401), so the symbol cannot survive as decoration — but it cannot
    see that the block is returned on the *success* path, nor that its link
    points at ``/my-tasks``.  That half is covered behaviourally in
    ``test_tools_timer.py``.
    """
    checked = 0
    for slug, module in _tools_with_callbacks():
        assert getattr(module, "build_submission_success", None) is not None, (
            f"{slug}: callbacks.py does not import build_submission_success from "
            "components.modal_helpers — this tool's submit message is a dead end"
        )
        checked += 1

    assert checked, "No tool with callbacks was found — discovery must have changed"


def test_every_tool_wraps_its_submit_errors():
    """Every tool's submit path must import the shared error row.

    The results div carries no styling of its own, so a validator message
    returned bare renders as ordinary body text — no box, no colour, no icon.
    A tool that skips the helper silently degrades every one of its validation
    messages, which is exactly the class of bug nothing else would report.

    An import check has teeth because ``tox run -e format`` removes unused
    imports (F401), so the symbol cannot survive as decoration — but it cannot
    see that *every* error branch is wrapped.  That half is covered
    behaviourally in each tool's own test file, via
    ``conftest.submission_error_text``, which asserts the row's class.
    """
    checked = 0
    for slug, module in _tools_with_callbacks():
        assert getattr(module, "build_submission_error", None) is not None, (
            f"{slug}: callbacks.py does not import build_submission_error from "
            "components.modal_helpers — this tool's validation messages render unstyled"
        )
        checked += 1

    assert checked, "No tool with callbacks was found — discovery must have changed"


def test_every_smiles_field_is_validated():
    """A tool that takes a structure must import a validator into its callbacks.

    The Run button is only as good as the check behind it: without one, a typo
    is accepted, submitted, and either dies in the worker or — for the reaction
    tools, whose enzymetk step reads the query as SMARTS — comes back as a
    successful job full of meaningless scores.  Walking the live modals means a
    new SMILES tool is held to this the moment it appears.
    """
    checked = 0
    for slug, _modal, module in _smiles_tools():
        validator = getattr(module, "validate_reaction_smiles", None) or getattr(module, "validate_smiles", None)
        assert validator is not None, (
            f"{slug}: has a SMILES field but its callbacks.py imports no validator "
            "from utils.smiles_validation — the Run button cannot be gating on it"
        )
        checked += 1

    assert checked, "No SMILES tool was found — the id-textarea-<slug>-smiles convention must have changed"


def test_every_smiles_field_debounces():
    """A SMILES textarea must send its value on a pause, not on every keystroke.

    Validating per keystroke puts several callback round-trips in flight at once,
    and the field ends up showing whichever verdict landed last — reproducibly, an
    earlier keystroke's, so a corrected structure stays marked invalid.  The value
    must be a **number** of milliseconds: ``True`` would defer to blur and leave
    Run disabled under a click that arrives first.

    A unit test cannot catch the race itself; it can stop the fix being removed.
    """
    checked = 0
    for slug, modal, _module in _smiles_tools():
        for textarea in find_components(modal, dbc.Textarea):
            if not str(getattr(textarea, "id", "")).endswith("-smiles"):
                continue
            debounce = getattr(textarea, "debounce", None)
            assert isinstance(debounce, int | float) and not isinstance(debounce, bool), (
                f"{slug}: SMILES textarea has debounce={debounce!r}; it must be a number of "
                "milliseconds so a burst of keystrokes cannot strand an earlier verdict"
            )
            assert debounce > 0
            checked += 1

    assert checked, "No SMILES textarea was found — the id-textarea-<slug>-smiles convention must have changed"


def test_every_example_smiles_passes_its_own_tools_validator():
    """An example the modal offers must survive the gate that tool puts on Run.

    Read off the live dropdowns and through the tool's own
    ``populate_example_*`` callback — which returns the SMILES first — so an
    example is checked exactly as the user's click delivers it.  Otherwise a
    shipped example could leave Run disabled with no way to tell why.
    """
    for slug, modal, module in _smiles_tools():
        validator = getattr(module, "validate_reaction_smiles", None) or getattr(module, "validate_smiles", None)
        dropdowns = [d for d in find_components(modal, dcc.Dropdown) if str(getattr(d, "id", "")).endswith("-example")]
        if not dropdowns:
            continue  # Tool ships no examples.

        populate = next(fn for name, fn in vars(module).items() if name.startswith("populate_example"))

        for option in dropdowns[0].options:
            smiles = populate(option["value"])[0]
            message = validator(smiles)
            assert message is None, f"{slug}: example '{option['label']}' is rejected by its own validator: {message}"


# ---------------------------------------------------------------------------
# Regression guards — protect against common mistakes
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
# Discovery error paths — does _discover_tools handle failures gracefully?
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
# Callback logic — do the callback functions behave correctly?
# ---------------------------------------------------------------------------
# These tests call the *functions* defined in ``callbacks.py`` directly,
# mocking ``dash.ctx`` where needed.  They do not require a running Dash app.


# def test_toggle_modal_opens_on_launch_click():
#     """The modal must open when the launch button triggers the callback."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import toggle_reaction_similarity_modal

#     with patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx:
#         mock_ctx.triggered_id = "id-btn-launch-reaction-similarity"
#         result = toggle_reaction_similarity_modal(1, 0)

#     assert result is True


# def test_toggle_modal_closes_on_cancel_click():
#     """The modal must close when the cancel button triggers the callback."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import toggle_reaction_similarity_modal

#     with patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx:
#         mock_ctx.triggered_id = "id-btn-reaction-similarity-cancel"
#         result = toggle_reaction_similarity_modal(0, 1)

#     assert result is False


# def test_toggle_modal_stays_closed_for_non_launch_trigger():
#     """The modal must stay closed for any trigger other than the launch button."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import toggle_reaction_similarity_modal

#     with patch("enzyme_tk_app.app.tools.reaction_similarity.callbacks.ctx") as mock_ctx:
#         mock_ctx.triggered_id = "id-btn-reaction-similarity-submit"
#         result = toggle_reaction_similarity_modal(0, 0)

#     assert result is False


# def test_populate_example_returns_value():
#     """Selecting an example must populate the textarea with its SMILES."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import populate_example_reaction

#     smiles = "CC(=O)O.CCO>>CC(=O)OCC.O"
#     assert populate_example_reaction(smiles) == smiles


# def test_populate_example_returns_empty_for_none():
#     """Clearing the example dropdown must raise PreventUpdate."""
#     from dash.exceptions import PreventUpdate

#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import populate_example_reaction

#     with pytest.raises(PreventUpdate):
#         populate_example_reaction(None)


# def test_validate_form_disabled_when_both_empty():
#     """Submit must be disabled when both fields are empty."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

#     assert validate_reaction_form("", "", ["db.csv"], ["tanimoto"]) is True
#     assert validate_reaction_form(None, None, ["db.csv"], ["tanimoto"]) is True


# def test_validate_form_disabled_when_name_missing():
#     """Submit must be disabled when task name is empty."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

#     assert validate_reaction_form("", "CC>>CC", ["db.csv"], ["tanimoto"]) is True


# def test_validate_form_disabled_when_smiles_missing():
#     """Submit must be disabled when SMILES is empty."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

#     assert validate_reaction_form("My Query", "", ["db.csv"], ["tanimoto"]) is True


# def test_validate_form_enabled_when_both_filled():
#     """Submit must be enabled when all fields have content."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

#     assert validate_reaction_form("My Query", "CC>>CC", ["db.csv"], ["tanimoto"]) is False


# def test_validate_form_disabled_when_whitespace_only():
#     """Submit must be disabled when fields contain only whitespace."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

#     assert validate_reaction_form("   ", "   ", ["db.csv"], ["tanimoto"]) is True


# def test_validate_form_disabled_when_no_databases():
#     """Submit must be disabled when no databases are selected."""
#     from enzyme_tk_app.app.tools.reaction_similarity.callbacks import validate_reaction_form

#     assert validate_reaction_form("My Query", "CC>>CC", [], ["tanimoto"]) is True
#     assert validate_reaction_form("My Query", "CC>>CC", None, ["tanimoto"]) is True
