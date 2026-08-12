"""Tests for build_enzyme_db.py — the sequence reader, the resume arithmetic, and where the
two artifacts land.

The script ships standalone, with its own Docker image, so it is loaded by path rather than
imported — see ``load_db_build_script`` in conftest, which also puts this directory on
``sys.path`` so the script's ``from download_data import ...`` resolves.

Nothing here touches torch, foldseek or the network. Both build functions are entered only as
far as the branch that returns before any of that starts, and ``subprocess.run`` is replaced
where even that could spawn something. pandas is used for real: the app depends on it anyway.
"""

import gzip

import pandas as pd
import pytest
from conftest import load_db_build_script

HEADER = ("Entry", "Sequence")
ROWS = [("A0A009IHW8", "MKKLLF"), ("A0A023I7E1", "MHSKFF")]


@pytest.fixture
def script(db_build_environment):
    """A freshly loaded copy of the script, so config edits in one test cannot leak into another.

    ``db_build_environment`` keeps the load from leaving anything behind: importing this
    script imports download_data, which sets HF_HOME in the process it is running in.
    """
    return load_db_build_script("build_enzyme_db")


def never_run(command, **kwargs):
    """Stand in for ``subprocess.run`` where nothing should be spawned at all.

    Both callers are testing a branch that returns before the work starts, and a test host
    that happens to have foldseek installed would otherwise really start building.
    """
    raise AssertionError(f"nothing should have been run here, but got: {command}")


def write_table(path, header=HEADER, rows=ROWS):
    """Write rows to path, picking delimiter and gzip from its suffixes."""
    delimiter = "\t" if path.name.endswith((".tsv", ".tsv.gz")) else ","
    text = "".join(delimiter.join(row) + "\n" for row in [header, *rows])
    if path.name.endswith(".gz"):
        path.write_bytes(gzip.compress(text.encode()))
    else:
        path.write_text(text)
    return path


@pytest.mark.parametrize("filename", ["seqs.csv", "seqs.tsv", "seqs.csv.gz", "seqs.tsv.gz"])
def test_read_sequences_handles_every_supported_suffix(script, tmp_path, filename):
    """All four suffixes the app accepts as a sequence database yield the same records."""
    assert script.read_sequences(write_table(tmp_path / filename)) == ROWS


def test_read_sequences_ignores_extra_columns(script, tmp_path):
    """The real enzymes.tsv has 17 columns; only Entry and Sequence are read."""
    path = tmp_path / "seqs.tsv"
    header = ("Entry", "Organism", "Sequence", "EC number")
    rows = [("A0A009IHW8", "Acinetobacter", "MKKLLF", "3.2.2.6")]
    write_table(path, header=header, rows=rows)

    assert script.read_sequences(path) == [("A0A009IHW8", "MKKLLF")]


def test_read_sequences_reports_missing_columns(script, tmp_path):
    """A file without the required columns exits naming both what is missing and what is there."""
    path = write_table(tmp_path / "seqs.csv", header=("Entry", "Organism"), rows=[("A0A009IHW8", "Acinetobacter")])

    with pytest.raises(SystemExit) as excinfo:
        script.read_sequences(path)

    message = str(excinfo.value)
    assert "Sequence" in message
    assert "Organism" in message


def test_read_sequences_rejects_an_empty_file(script, tmp_path):
    """An empty file exits cleanly — DictReader.fieldnames is None, which must not raise TypeError."""
    path = tmp_path / "seqs.csv"
    path.write_text("")

    with pytest.raises(SystemExit):
        script.read_sequences(path)


def test_read_sequences_rejects_a_missing_file(script, tmp_path):
    """A mistyped INPUT_FILE exits with the path, rather than raising FileNotFoundError."""
    with pytest.raises(SystemExit):
        script.read_sequences(tmp_path / "nope.csv")


def test_read_sequences_skips_blank_and_duplicate_rows(script, tmp_path):
    """Blank ids and sequences are dropped, and a repeat id is kept only once.

    A duplicate would become a duplicate FASTA header and a duplicate pickle row.
    """
    rows = [
        ("A0A009IHW8", "MKKLLF"),
        ("", "MHSKFF"),  # no id
        ("A0A023I7E1", "   "),  # whitespace sequence
        ("A0A009IHW8", "MDIFFERENT"),  # repeat id
    ]
    path = write_table(tmp_path / "seqs.csv", rows=rows)

    assert script.read_sequences(path) == [("A0A009IHW8", "MKKLLF")]


def test_read_sequences_exits_when_every_row_is_unusable(script, tmp_path):
    """A file whose rows all lack an id or a sequence is an error, not an empty result."""
    path = write_table(tmp_path / "seqs.csv", rows=[("", "MKKLLF"), ("A0A023I7E1", "")])

    with pytest.raises(SystemExit):
        script.read_sequences(path)


def test_limit_truncates_the_input(script, tmp_path):
    """LIMIT is the quick-test knob: it stops the reader early."""
    script.LIMIT = 1

    assert script.read_sequences(write_table(tmp_path / "seqs.csv")) == ROWS[:1]


@pytest.mark.parametrize(
    ("input_file", "expected"),
    [
        ("enzymes.tsv.gz", "enzymes"),  # both suffixes go, which Path.stem alone gets wrong
        ("protein.csv.gz", "protein"),
        ("enzymes_sample_10.tsv", "enzymes_sample_10"),
        ("protein.csv", "protein"),
    ],
)
def test_output_name_strips_every_suffix(script, input_file, expected):
    """Both artifacts are named after the input file, with its suffixes removed."""
    script.INPUT_FILE = input_file

    assert script.output_name() == expected


def test_select_pending_skips_ids_already_embedded(script):
    """Resume: only ids missing from the existing pickle are handed to ESM3."""
    records = [(f"E{i}", "MKKLLF") for i in range(5)]

    assert script.select_pending(records, {"E0", "E2", "E4"}) == [("E1", "MKKLLF"), ("E3", "MKKLLF")]


def test_select_pending_keeps_every_length(script):
    """No length ceiling: a 50,000-residue protein is embedded like any other.

    Length costs nothing on disk — every protein yields one 1536-float vector — and the
    sequences over 2000 aa are only ~6% of the compute for the whole of enzymes.tsv.
    """
    assert script.select_pending([("long", "M" * 50_000)], set()) == [("long", "M" * 50_000)]


def test_select_pending_returns_everything_when_nothing_is_done(script):
    """An empty pickle means every record is pending."""
    records = [("E1", "MKKLLF"), ("E2", "MHSKFF")]

    assert script.select_pending(records, set()) == records


def test_select_pending_orders_shortest_first(script):
    """Shortest first is what makes an out-of-memory kill cheap.

    Everything that fits in memory is embedded before anything that does not, so the run
    gets as far as the host allows and the first kill marks the ceiling — every sequence
    still pending after it is at least as long, and can be reported without being tried.
    """
    records = [("long", "M" * 900), ("short", "M" * 10), ("mid", "M" * 100)]

    assert [seq_id for seq_id, _ in script.select_pending(records, set())] == ["short", "mid", "long"]


def test_pickle_columns_match_the_app_contract(script):
    """Func-E requires exactly these three columns of an embeddings pickle (funce/compute.py)."""
    assert script.PICKLE_COLUMNS == ["Entry", "Sequence", "esm3_mean"]


# ── The models, which download_data.py now supplies ──────────────────────────


@pytest.mark.parametrize(
    "require_function",
    ["require_prostt5_weights", "require_esm3_weights"],
    ids=["prostt5", "esm3"],
)
def test_a_missing_model_names_the_script_that_downloads_it(script, tmp_path, monkeypatch, require_function):
    """Neither model is downloaded here any more, so the message has to say where they come from.

    A bare "not found" would leave someone with a half-built database and no next command.
    """
    monkeypatch.setattr(script, "FOLDSEEK_WEIGHTS_DIR", tmp_path)  # empty, so ProstT5 is absent
    monkeypatch.setattr(script, "esm3_is_cached", lambda: False)

    with pytest.raises(SystemExit) as excinfo:
        getattr(script, require_function)()

    assert "download_data.py" in str(excinfo.value)


def test_require_prostt5_weights_returns_the_directory_holding_them(script, tmp_path, monkeypatch):
    """The return value is handed to `foldseek createdb --prostt5-model`, which wants the directory.

    It is the file that is checked, though: foldseek is given a folder and would fail much
    later, mid-build, if the weights inside it were the thing missing.
    """
    monkeypatch.setattr(script, "FOLDSEEK_WEIGHTS_DIR", tmp_path)
    (tmp_path / script.PROSTT5_WEIGHTS_FILE).write_bytes(b"")

    assert script.require_prostt5_weights() == tmp_path


def test_require_esm3_weights_passes_when_the_checkpoint_is_cached(script, monkeypatch):
    """A populated Hugging Face cache is the whole check — this script never downloads ESM3 itself."""
    monkeypatch.setattr(script, "esm3_is_cached", lambda: True)

    assert script.require_esm3_weights() is None


def test_weights_only_now_redirects_to_the_download_script(script):
    """--weights-only moved to download_data.py, and saying so is the only reason the flag survives.

    The dispatch at the bottom of the script falls through to `main()`, so a flag that
    returned instead of exiting would start a full database build without a word.
    """
    with pytest.raises(SystemExit) as excinfo:
        script.weights_only_redirect()

    assert "download_data.py" in str(excinfo.value)


# ── Where the artifacts land ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path_function", "expected_name"),
    [
        ("embeddings_path", "enzymes.pkl"),
        ("inflight_path", ".enzymes.inflight"),
        ("ceiling_path", ".enzymes.ceiling"),
    ],
    ids=["pickle", "in-flight-marker", "ceiling-marker"],
)
def test_every_embedding_artifact_lands_in_the_apps_data_directory(
    script, tmp_path, monkeypatch, path_function, expected_name
):
    """The pickle and its two markers sit in sequence_embeddings/, not in a local output/ folder.

    That directory is the one Func-E's dropdown scans, so a finished build needs no copying;
    the markers keep the pickle's name, so two inputs being built cannot overwrite each other's.
    """
    monkeypatch.setattr(script, "SEQUENCE_EMBEDDINGS_DIR", tmp_path)
    monkeypatch.setattr(script, "INPUT_FILE", "enzymes.tsv.gz")

    assert getattr(script, path_function)() == tmp_path / expected_name


def test_the_foldseek_database_lands_in_the_apps_data_directory(script, tmp_path, monkeypatch, capsys):
    """The database is built under foldseek_db/<name>/, which is where the app's dropdown scans.

    Read through the "already exists" branch, which is also what makes a re-run cheap: with
    the .index in place the build names the database it found and returns, without spending
    hours rebuilding it.
    """
    monkeypatch.setattr(script, "FOLDSEEK_DB_DIR", tmp_path)
    monkeypatch.setattr(script, "INPUT_FILE", "enzymes.tsv.gz")
    monkeypatch.setattr(script, "require_foldseek", lambda: None)  # no binary on a test host
    monkeypatch.setattr(script.subprocess, "run", never_run)
    prefix = tmp_path / "enzymes" / "enzymes"
    prefix.parent.mkdir()
    prefix.with_suffix(".index").write_bytes(b"")

    script.build_enzyme_db_foldseek(ROWS)

    assert str(prefix) in capsys.readouterr().out


# ── Picking a half-finished run back up ──────────────────────────────────────


def test_an_absent_pickle_starts_an_empty_frame_with_the_right_columns(script, tmp_path, monkeypatch):
    """The first run has nothing to resume from, and must still produce the app's three columns.

    Concatenating onto a frame with no columns is how a pickle ends up with whatever ESM3
    returned that day instead.
    """
    monkeypatch.setattr(script, "SEQUENCE_EMBEDDINGS_DIR", tmp_path)

    done = script.load_embeddings(pd)

    assert list(done.columns) == script.PICKLE_COLUMNS
    assert len(done) == 0


def test_a_pickle_with_other_columns_is_refused_before_the_run_starts(script, tmp_path, monkeypatch):
    """A mismatched pickle stops the run immediately, naming both column lists.

    People leave this script running for days; discovering the mismatch as a KeyError on the
    first checkpoint would throw all of that away.
    """
    monkeypatch.setattr(script, "SEQUENCE_EMBEDDINGS_DIR", tmp_path)
    pd.DataFrame(columns=["Entry", "esm2_mean"]).to_pickle(script.embeddings_path())

    with pytest.raises(SystemExit) as excinfo:
        script.load_embeddings(pd)

    assert "esm2_mean" in str(excinfo.value)  # what is there
    assert str(script.PICKLE_COLUMNS) in str(excinfo.value)  # what was expected


def test_an_input_that_is_fully_embedded_does_not_start_a_worker(script, tmp_path, monkeypatch, capsys):
    """Re-running a finished input costs nothing — that is what makes topping one up cheap.

    Adding sequences to an input file should pay for the new sequences only, so a run with
    nothing pending returns before the model is even asked for.
    """
    monkeypatch.setattr(script, "SEQUENCE_EMBEDDINGS_DIR", tmp_path)
    monkeypatch.setattr(script.subprocess, "run", never_run)
    embedded = pd.DataFrame(
        [(seq_id, sequence, [0.0]) for seq_id, sequence in ROWS],
        columns=script.PICKLE_COLUMNS,
    )
    embedded.to_pickle(script.embeddings_path())

    script.build_enzyme_db_esm3(ROWS)

    assert str(script.embeddings_path()) in capsys.readouterr().out
