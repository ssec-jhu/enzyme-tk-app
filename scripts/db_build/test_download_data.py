"""Tests for download_data.py — the downloader for the app's models and databases.

The script ships standalone, in a Docker image that does not have the app package installed,
so it is loaded by path (``load_db_build_script`` in conftest) rather than imported.

Nothing here reaches the network, needs the foldseek binary, or needs ``huggingface_hub``
installed: ``subprocess.run`` is replaced by a recorder that leaves behind the file foldseek
would have left, and ``huggingface_hub`` by a stand-in the download units import instead of
the real package.

The script duplicates several of the app's own checks — it cannot import the app — so the
app's constants are imported here and compared against the script's copies.  The two
disagreeing is the failure this file exists to catch: a database the app offers but the
report calls missing, or the reverse.
"""

import gzip
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import load_db_build_script

from enzyme_tk_app.app.tools.funce.check_data import _CHECKPOINT_STEM, EC_LEVELS
from enzyme_tk_app.app.utils.data_loading import REQUIRED_SEQUENCE_COLUMNS, SEQUENCE_DB_SUFFIXES

# Every path constant the script mirrors from the app's paths.py.
DIRECTORY_CONSTANTS = (
    "SEQUENCES_DIR",
    "REACTIONS_DIR",
    "FOLDSEEK_DB_DIR",
    "FOLDSEEK_WEIGHTS_DIR",
    "SEQUENCE_EMBEDDINGS_DIR",
    "FUNCE_MODELS_DIR",
    "UNIMOL_WEIGHTS_DIR",
)

# One entry per unit that downloads through foldseek: the function to call, the single file
# it looks for, the name it asks foldseek for, and where foldseek is told to write.  Paths
# are relative to the data directory.
FOLDSEEK_UNITS = [
    {
        "function": "download_foldseek_db_pdb",
        "marker": "foldseek_db/PDB/PDB.dbtype",
        "foldseek_name": "PDB",
        "destination": "foldseek_db/PDB/PDB",
    },
    {
        "function": "download_foldseek_db_afdb_swissprot",
        "marker": "foldseek_db/AFDB_SWISSPROT/AFDB_SWISSPROT.dbtype",
        "foldseek_name": "Alphafold/Swiss-Prot",
        "destination": "foldseek_db/AFDB_SWISSPROT/AFDB_SWISSPROT",
    },
    {
        "function": "download_prostt5_weights",
        "marker": "foldseek_models/weights/prostt5-f16.gguf",
        "foldseek_name": "ProstT5",
        "destination": "foldseek_models/weights",
    },
]
FOLDSEEK_UNIT_IDS = ["pdb", "afdb-swissprot", "prostt5"]


# Every test here loads the script, and the script reads $ETK_DATA_DIR and $HF_HOME as it is
# imported, so all of them start from the two being unset (see the fixture in conftest).
pytestmark = pytest.mark.usefixtures("db_build_environment")


@pytest.fixture
def script():
    """A freshly loaded copy of the script, so constants patched in one test cannot leak into another."""
    return load_db_build_script("download_data")


@pytest.fixture
def data_dir(script, tmp_path, monkeypatch):
    """Move the whole data directory to an empty tmp_path, keeping the real layout inside it.

    The constants are patched rather than $ETK_DATA_DIR: the script reads the environment
    once, at import, so a variable set afterwards would leave the functions pointing at the
    developer's real (and possibly populated) data directory.
    """
    for name in DIRECTORY_CONSTANTS:
        monkeypatch.setattr(script, name, tmp_path / getattr(script, name).relative_to(script.DATA_DIR))
    monkeypatch.setattr(script, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def hugging_face(monkeypatch):
    """Stand in for the huggingface_hub package, so no test needs it installed or online.

    Both download units import it inside the function body, so replacing the ``sys.modules``
    entry is enough to intercept them.  ``calls`` collects the keyword arguments of every
    ``snapshot_download``; nothing is cached until a test says otherwise.
    """
    calls = []

    def snapshot_download(**kwargs):
        calls.append(kwargs)
        # The real call leaves the checkpoint behind, and the unit exits if it is not there
        # afterwards, so the stand-in has to leave it too.
        local_dir, pattern = kwargs.get("local_dir"), kwargs.get("allow_patterns")
        if local_dir and pattern:
            checkpoint = Path(local_dir) / pattern
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_bytes(b"")
        return str(local_dir or "/hf-cache/snapshot")

    hub = SimpleNamespace(
        calls=calls,
        snapshot_download=snapshot_download,
        try_to_load_from_cache=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    return hub


def fake_foldseek(script, monkeypatch, creates=None):
    """Replace the foldseek binary with a recorder, and return the list of commands it is given.

    *creates* is the file the real ``foldseek databases`` would leave behind; it is written
    here because the script checks for it afterwards and exits if it is missing.  The
    attributes are patched on the modules themselves — the script does ``import subprocess``,
    so its own attribute is the only handle there is.
    """
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if creates is not None:
            creates.parent.mkdir(parents=True, exist_ok=True)
            creates.write_bytes(b"")
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(script.shutil, "which", lambda _: "/usr/local/bin/foldseek")
    monkeypatch.setattr(script.subprocess, "run", run)
    return commands


def write_sequence_table(path, columns):
    """Write a table with just a header row, gzipped and tab-separated as *path*'s name implies.

    Only the header is written because only the header decides whether a file is a sequence
    database.
    """
    delimiter = "\t" if path.name.removesuffix(".gz").endswith(".tsv") else ","
    text = delimiter.join(columns) + "\n"
    if path.name.endswith(".gz"):
        path.write_bytes(gzip.compress(text.encode()))
    else:
        path.write_text(text)
    return path


# ── FoldSeek downloads ───────────────────────────────────────────────────────


@pytest.mark.parametrize("unit", FOLDSEEK_UNITS, ids=FOLDSEEK_UNIT_IDS)
def test_a_foldseek_unit_reuses_what_is_already_on_disk(script, data_dir, monkeypatch, unit):
    """Re-running the script must cost nothing: with the file there, foldseek is never called.

    These are 2-6 GB downloads, and the script is meant to be re-run to see what a host has.
    """
    marker = data_dir / unit["marker"]
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"")
    commands = fake_foldseek(script, monkeypatch)

    getattr(script, unit["function"])()

    assert commands == []


@pytest.mark.parametrize("unit", FOLDSEEK_UNITS, ids=FOLDSEEK_UNIT_IDS)
def test_a_foldseek_unit_asks_for_the_database_by_foldseeks_own_name(script, data_dir, monkeypatch, unit):
    """foldseek's name for a database is not always the folder the app shows it under.

    AFDB_SWISSPROT is downloaded as "Alphafold/Swiss-Prot": send foldseek the folder name and
    it fails outright; write to foldseek's name and the app's dropdown never finds the result.
    """
    commands = fake_foldseek(script, monkeypatch, creates=data_dir / unit["marker"])

    getattr(script, unit["function"])()

    assert len(commands) == 1
    # The command's last argument is foldseek's scratch directory, whose name is random.
    assert commands[0][:4] == ["foldseek", "databases", unit["foldseek_name"], str(data_dir / unit["destination"])]


def test_an_interrupted_download_is_not_mistaken_for_a_finished_one(script, data_dir, monkeypatch):
    """The folder is not the check — one file inside it is.

    An interrupted download leaves the folder behind, which would read as FOUND right up
    until a search tried to open what is not in it.
    """
    marker = data_dir / "foldseek_db" / "PDB" / "PDB.dbtype"
    marker.parent.mkdir(parents=True)
    (marker.parent / "PDB_ss").write_bytes(b"half a download")
    commands = fake_foldseek(script, monkeypatch, creates=marker)

    script.download_foldseek_db_pdb()

    assert len(commands) == 1


def test_foldseek_exiting_zero_without_the_file_is_still_a_failure(script, data_dir, monkeypatch):
    """A download that reported success and left nothing behind has to stop the run.

    Taken on trust it would be reported as downloaded and fail hours later, inside a search,
    with nothing pointing back here.
    """
    fake_foldseek(script, monkeypatch)  # exits 0, writes nothing

    with pytest.raises(SystemExit) as excinfo:
        script.download_foldseek_db_pdb()

    assert str(data_dir / "foldseek_db" / "PDB" / "PDB.dbtype") in str(excinfo.value)


def test_a_host_without_the_foldseek_binary_is_told_so(script, data_dir, monkeypatch):
    """foldseek *is* the downloader here, not just the builder, so its absence is a message.

    Without the check the run ends in a FileNotFoundError from subprocess, which reads like
    a missing database rather than a missing program.
    """
    monkeypatch.setattr(script.shutil, "which", lambda _: None)

    with pytest.raises(SystemExit) as excinfo:
        script.download_foldseek_db_pdb()

    assert "foldseek" in str(excinfo.value)


# ── Hugging Face downloads ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cache_answer", "expected"),
    [("/hf-cache/models--esm3/esm3_sm_open_v1.pth", True), (None, False), (object(), False)],
    ids=["a-path", "nothing-cached", "known-to-be-absent"],
)
def test_esm3_counts_as_cached_only_when_the_cache_answers_with_a_path(script, hugging_face, cache_answer, expected):
    """``try_to_load_from_cache`` answers with a path, with None, or with a "known absent" sentinel.

    The sentinel is an object, so it is truthy: a ``bool()`` check here would call a
    checkpoint present that is not, and the build would fail much later, inside the worker.
    """
    hugging_face.try_to_load_from_cache = lambda *args, **kwargs: cache_answer

    assert script.esm3_is_cached() is expected


def test_the_esm3_check_survives_a_host_without_huggingface_hub(script, monkeypatch):
    """``report()`` must run with nothing but the standard library.

    A host that only wants the FoldSeek databases has no reason to have huggingface_hub
    installed, and an ImportError there would take the whole report down with it.
    """
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)  # makes `from huggingface_hub import …` raise

    assert script.esm3_is_cached() is False


@pytest.mark.parametrize("cached", [True, False], ids=["already-cached", "cache-empty"])
def test_esm3_weights_are_fetched_only_when_the_cache_is_empty(script, hugging_face, monkeypatch, cached):
    """A populated cache means no request at all — 5.4 GB is not re-fetched on every build.

    What is fetched is the whole repository rather than the one checkpoint, because
    ESM3.from_pretrained reaches for the rest of it on its own.
    """
    monkeypatch.setattr(script, "esm3_is_cached", lambda: cached)

    script.download_esm3_weights()

    assert hugging_face.calls == ([] if cached else [{"repo_id": script.ESM3_REPO}])


def test_unimol_weights_are_not_fetched_again_when_the_checkpoint_is_there(script, data_dir, hugging_face):
    """The checkpoint on disk is the check, so a fresh container reuses it instead of re-downloading."""
    checkpoint = data_dir / "unimol_weights" / script.UNIMOL_CHECKPOINT
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"")

    script.download_unimol_weights()

    assert hugging_face.calls == []


def test_unimol_fetches_only_the_164m_checkpoint(script, data_dir, hugging_face):
    """The repository holds five model sizes; without allow_patterns all five are downloaded.

    ``local_dir`` is named for the same reason: Func-E points unimol_tools at this exact
    directory, and without it the package fetches its own copy into site-packages instead.
    """
    script.download_unimol_weights()

    assert hugging_face.calls == [
        {
            "repo_id": script.UNIMOL_REPO,
            "local_dir": data_dir / "unimol_weights",
            "allow_patterns": script.UNIMOL_CHECKPOINT,
        }
    ]


def test_a_unimol_download_that_leaves_no_checkpoint_is_a_failure(script, data_dir, hugging_face):
    """A finished download with nothing under it stops here rather than at the first Func-E job.

    The data mount is read-only in the app, so a wrongly laid-out unimol_weights/ cannot be
    repaired at run time.
    """
    hugging_face.snapshot_download = lambda **kwargs: "/hf-cache/snapshot"  # leaves nothing behind

    with pytest.raises(SystemExit) as excinfo:
        script.download_unimol_weights()

    assert script.UNIMOL_CHECKPOINT in str(excinfo.value)


# ── Func-E ensemble ──────────────────────────────────────────────────────────


def test_the_funce_files_are_exactly_the_ones_the_app_requires(script, data_dir):
    """The script cannot import the app, so this is where the two lists of filenames are compared.

    tools/funce/check_data.py refuses to run the tool unless these eight files are present:
    a name that drifted apart would be reported here as a complete ensemble and by the app
    as a missing one.
    """
    expected = {
        f"{_CHECKPOINT_STEM.format(ec=ec)}_{suffix}" for ec in EC_LEVELS for suffix in ("conf.pkl", "checkpoint.pth")
    }
    files = script.funce_model_files()

    assert len(files) == 8  # a config and a checkpoint for each of the four EC levels
    assert {path.name for path in files} == expected
    assert {path.parent for path in files} == {data_dir / "funce_models"}


@pytest.mark.parametrize(
    ("levels_present", "expected_line"),
    [
        (EC_LEVELS, "Func-E ensemble: FOUND"),
        (EC_LEVELS[:-1], "Func-E ensemble: NOT FOUND"),
        ((), "Func-E ensemble: NOT FOUND"),
    ],
    ids=["complete", "three-of-four", "nothing-at-all"],
)
def test_anything_short_of_the_whole_funce_ensemble_is_reported_as_missing(
    script, data_dir, capsys, levels_present, expected_line
):
    """Three of four EC levels is missing, not mostly there — the same line check_data.py draws.

    Func-E loads one model per EC level, so an incomplete set still runs and silently
    predicts from a different ensemble than the results claim.  Every absent file is named,
    because there is no download yet and they have to be copied in by hand.
    """
    script.FUNCE_MODELS_DIR.mkdir()
    for ec in levels_present:
        for suffix in ("conf.pkl", "checkpoint.pth"):
            (script.FUNCE_MODELS_DIR / f"{script.FUNCE_CHECKPOINT_STEM.format(ec=ec)}_{suffix}").write_bytes(b"")

    script.check_funce_models()

    output = capsys.readouterr().out
    assert expected_line in output
    for path in script.funce_model_files():
        if not path.exists():
            assert str(path) in output


# ── Sequence databases ───────────────────────────────────────────────────────


def test_the_sequence_database_contract_matches_the_apps(script):
    """The script duplicates this contract because it cannot import the app; the two must agree.

    Diverge, and the report calls a database missing that the app is happily offering — or
    tells someone their file is fine when no dropdown will ever show it.
    """
    assert script.SEQUENCE_DB_SUFFIXES == SEQUENCE_DB_SUFFIXES
    assert script.REQUIRED_SEQUENCE_COLUMNS == REQUIRED_SEQUENCE_COLUMNS


@pytest.mark.parametrize("suffix", SEQUENCE_DB_SUFFIXES, ids=[s.lstrip(".") for s in SEQUENCE_DB_SUFFIXES])
def test_a_sequence_database_is_recognised_in_every_format_the_app_accepts(script, data_dir, suffix):
    """CSV or TSV, plain or gzipped — all four are databases to the app, so all four count here."""
    script.SEQUENCES_DIR.mkdir()
    write_sequence_table(script.SEQUENCES_DIR / f"enzymes{suffix}", REQUIRED_SEQUENCE_COLUMNS)

    assert script.has_sequence_database() is True


@pytest.mark.parametrize(
    "missing_column",
    REQUIRED_SEQUENCE_COLUMNS,
    ids=[f"without-{column.replace(' ', '-')}" for column in REQUIRED_SEQUENCE_COLUMNS],
)
def test_a_table_missing_a_required_column_is_not_a_database(script, data_dir, missing_column):
    """The header is the contract, not the extension — the app would not offer this file either.

    Calling sequences/ satisfied when nothing in it can be searched is the one answer that
    sends someone looking in the wrong place.
    """
    script.SEQUENCES_DIR.mkdir()
    columns = [column for column in REQUIRED_SEQUENCE_COLUMNS if column != missing_column]
    write_sequence_table(script.SEQUENCES_DIR / "enzymes.csv", columns)

    assert script.has_sequence_database() is False


def test_a_file_that_is_not_a_delimited_table_is_not_a_database(script, data_dir):
    """The right columns in a .txt still count for nothing: the extension is checked as well."""
    script.SEQUENCES_DIR.mkdir()
    write_sequence_table(script.SEQUENCES_DIR / "enzymes.txt", REQUIRED_SEQUENCE_COLUMNS)

    assert script.has_sequence_database() is False


@pytest.mark.parametrize(
    ("filename", "content"),
    [("broken.csv.gz", b"this was never gzipped"), ("binary.csv", b"\xff\xfe\x00\x01")],
    ids=["not-really-gzipped", "not-text-at-all"],
)
def test_a_file_that_cannot_be_read_is_skipped_rather_than_raising(script, data_dir, filename, content):
    """Anything can be dropped into sequences/, and one bad file must not take the report down.

    Both names sort before the good database below, so a raise here would also hide a
    perfectly usable file that had not been reached yet.
    """
    script.SEQUENCES_DIR.mkdir()
    (script.SEQUENCES_DIR / filename).write_bytes(content)

    assert script.has_sequence_database() is False

    write_sequence_table(script.SEQUENCES_DIR / "enzymes.csv", REQUIRED_SEQUENCE_COLUMNS)
    assert script.has_sequence_database() is True


@pytest.mark.parametrize("create_directory", [False, True], ids=["no-directory-at-all", "empty-directory"])
def test_there_is_no_sequence_database_when_there_is_nothing_to_read(script, data_dir, create_directory):
    """A directory that is not there and one with nothing in it are the same answer to the user."""
    if create_directory:
        script.SEQUENCES_DIR.mkdir()

    assert script.has_sequence_database() is False


# ── Report ───────────────────────────────────────────────────────────────────


def write_every_data_item(script):
    """Put one of everything ``report()`` looks for into the data directory."""
    script.SEQUENCES_DIR.mkdir(parents=True)
    write_sequence_table(script.SEQUENCES_DIR / "enzymes.csv", REQUIRED_SEQUENCE_COLUMNS)

    script.REACTIONS_DIR.mkdir(parents=True)
    (script.REACTIONS_DIR / "reactions.csv").write_text("id,unmapped\n")

    (script.FOLDSEEK_DB_DIR / "PDB").mkdir(parents=True)

    script.FOLDSEEK_WEIGHTS_DIR.mkdir(parents=True)
    (script.FOLDSEEK_WEIGHTS_DIR / script.PROSTT5_WEIGHTS_FILE).write_bytes(b"")

    script.SEQUENCE_EMBEDDINGS_DIR.mkdir(parents=True)
    (script.SEQUENCE_EMBEDDINGS_DIR / "enzymes.pkl").write_bytes(b"")

    script.FUNCE_MODELS_DIR.mkdir(parents=True)
    for path in script.funce_model_files():
        path.write_bytes(b"")

    checkpoint = script.UNIMOL_WEIGHTS_DIR / script.UNIMOL_CHECKPOINT
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"")


def report_statuses(output):
    """The OK / MISSING word from each item line ``report()`` printed."""
    return [line.split()[0] for line in output.splitlines() if line.startswith(("  OK", "  MISSING"))]


@pytest.mark.parametrize("populated", [False, True], ids=["empty-data-directory", "everything-present"])
def test_report_marks_every_item_against_the_data_directory(script, data_dir, monkeypatch, capsys, populated):
    """The report is where someone reads off what this host has, so no item may go unlisted.

    Eight of them: the seven directories, plus the ESM3 cache that only the build script uses.
    """
    monkeypatch.setattr(script, "esm3_is_cached", lambda: populated)
    if populated:
        write_every_data_item(script)

    script.report()

    output = capsys.readouterr().out
    assert report_statuses(output) == ["OK" if populated else "MISSING"] * 8
    assert str(data_dir) in output  # the directory it answered for, so a mount typo is visible


# ── Where the data directory is ──────────────────────────────────────────────


def test_the_data_directory_follows_etk_data_dir(tmp_path, monkeypatch):
    """The app reads $ETK_DATA_DIR too, so a deployment that already sets it needs no edit here.

    Loaded fresh because the variable is read once, when the script is imported.
    """
    monkeypatch.setenv("ETK_DATA_DIR", str(tmp_path))

    script = load_db_build_script("download_data")

    assert script.DATA_DIR == tmp_path
    for name in DIRECTORY_CONSTANTS:
        assert tmp_path in getattr(script, name).parents, f"{name} must sit under DATA_DIR"


def test_the_data_directory_defaults_to_the_one_in_the_repository():
    """With nothing set, a run on the host writes where the app already looks — no copying afterwards."""
    script = load_db_build_script("download_data")

    # The app's own data directory: this file sits two levels below the repository root.
    repository_root = Path(__file__).resolve().parents[2]
    assert script.DATA_DIR == repository_root / "enzyme_tk_app" / "app" / "data"


def test_the_hugging_face_cache_sits_inside_the_data_directory_by_default(tmp_path, monkeypatch):
    """One mount then carries the 5.4 GB ESM3 snapshot, so `docker run --rm` cannot throw it away.

    HF_HOME is exported as well as read: huggingface_hub freezes its cache paths when it is
    imported, so this is the one place the location can still be decided — for this script
    and for build_enzyme_db.py, which imports it.
    """
    monkeypatch.setenv("ETK_DATA_DIR", str(tmp_path))

    script = load_db_build_script("download_data")

    assert script.HF_CACHE_DIR == tmp_path / ".hf_cache"
    assert os.environ["HF_HOME"] == str(script.HF_CACHE_DIR)


def test_a_host_with_its_own_hugging_face_cache_keeps_it(tmp_path, monkeypatch):
    """A machine with a shared model cache reuses it instead of downloading 5.4 GB it already has."""
    shared_cache = tmp_path / "shared-hf-cache"
    monkeypatch.setenv("HF_HOME", str(shared_cache))
    monkeypatch.setenv("ETK_DATA_DIR", str(tmp_path / "data"))

    script = load_db_build_script("download_data")

    assert script.HF_CACHE_DIR == shared_cache
