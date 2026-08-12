"""Tests for scripts/db_build/build_enzyme_db.py — the sequence reader and the resume arithmetic.

The script lives outside the package (it ships standalone, with its own Docker image), so it
is loaded by path rather than imported. Nothing here touches torch, foldseek or the network:
the heavy work sits behind lazy imports inside the two build functions, which these tests
never call.
"""

import gzip
import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[3] / "scripts" / "db_build" / "build_enzyme_db.py"

HEADER = ("Entry", "Sequence")
ROWS = [("A0A009IHW8", "MKKLLF"), ("A0A023I7E1", "MHSKFF")]


def load_script():
    """Load build_enzyme_db.py by path — it is a standalone script, not part of the package."""
    spec = importlib.util.spec_from_file_location("build_enzyme_db", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script():
    """A freshly loaded copy of the script, so config edits in one test cannot leak into another."""
    return load_script()


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


def test_weights_only_skips_the_input_file(script, monkeypatch):
    """--weights-only must run before any input file exists — the weights come first.

    Patching the downloads keeps this off the network and past the foldseek guard, which
    would otherwise exit on a host with no binary.
    """
    called = []
    monkeypatch.setattr(script, "INPUT_FILE", "no-such-file.tsv")
    monkeypatch.setattr(script, "download_or_reuse_prostt5_weights", lambda _: called.append("prostt5"))
    monkeypatch.setattr(script, "download_or_reuse_esm3_weights", lambda: called.append("esm3"))

    script.download_weights_only()  # would SystemExit if it read INPUT_FILE

    assert called == ["prostt5", "esm3"]
