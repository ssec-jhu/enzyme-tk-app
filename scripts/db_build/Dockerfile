# Enzyme DB builder — independent of the app image. See README.md.
#
# Build:  docker build -t etk-db-build scripts/db_build
# Run:    docker run --rm -v "$(pwd)/scripts/db_build:/app" etk-db-build
#
# The mount carries three things: the script (so editing its CONFIG block or commenting
# out a step in main() needs no rebuild), the input sequence file, and output/ — which is
# how the built database, the embeddings pickle and the downloaded weights reach the host.
#
# python:3.12, not 3.11 or 3.10. Two hard constraints:
#   * esm 3.2.2+ declares requires-python >=3.12,<3.13 (3.2.1.post1 was the last to take 3.10).
#   * biotite, which esm.sdk.api imports, has no cp310 linux-aarch64 wheel at any version.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# foldseek static binary, arch-aware (works on Apple-Silicon aarch64 and x86_64).
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ];  then URL=https://mmseqs.com/foldseek/foldseek-linux-avx2.tar.gz; \
    elif [ "$ARCH" = "aarch64" ]; then URL=https://mmseqs.com/foldseek/foldseek-linux-arm64.tar.gz; \
    else echo "unsupported arch: $ARCH" && exit 1; fi && \
    wget -q "$URL" -O /tmp/fs.tgz && tar -xzf /tmp/fs.tgz -C /tmp && \
    cp /tmp/foldseek/bin/foldseek /usr/local/bin/foldseek && \
    chmod +x /usr/local/bin/foldseek && rm -rf /tmp/foldseek*

# Python dependencies for the ESM3 step, in an order that matters. Ported from
# enzyme-tk-agentic/examples/Dockerfile.esm3, where each trap below was found the hard way.
#
# 1. torch first, CPU build, pinned. Three separate traps:
#    a. CPU build — torch's nvidia deps carry `platform_system == "Linux"` with no
#       `platform_machine` qualifier, so plain PyPI installs gigabytes of CUDA aarch64
#       (sbsa) wheels that Docker Desktop can never reach. Override TORCH_INDEX_URL with
#       a CUDA index on a GPU host, the same knob the app image uses.
#    b. Pinned to 2.9.1 — the CPU index carries aarch64 wheels only up to 2.9.1; asking
#       for newer makes pip silently backtrack. esm needs torch>=2.2.0, so 2.9.1 is fine.
#    c. --extra-index-url, not --index-url alone — the latter *replaces* PyPI, so torch's
#       own generic dependencies stop resolving. `+cpu` still sorts above the plain build.
#    First in the list because enzymetk (step 5) depends on an unpinned `torch`: installed
#    here, that resolves to "already satisfied" instead of pulling the CUDA build.
# 2. esm with --no-deps, then its real dependencies by hand. Its declared list requires
#    torchtext, which has no aarch64 wheel AND no sdist, so a plain `pip install esm`
#    cannot succeed on arm64 at all. The list below is the traced import set of
#    esm.sdk.api / esm.models.esm3, minus what torch already provides. flash_attn is NOT
#    among them: every one of its imports in esm sits inside try/except ImportError, and
#    use_flash_attn defaults to False, so CPU inference is the supported path.
#    tenacity and httpx are needed because `from esm.sdk.api import ...` first executes
#    esm/sdk/__init__.py, which imports the Forge HTTP client whether or not you use it.
# 3. build-essential installed and purged inside this one RUN. zstd (manylinux aarch64
#    wheels stop at cp311) and biotraj (a hard biotite dep publishing x86_64 linux wheels
#    only) must compile. Layers are additive, so purging in a later step would leave the
#    ~250 MB in the image anyway. zstd is genuinely required — esm/utils/misc.py imports
#    it at module level.
# 4. transformers<4.48.2 is esm's own pin, which --no-deps skipped. It matters:
#    EsmSequenceTokenizer subclasses PreTrainedTokenizerFast, and subclassing is exactly
#    where transformers version drift breaks.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir "torch==2.9.1" \
        --index-url "$TORCH_INDEX_URL" \
        --extra-index-url https://pypi.org/simple && \
    pip install --no-cache-dir --no-deps "esm==3.2.3" && \
    pip install --no-cache-dir \
        attrs biotite brotli cloudpathlib einops msgpack msgpack-numpy zstd tenacity httpx && \
    pip install --no-cache-dir "transformers<4.48.2" && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/*

# enzymetk last, and from a branch rather than a pinned commit: only funce-updates has the
# EmbedESM3 that takes a device= and skips the interactive huggingface_hub login() — main
# still hard-codes .to("cuda") and would raise on any CPU host. Its install_requires leaves
# torch and transformers unpinned, so both stay exactly as installed above, and fair-esm is
# absent from that list, so the ESM-2/ESM-3 collision over the top-level `esm/` package
# cannot arise. Real deps, not --no-deps: enzymetk/__init__.py imports every step module.
#
# pip and the Docker layer cache both key on the ref, not the commit it resolves to, so
# `docker build --no-cache` is what picks up newer commits on the branch.
ARG ENZYMETK_REF=funce-updates
RUN pip install --no-cache-dir \
    "enzymetk @ git+https://github.com/moragroup/enzyme-tk-agentic.git@${ENZYMETK_REF}"

WORKDIR /app

# HF_HOME points at the mount so the 5.4 GB ESM3 snapshot survives `docker run --rm`.
# Set here as well as in the script because huggingface_hub freezes its cache paths at
# import time. Nothing is COPYed in — the script and its input arrive on the mount.
ENV HF_HOME=/app/output/hf

# No `VOLUME /app/output`. The mount lands on /app, its parent, and a VOLUME declared on a
# subdirectory of a bind mount shadows it with an empty anonymous volume: the container
# would see none of the host's output/, and everything written there would be thrown away
# by `docker run --rm`. Unbuffered so the script's own progress lines interleave with
# foldseek's instead of sitting in a block buffer until the process exits.
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "build_enzyme_db.py"]
