# Host data directory

This directory is bind-mounted into the running Docker containers at
`/data` (read-only). It is the **external data tier** for the EnzymeTK
app — large files that should never be baked into the Docker image.

The folder itself is committed to the repo (kept alive by `.gitkeep` and
this README) so the bind-mount target always exists right after
`git clone`. Its contents are gitignored.

## Expected sub-layout

Drop your data files here using exactly these directory names:

```
data/
├── sequences/         # *.csv  protein sequence databases
├── reactions/         # *.csv  reaction databases
├── foldseek_db/       # one sub-directory per pre-built FoldSeek DB
│   └── <db_name>/...
└── foldseek_models/   # ProstT5 / FoldSeek model weights
```

The application reads from these via the `ETK_DATA_DIR` environment
variable (set to `/data` inside the container). Outside Docker the same
paths default to `enzyme_tk_app/app/data/` in the source tree.

## What does NOT belong here

- `structures/` — bundled `.cif` files that ship inside the image. They
  live at `enzyme_tk_app/app/data/structures/` and are version-locked to
  the application code. Do **not** place a `structures/` folder in this
  directory; it would not be used.

## Production / cloud

In production the host path is configured via `ETK_DATA_DIR_HOST` in
`.env.prod` and may point at any local path, NFS mount, or cloud-storage
sidecar that exposes the same sub-layout at `/data` inside the
container.
