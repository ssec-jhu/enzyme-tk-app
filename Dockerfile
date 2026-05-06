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
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxrender1 \
    libxext6 \
    libexpat1 \
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

COPY requirements/prd.txt requirements.txt

RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050

CMD ["gunicorn", "enzyme_tk_app.app.app:server", "--bind", "0.0.0.0:8050", "--workers", "2", "--threads", "4"]
