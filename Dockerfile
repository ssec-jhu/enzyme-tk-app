FROM buchfink/diamond:latest AS diamond-bin

FROM python:3.12-slim
#FROM python:3.11
# -------------------------------
# IF one decides to use python:3.11-slim we need the lines below. This is required for the RDkit
# I sswithed to the non-slim python package and that resolved the lib issue but will keep these commets for reference.
# RDKit is a C++ library with Python bindings — and its Python wheels often link against native system libraries.
# RDKit drawing module (rdMolDraw2D) relies on X11 libraries for rendering. They are essential for Linux deployments.
# RDKit drawing module (rdMolDraw2D) relies on X11 libraries for rendering.
# These small runtime deps are needed on slim but absent from the full image.
# ------------------------------
# -y assumes yes to all prompts
# libsm6 / libglib2.0-0 are for unimol_tools (Func-E reaction encoding): it imports
# rdkit.Chem.PandasTools at module load, which pulls in rdkit.Chem.Draw and links
# against glib and X11.  Without them the import dies on
# "libSM.so.6: cannot open shared object file" before any code runs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxrender1 \
    libxext6 \
    libexpat1 \
    libsm6 \
    libglib2.0-0 \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*


# ── Diamond BLAST aligner ─────────────────────────────────────────
# Required by the Sequence Similarity tool (enzymetk.sequence_search_blast).
# Diamond is a high-throughput protein alignment tool used as the BLAST
# backend.  Built from source so it works on both x86-64 and ARM64
# (Apple Silicon) hosts.  Static linking (-DSTATIC=ON) avoids runtime
# linker mismatches when Docker layers are cached across platforms.

# DO NOT USE BELOW INSTALLATION METHOD (FROM SOURCE) — 
# it causes caching issues on Apple Silicon (M1/M2) Macs, 
# where the build layer is cached for x86-64 and then fails to run on ARM64.  
# Instead, we pull the multi-arch binary from the official image to ensure 
# compatibility across all platforms.
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     wget cmake g++ zlib1g-dev ca-certificates \
#     && wget -q https://github.com/bbuchfink/diamond/archive/refs/tags/v2.1.9.tar.gz -O /tmp/diamond.tar.gz \
#     && tar -xzf /tmp/diamond.tar.gz -C /tmp \
#     && cd /tmp/diamond-2.1.9 \
#     && mkdir build && cd build \
#     && cmake .. -DCMAKE_BUILD_TYPE=Release -DSTATIC=ON \
#     && make -j"$(nproc)" \
#     && mv diamond /usr/local/bin/diamond \
#     && cd / && rm -rf /tmp/diamond* \
#     && apt-get purge -y wget cmake g++ \
#     && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
# We pull the multi-arch binary from the official image to ensure compatibility
# across Apple Silicon (Mac), Windows, and Cloud (Azure/GCP/K8s) environments.
COPY --from=diamond-bin /usr/local/bin/diamond /usr/local/bin/diamond

# ── FoldSeek structural aligner ───────────────────────────────────
# Required by the Sequence & Structure-Based Similarity tool
# (enzymetk.similarity_sequence_and_structure_step).
# FoldSeek performs fast protein structure and sequence similarity
# searches using ProstT5 embeddings or CIF/PDB structure files.
#
# DO NOT USE the multi-stage COPY approach (COPY --from=foldseek-bin) —
# the upstream image stores arch-specific binaries at different paths
# (foldseek_arch for ARM64, foldseek_sse41/foldseek_avx2 for x86_64)
# with a wrapper script to dispatch.  Copying a single binary (e.g.
# foldseek_arch) produces an empty file on x86_64 hosts.
# Instead, we download the static binary from the official source,
# which handles both x86_64 and ARM64 (Apple Silicon) correctly.
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        FOLDSEEK_URL="https://mmseqs.com/foldseek/foldseek-linux-avx2.tar.gz"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        FOLDSEEK_URL="https://mmseqs.com/foldseek/foldseek-linux-arm64.tar.gz"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    wget -q "$FOLDSEEK_URL" -O /tmp/foldseek.tar.gz && \
    tar -xzf /tmp/foldseek.tar.gz -C /tmp && \
    cp /tmp/foldseek/bin/foldseek /usr/local/bin/foldseek && \
    chmod +x /usr/local/bin/foldseek && \
    rm -rf /tmp/foldseek*

WORKDIR /app

# ── PyTorch (CPU by default) ──────────────────────────────────────
# MUST come before the requirements install.  enzymetk depends on unpinned `torch`,
# so if requirements go first pip resolves the CUDA build from PyPI (~2.9 GB of
# nvidia-cu* wheels on amd64) and this line degrades to "Requirement already
# satisfied".  In this order the CPU wheel is already present and *satisfies* that
# unpinned dependency, so pip leaves it alone — measured 6.41 GB -> 2.2 GB.
#
# --extra-index-url is not optional: --index-url alone *replaces* PyPI, and pip then
# silently backtracks to torch 2.5.1 — below the >=2.6 floor transformers enforces
# before it will torch.load a .bin checkpoint (CVE-2025-32434).  rxnfp's BERT weights
# are .bin, so that failure would surface at runtime inside the rxnfp subprocess
# rather than here at build time.
#
# GPU: rebuild with --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124
# (PyPI ships no CUDA torch for arm64, so on Apple Silicon this is already CPU-only.)
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip3 install --no-cache-dir "torch>=2.6" \
    --index-url "$TORCH_INDEX_URL" \
    --extra-index-url https://pypi.org/simple

COPY requirements/prd.txt requirements.txt

RUN pip3 install --no-cache-dir -r requirements.txt

# ── rxnfp (Func-E reaction fingerprints) ──────────────────────────
# --no-deps is deliberate.  rxnfp's metadata hard-pins scipy==1.4.1,
# scikit-learn==0.23.1 and matplotlib==3.2.2 — 2020 releases with no wheels for this
# Python, so a plain install fails building them from source.  0.23.1 would also
# clobber the scikit-learn that unpickles the Func-E MinMaxScalers.  Nothing is lost:
# its BERT weights ship inside the wheel, and its only conda-only import (tmap) lives
# in the minhash generator we never construct.
#
# setuptools is installed alongside it for `pkg_resources`, which rxnfp imports at
# module load to locate its bundled bert_ft weights.  Python 3.12 dropped the
# implicit setuptools that used to make that work, so without this the import fails
# with ModuleNotFoundError.  Capped below 81 because pkg_resources is being removed
# from setuptools — the deprecation warning rxnfp triggers says to pin exactly this.
# It still warns at 80.x; the cap buys working code, not a quiet log.
RUN pip3 install --no-cache-dir "setuptools<81" && \
    pip3 install --no-cache-dir --no-deps rxnfp==0.1.0

COPY . .

EXPOSE 8050

CMD ["gunicorn", "enzyme_tk_app.app.app:server", "--bind", "0.0.0.0:8050", "--workers", "2", "--threads", "4"]
