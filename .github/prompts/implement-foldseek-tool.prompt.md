# Implement FoldSeek Sequence & Structure Similarity Tool

## Original promt during working session

I want to add a new tool to interface enzymetk package's FoldSeek step from similarity_sequence_and_structure_step. The new code is in a branch at git+https://github.com/moragroup/enzyme-tk-agentic.git@foldseek-for-enzymetk-app" and not released in yet with the package. So use this instead.
There is an exampl usage in the branch in the file examples/foldseek_sequence_and_struct. I will only import from enzymetk.similarity_sequence_and_structure_step import FoldSeek, FoldSeekDatabase for this tool.
In this sequence_structure_similarity tool, I want the user to be able to input a sequence and selcet databases from the databases found in /data/foldseek_db which will be in the DB_ROOT and submit a job to the step function I wrote. The dropdown list should pick up all the databases in the foldseek_db folder. The folder name is the db name used to send the list to foldseek. The user also has an option to upload a cif or pdb file in which case there is a sequence and structure mode that is run in similarity_sequence_and_structure_step. You can assume the weights dir path is set in /data/foldseek_modules.
The results page should return the full df that the algorithm returns. Set N to be a larg number like 1000 for default.
Also, create a couple of exmamples similar to the other tools so user can click and run to see. try the A0A009IHW8, A0A067CMC7 and 1AKI examples. 1AKI also has a sturcture in /data/structures. A0A009IHw8 also has a structure in /data/structures called A0A009IHW8-chai.cif. I want to have both modes of this sequence in the examples: one sequence only, and one to test with its structure.
Also update docker file with anythig related to foldseek if need be.
Make sure to update readme with the new addtion.
No need to write tests at the moment.
Ask me questions to clarify implemetation.

## Summary

Flesh out the existing `sequence_structure_similarity/` scaffold into a fully functional tool that interfaces with enzymetk's `FoldSeek` step. The tool lets users input a sequence, optionally upload or select a CIF/PDB structure file, choose databases from `/data/foldseek_db`, and submit a job that returns the full FoldSeek results DataFrame.

## Architecture

```
User Modal → callbacks.py → TaskScheduler → Celery Worker → compute.py
                                                                  │
                                                                  ▼
                                                   FoldSeek(enzymetk)
                                                   ├─ ProstT5 weights (/data/foldseek_models/weights/)
                                                   ├─ Databases (/data/foldseek_db/{PDB,AFDB_SWISSPROT,...})
                                                   └─ Structure file (optional CIF/PDB)
                                                                  │
                                                                  ▼
                                                   results.py → AG Grid table
```

## Key Decisions

### Dependencies
- **enzymetk source**: `git+https://github.com/moragroup/enzyme-tk-agentic.git@foldseek-for-enzymetk-app` (unreleased branch with FoldSeek support)
- **foldseek binary**: Pulled from `ghcr.io/steineggerlab/foldseek:master` via multi-stage Docker build (same pattern as Diamond)

### FoldSeek API Contract
```python
from enzymetk.similarity_sequence_and_structure_step import FoldSeek

step = FoldSeek(
    id_column_name="Entry",
    sequence_column_name="Sequence",
    prostt5_weights_path="/data/foldseek_models/weights",
    databases=["PDB", "AFDB_SWISSPROT"],      # folder names
    database_root_path="/data/foldseek_db",
    structure_column_name="structure",          # None for seq-only mode
)
result_df = step.execute(query_df)
```

**Output columns**: `query, target, fident, alnlen, mismatch, gapopen, qstart, qend, tstart, tend, evalue, bits, database`

### Modes
- **Sequence only**: `structure_column_name=None` — uses ProstT5 to predict structure from sequence
- **Sequence + Structure**: `structure_column_name="structure"` — uses provided CIF/PDB for direct comparison

### Database Discovery
- All subdirectories in `DATA_DIR / "foldseek_db"` are listed as options
- No custom DB building exposed — tool only searches pre-built databases
- Backend auto-downloads missing standard DBs (PDB, AFDB_SWISSPROT)

### Modal UX
- Example dropdown values are JSON-encoded: `{"sequence": "...", "structure_file": "1AKI.cif" | null}`
- Structure input: two paths — upload via `dcc.Upload` OR select from pre-loaded dropdown
- Uploaded file takes precedence over dropdown selection
- Default Top-N: 1000

### Params Schema (callbacks → compute)
```python
{
    "task_name": str,
    "sequence": str,
    "databases": list[str],           # folder names in foldseek_db
    "top_n": int,                     # default 1000
    "structure_content": str | None,  # base64 data URI from dcc.Upload
    "structure_filename": str | None, # original filename of upload
    "structure_preloaded": str | None # filename in data/structures/
}
```

### Compute Output Schema
```python
{
    "_stat_cards": [
        {"label": "Databases Searched", "value": "2/2"},
        {"label": "Results Returned", "value": "847"},
        {"label": "Mode", "value": "Sequence + Structure"},
        {"label": "Run Time", "value": "12.3s"},
    ],
    "dataframe": {
        "columns": ["query", "target", "fident", ...],
        "data": [{...}, ...]
    }
}
```

## Files Modified/Created

| File | Action | Purpose |
|------|--------|---------|
| `requirements/prd.txt` | Modified | Switch enzymetk to git branch |
| `Dockerfile` | Modified | Add foldseek binary from official image |
| `enzyme_tk_app/app/utils/data_loading.py` | Modified | Add `get_foldseek_database_options()`, `get_structure_file_options()` |
| `enzyme_tk_app/app/tools/sequence_structure_similarity/__init__.py` | Modified | Updated TOOL_DEF description |
| `enzyme_tk_app/app/tools/sequence_structure_similarity/modal.py` | Created | Modal with seq input, structure upload, DB multi-select |
| `enzyme_tk_app/app/tools/sequence_structure_similarity/callbacks.py` | Created | Toggle, example population, validation, submit |
| `enzyme_tk_app/app/tools/sequence_structure_similarity/compute.py` | Created | FoldSeek execution via enzymetk |
| `enzyme_tk_app/app/tools/sequence_structure_similarity/results.py` | Created | AG Grid results display |
| `README.md` | Modified | Updated tool description |

## Example Data

| Entry | Sequence | Structure File | Modes Tested |
|-------|----------|---------------|--------------|
| A0A009IHW8 | MSLEQKKGADIISKILQIQ... | A0A009IHW8-chai.cif | Seq-only, Seq+Struct |
| A0A067CMC7 | MLEVPVWIPILAFAVGLGL... | — | Seq-only |
| 1AKI | KVFGRCELAAAMKRHGLDN... | 1AKI.cif | Seq-only, Seq+Struct |

## Verification

```bash
tox run -e format   # auto-format + remove unused imports
tox                 # full test suite + style check
docker compose up --build  # smoke test
docker compose exec worker foldseek --help  # verify binary
```
