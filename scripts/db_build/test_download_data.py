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
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from functools import partial
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

# The staging directory download_funce_models() fetches the archive into.  Dotted so the app's
# *.pkl scans never see it, and persistent so an interrupted 1.35 GB download can resume.
FUNCE_STAGING_DIR = ".download"


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

    Every download unit imports it inside the function body, so replacing the ``sys.modules``
    entry is enough to intercept them.  ``calls`` collects the keyword arguments of every
    ``snapshot_download``; nothing is cached until a test says otherwise.

    ``hf_hub_download`` is deliberately left off: the ``fake_download`` fixture below adds it,
    so a unit that reaches for the project's dataset repository in a test that set no download
    up fails with an AttributeError rather than quietly finding a stand-in.
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


@pytest.fixture
def fake_download(hugging_face):
    """Give the huggingface_hub stand-in an ``hf_hub_download``, so no test reaches the network.

    ``filenames`` collects the file each request asked for, so a test can assert that nothing
    was fetched at all; ``calls`` keeps the whole keyword arguments for the one test that is
    about how the request is addressed.  ``archive`` is the file the stand-in lands at the
    destination, standing in for whatever the dataset repository would have served — the Func-E
    zip, or the EnzymeMap CSV.  A test that expects no download leaves it as ``None``, and any
    request then fails loudly rather than silently reporting success.
    """
    download = SimpleNamespace(calls=[], filenames=[], archive=None)

    def hf_hub_download(**kwargs):
        download.calls.append(kwargs)
        download.filenames.append(kwargs["filename"])
        if download.archive is None:
            raise AssertionError(f"nothing should have been downloaded, but got: {kwargs['filename']}")
        # The real call creates local_dir and returns where it put the file; both are what the
        # caller goes on to unpack, so the stand-in has to do the same.
        landed = Path(kwargs["local_dir"]) / Path(kwargs["filename"]).name
        landed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(download.archive, landed)
        return str(landed)

    hugging_face.hf_hub_download = hf_hub_download
    return download


def write_archive(path, member_names):
    """Write a real archive at *path* holding an empty file per name in *member_names*.

    The format follows the suffix, because that is how the script picks its branch: a file
    ending in ``.zip`` is unpacked by ``zipfile``, anything else by ``tarfile``.  The
    members are empty because only their names and their landing place are under test.
    """
    if path.name.endswith(".zip"):
        with zipfile.ZipFile(path, "w") as bundle:
            for name in member_names:
                bundle.writestr(name, b"")
    else:
        with tarfile.open(path, "w:gz") as bundle:
            for name in member_names:
                bundle.addfile(tarfile.TarInfo(name), io.BytesIO(b""))
    return path


def record_every_unit(script, monkeypatch):
    """Swap every download unit for a recorder, and return the list it appends its name to.

    The ``UNITS`` dict holds direct references to the functions, so patching the functions
    themselves would leave the dict pointing at the real downloads — the dict is what
    ``main()`` reads, so the dict is what is replaced.
    """
    units_run = []

    def record(name):
        units_run.append(name)

    monkeypatch.setattr(script, "UNITS", {name: partial(record, name) for name in script.UNITS})
    # report() runs after every invocation, and a run that selected esm3 would otherwise ask
    # the Hugging Face cache about a directory this test never set up.
    monkeypatch.setattr(script, "esm3_is_cached", lambda: False)
    return units_run


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


def test_the_shipped_script_names_the_files_it_downloads(script):
    """The shipped state is "configured": every clone downloads from these three constants.

    An empty or misspelled one turns a download into a failure a long way from here: an empty
    repository id never resolves to a repository at all, and a filename with no archive suffix
    drops through ``_extract_archive`` into its tar branch.  Clones run on these values, so
    these are the ones that have to be right — every test below sets its own.
    """
    owner, _, name = script.HUGGING_FACE_DATASET_REPO.partition("/")

    assert owner and name, "the dataset repository must be named owner/name"
    # The suffix is what picks the branch in _extract_archive; nothing else unpacks anything.
    assert script.FUNCE_MODELS_FILE.endswith((".zip", ".tar.gz"))
    # report() and both reaction tools look for reactions/*.csv, so the reference has to be one.
    assert script.REACTIONS_FILE.endswith(".csv")


def test_a_dataset_file_is_requested_from_the_projects_own_dataset_repository(script, fake_download, tmp_path):
    """A dataset repository has to be asked for as one — ``repo_type="dataset"``.

    Left at the default the Hub looks the file up in the *model* index, and answers with a bare
    404 that reads as "the file is gone" rather than "you asked the wrong index".  This is the
    one assertion that catches the next dataset file wired up with the wrong type.  The path
    that comes back is what ``download_funce_models`` goes on to unpack.
    """
    destination = tmp_path / "landing"
    fake_download.archive = write_archive(tmp_path / "published.zip", ["run_1_conf.pkl"])

    landed = script.fetch_dataset_file_from_hugging_face(script.FUNCE_MODELS_FILE, destination)

    assert fake_download.calls == [
        {
            "repo_id": script.HUGGING_FACE_DATASET_REPO,
            "filename": script.FUNCE_MODELS_FILE,
            "repo_type": "dataset",
            "local_dir": str(destination),
        }
    ]
    assert landed == destination / script.FUNCE_MODELS_FILE


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


def place_funce_models(script, levels_present):
    """Write an empty config and checkpoint into funce_models/ for each EC level given."""
    script.FUNCE_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for ec in levels_present:
        for suffix in ("conf.pkl", "checkpoint.pth"):
            (script.FUNCE_MODELS_DIR / f"{script.FUNCE_CHECKPOINT_STEM.format(ec=ec)}_{suffix}").write_bytes(b"")


def publish_funce_archive(script, fake_download, tmp_path, members=None):
    """Hand the download stand-in an archive of *members*, as the dataset repository serves it.

    It is named FUNCE_MODELS_FILE because that suffix is what picks the branch in
    ``_extract_archive``.  *members* defaults to the whole ensemble — every case but the
    deliberately incomplete one wants all eight files.
    """
    if members is None:
        members = [path.name for path in script.funce_model_files()]
    release = tmp_path / "release"
    release.mkdir()
    fake_download.archive = write_archive(release / script.FUNCE_MODELS_FILE, members)


@pytest.mark.parametrize(
    ("levels_present", "expected_line", "expects_download"),
    [
        (EC_LEVELS, "Func-E ensemble: FOUND", False),
        (EC_LEVELS[:-1], "Func-E ensemble: NOT FOUND", True),
        ((), "Func-E ensemble: NOT FOUND", True),
    ],
    ids=["complete", "three-of-four", "nothing-at-all"],
)
def test_anything_short_of_the_whole_funce_ensemble_is_downloaded_again(
    script, data_dir, fake_download, tmp_path, capsys, levels_present, expected_line, expects_download
):
    """Three of four EC levels is missing, not mostly there — the same line check_data.py draws.

    Func-E loads one model per EC level, so an incomplete set still runs and silently predicts
    from a different ensemble than the results claim; the only safe answer is to fetch the
    archive again.  The complete case is the other half, and the one that has to cost nothing:
    1.35 GB is not re-downloaded every time the script is re-run to see what a host has, so it
    leaves ``archive`` unset and any request at all fails on the spot.
    """
    place_funce_models(script, levels_present)
    if expects_download:
        publish_funce_archive(script, fake_download, tmp_path)

    script.download_funce_models()

    assert expected_line in capsys.readouterr().out
    assert fake_download.filenames == ([script.FUNCE_MODELS_FILE] if expects_download else [])


@pytest.mark.parametrize("suffix", [".tar.gz", ".zip"], ids=["tar-gz", "zip"])
def test_a_published_archive_is_fetched_and_unpacked_into_funce_models(
    script, data_dir, fake_download, monkeypatch, tmp_path, suffix
):
    """The unit end to end: fetch the archive from the dataset repository, unpack it, confirm.

    Both archive formats are covered because ``_extract_archive`` has a separate branch for
    each and only the filename's suffix decides which one runs — so a change to one branch that
    left the other broken would otherwise ship unnoticed.  The published file is the zip today;
    the tarball case is FUNCE_MODELS_FILE named the way a future release might be.
    """
    monkeypatch.setattr(script, "FUNCE_MODELS_FILE", f"data_funce{suffix}")
    required = script.funce_model_files()
    publish_funce_archive(script, fake_download, tmp_path)

    script.download_funce_models()

    assert fake_download.filenames == [script.FUNCE_MODELS_FILE]
    assert [path for path in required if not path.exists()] == []


def test_a_finished_download_does_not_leave_the_archive_behind(script, data_dir, fake_download, tmp_path):
    """Once the ensemble is complete the staging directory goes, and 1.35 GB of disk with it.

    It is a persistent ``.download/`` rather than a TemporaryDirectory so an interrupted
    download can resume; that is exactly why clearing it once the ensemble is complete is this
    unit's own job — nothing else will ever come back for it.
    """
    publish_funce_archive(script, fake_download, tmp_path)

    script.download_funce_models()

    assert not (script.FUNCE_MODELS_DIR / FUNCE_STAGING_DIR).exists()


def test_unpacking_an_archive_leaves_a_checkpoint_that_is_already_there_alone(
    script, data_dir, fake_download, tmp_path
):
    """A file already in funce_models/ is kept, not replaced by the archive's copy.

    Half-copied is the normal state of this directory while the ensemble is being put
    together by hand, and each checkpoint is hundreds of megabytes — overwriting what is
    already correct would make finishing a copy cost as much as starting one.
    """
    required = script.funce_model_files()
    already_there = required[0]
    already_there.parent.mkdir(parents=True)
    already_there.write_bytes(b"copied in by hand")
    publish_funce_archive(script, fake_download, tmp_path)

    script.download_funce_models()

    assert already_there.read_bytes() == b"copied in by hand"


def test_an_archive_that_unpacks_without_the_whole_ensemble_stops_the_run(script, data_dir, fake_download, tmp_path):
    """An archive that unpacked cleanly but held the wrong layout must not read as done.

    Taken on trust it would be reported as downloaded and surface much later, as a Func-E
    job predicting from three models instead of four.  Every file still absent is named,
    because the data mount is read-only in the app and cannot be repaired at run time.
    """
    required = script.funce_model_files()
    # Everything but the last EC level's two files, which is the partial ensemble Func-E
    # would otherwise load without complaint.
    publish_funce_archive(script, fake_download, tmp_path, [path.name for path in required[:-2]])

    with pytest.raises(SystemExit) as excinfo:
        script.download_funce_models()

    for path in required[-2:]:
        assert str(path) in str(excinfo.value)
    # The download itself was fine, so the archive is kept: re-fetching 1.35 GB would punish
    # the wrong step, and the next run unpacks what is already in the staging directory.
    assert (script.FUNCE_MODELS_DIR / FUNCE_STAGING_DIR / script.FUNCE_MODELS_FILE).exists()


@pytest.mark.parametrize(
    "wrapper",
    ["", "data_funce/", "data_funce/models/", "data/Funce/models/"],
    ids=["files-at-the-top", "one-folder", "two-folders", "the-published-three"],
)
def test_an_archive_is_flattened_however_deep_its_wrapping_folders_go(script, tmp_path, wrapper):
    """The published Func-E archive wraps its payload three folders deep: ``data/Funce/models/``.

    The checkpoints are wanted flat at the top of funce_models/, the one path Func-E's
    check_data looks in.  Stripping a single wrapping folder — which is what this used to do —
    left them two directories further down where ``funce_model_files()`` cannot see them, and
    the only sign was the "still missing" exit at the end of a 1.35 GB download.
    """
    destination = tmp_path / "funce_models"
    members = ["run_1_conf.pkl", "run_1_checkpoint.pth"]
    archive = write_archive(tmp_path / "data_funce.zip", [f"{wrapper}{name}" for name in members])

    script._extract_archive(archive, destination)

    # Everything in the destination, so a wrapping folder left behind would show up here too.
    assert sorted(path.name for path in destination.iterdir()) == sorted(members)


@pytest.mark.parametrize(
    "member",
    ["/etc/passwd", "../../etc/passwd", "models/../../../etc/passwd"],
    ids=["absolute-path", "leading-parent-directory", "parent-directory-part-way-through"],
)
def test_a_zip_member_that_escapes_the_destination_is_refused(script, tmp_path, member):
    """Archive members are a trust boundary, and zipfile has no ``filter="data"`` to lean on.

    The tar branch gets that refusal from tarfile itself; the zip branch applies the same
    rule by hand, so it is the one that needs proving.  Without it a crafted release could
    write anywhere the process can reach.
    """
    destination = tmp_path / "funce_models"
    archive = write_archive(tmp_path / "release.zip", [member])

    with pytest.raises(SystemExit) as excinfo:
        script._extract_archive(archive, destination)

    assert member in str(excinfo.value)
    # Refused before anything was unpacked, not cleaned up afterwards.
    assert list(destination.iterdir()) == []


# ── The full EnzymeMap reference ─────────────────────────────────────────────


def test_the_reactions_reference_is_not_fetched_again_when_it_is_already_there(script, data_dir, fake_download):
    """130 MB, and the CSV itself is the check, so a re-run reuses it instead of downloading."""
    script.REACTIONS_DIR.mkdir(parents=True)
    (script.REACTIONS_DIR / script.REACTIONS_FILE).write_text("rxn_idx,mapped\n")

    script.download_reactions()

    assert fake_download.filenames == []


def test_the_reactions_reference_lands_in_the_reactions_directory(script, data_dir, fake_download, tmp_path):
    """Both reaction tools read reactions/*.csv, so the file has to arrive there under its own name.

    Landing it anywhere else leaves the shipped demo set as the only thing their dropdowns
    offer, after a finished download and with nothing to say why.
    """
    # A plain CSV, not an archive: this unit downloads the reference file itself.
    published = tmp_path / "published.csv"
    published.write_text("rxn_idx,mapped\n")
    fake_download.archive = published

    script.download_reactions()

    assert fake_download.filenames == [script.REACTIONS_FILE]
    assert (script.REACTIONS_DIR / script.REACTIONS_FILE).read_bytes() == published.read_bytes()


def test_a_reactions_download_that_leaves_no_csv_is_a_failure(script, data_dir, hugging_face):
    """A finished download with nothing under it stops here rather than at the first search.

    ``hf_hub_download`` keeps the repository's own folders under ``local_dir``, so a reference
    published one directory deep lands where nothing scans for ``reactions/*.csv`` — and both
    reaction tools would go on offering the demo set alone, with a successful run behind them.
    """
    hugging_face.hf_hub_download = lambda **kwargs: "/hf-cache/nothing.csv"  # leaves nothing behind

    with pytest.raises(SystemExit) as excinfo:
        script.download_reactions()

    assert script.REACTIONS_FILE in str(excinfo.value)


# ── The command line ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("argv", "expected_units"),
    [
        ([], ["prostt5", "unimol", "funce"]),
        (["--full"], ["prostt5", "unimol", "funce", "reactions", "pdb", "afdb", "esm3"]),
        (["prostt5"], ["prostt5"]),
        (["prostt5", "esm3"], ["prostt5", "esm3"]),
    ],
    ids=["no-arguments-is-the-minimal-tier", "full-is-everything", "one-named-unit", "several-named-units"],
)
def test_the_command_line_runs_exactly_the_units_it_was_asked_for(script, data_dir, monkeypatch, argv, expected_units):
    """Which units run is the whole contract of the CLI, so that is what is asserted.

    The expected names are spelled out rather than read back off MINIMAL and UNITS: a
    reordering or a unit quietly dropped from the minimal tier is exactly the change this
    should catch, and comparing the script against itself would wave it through.
    """
    units_run = record_every_unit(script, monkeypatch)

    script.main(argv)

    assert units_run == expected_units


# What every progress line opens with: [position/total] unit-name.
PROGRESS_LINE = re.compile(r"^\[(\d+)/(\d+)\] (\w+)", flags=re.MULTILINE)


def test_every_unit_is_announced_with_its_place_in_the_run(script, data_dir, monkeypatch, capsys):
    """A --full run is seven units and ~20 GB, and a unit cannot know its own place in it.

    Without the counter there is no way to tell a long download from a hung one.  Which units
    run is the test above's job; this one only reads the counters and the names back, so the
    banners around them can be restyled without a test to fix.
    """
    units_run = record_every_unit(script, monkeypatch)

    script.main(["--full"])

    announced = []
    for position, total, name in PROGRESS_LINE.findall(capsys.readouterr().out):
        # Each unit is announced twice, as it starts and as it finishes, and both lines carry
        # the same counter, so the second one has nothing new to check.
        if (int(position), int(total), name) not in announced:
            announced.append((int(position), int(total), name))

    assert announced == [(position, len(units_run), name) for position, name in enumerate(units_run, start=1)]


@pytest.mark.parametrize(
    "argv",
    [["--full", "prostt5"], ["nosuchunit"], ["prostt5", "nosuchunit"]],
    ids=["full-together-with-a-unit", "an-unknown-unit", "one-known-one-unknown"],
)
def test_the_command_line_refuses_a_request_it_cannot_honour(script, data_dir, monkeypatch, argv):
    """A request that cannot be honoured exits 2 and downloads nothing.

    Falling back to the minimal tier on a typo would be the worst outcome: several GB
    downloaded, and no sign that the unit actually asked for was never run.
    """
    units_run = record_every_unit(script, monkeypatch)

    with pytest.raises(SystemExit) as excinfo:
        script.main(argv)

    assert excinfo.value.code == 2  # argparse's usage-error exit code
    assert units_run == []


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
def test_report_marks_every_item_against_the_data_directory(script, data_dir, capsys, populated):
    """The report is where someone reads off what this host has, so no item may go unlisted.

    Seven of them: the directories the app reads. The ESM3 cache is not one -- see below.
    """
    if populated:
        write_every_data_item(script)

    script.report()

    output = capsys.readouterr().out
    assert report_statuses(output) == ["OK" if populated else "MISSING"] * 7
    assert str(data_dir) in output  # the directory it answered for, so a mount typo is visible


@pytest.mark.parametrize("selected", [[], ["prostt5"], ["esm3"], ["prostt5", "esm3"]])
def test_the_report_names_esm3_only_when_the_run_asked_for_it(script, monkeypatch, capsys, selected):
    """No tool reads the ESM3 cache, so an unasked-for run must not report it as missing data."""
    monkeypatch.setattr(script, "esm3_is_cached", lambda: False)

    script.report(selected)

    assert ("ESM3" in capsys.readouterr().out) == ("esm3" in selected)


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
