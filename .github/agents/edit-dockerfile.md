# Edit Dockerfile Agent

**Trigger:** When adding, removing, or modifying binary dependencies, system
packages, or build steps in the `Dockerfile` (e.g. while integrating a new
tool via the [Create Tool Agent](create-tool.md)).

This agent ensures that every Dockerfile change preserves **cross-platform,
multi-architecture** compatibility so the image can be deployed on:

| Target | Architecture | Example environments |
|--------|-------------|----------------------|
| Apple Silicon Mac | `linux/arm64` | M1 / M2 / M3 local Docker Desktop |
| Intel / AMD Mac | `linux/amd64` | Older MacBook / Mac Pro Docker Desktop |
| Linux server | `linux/amd64` | CI runners, bare-metal, on-prem |
| Linux ARM server | `linux/arm64` | AWS Graviton, Ampere |
| Cloud Kubernetes | `linux/amd64`, `linux/arm64` | Azure AKS, GCP GKE, AWS EKS |
| Windows | `linux/amd64` | Docker Desktop (WSL2 backend) |

> [!IMPORTANT]
> Docker images in this project are **Linux containers**. "Windows support"
> means running under Docker Desktop / WSL2 on a Windows host — **not**
> producing a native Windows image. All instructions target `linux/amd64`
> and `linux/arm64`.

---

## 1. Decision Flowchart — How to Install a Binary

When a new external binary is needed, evaluate the options **in this order**.
Pick the first one that satisfies multi-arch support:

### Option A — Multi-arch Docker image (preferred)

If the upstream project publishes an official Docker image with multi-arch
manifests (`linux/amd64` + `linux/arm64`), use a multi-stage `COPY --from`:

```dockerfile
FROM upstream/image:tag AS new-bin
# ...
COPY --from=new-bin /path/to/binary /usr/local/bin/binary
```

**How to verify:** Run `docker manifest inspect upstream/image:tag` or check
Docker Hub / GitHub Container Registry for the manifest list. Both
`linux/amd64` and `linux/arm64` must be present.

> [!WARNING]
> Some multi-arch images store architecture-specific binaries at different
> paths or use a wrapper script to dispatch (e.g. FoldSeek). In that case
> `COPY --from` will silently copy the wrong binary. Test on both platforms
> or fall back to Option B.

### Option B — Official static / pre-built release binary

If the project publishes pre-built static binaries for both `x86_64` and
`aarch64` / `arm64`, download the correct one at build time:

```dockerfile
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then \
        URL="https://example.com/tool-linux-amd64.tar.gz"; \
    elif [ "$ARCH" = "aarch64" ]; then \
        URL="https://example.com/tool-linux-arm64.tar.gz"; \
    else \
        echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    wget -q "$URL" -O /tmp/tool.tar.gz && \
    tar -xzf /tmp/tool.tar.gz -C /tmp && \
    cp /tmp/tool/bin/tool /usr/local/bin/tool && \
    chmod +x /usr/local/bin/tool && \
    rm -rf /tmp/tool*
```

Pin to a **specific release version** (not `latest`) so builds are
reproducible.

### Option C — Build from source

If neither pre-built binaries nor multi-arch images exist, build from source
inside the Dockerfile. Use static linking when possible to avoid runtime
library mismatches across cached layers:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        cmake g++ zlib1g-dev ca-certificates wget && \
    wget -q https://github.com/example/tool/archive/refs/tags/vX.Y.Z.tar.gz \
         -O /tmp/tool.tar.gz && \
    tar -xzf /tmp/tool.tar.gz -C /tmp && \
    cd /tmp/tool-X.Y.Z && mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release -DSTATIC=ON && \
    make -j"$(nproc)" && \
    mv tool /usr/local/bin/tool && \
    cd / && rm -rf /tmp/tool* && \
    apt-get purge -y cmake g++ && \
    apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
```

> [!CAUTION]
> Building from source is the **least preferred** option. It makes builds
> slow, non-reproducible if upstream changes, and may introduce
> architecture-specific compiler flags. Use only as a last resort.

### Option D — Architecture NOT supported

If the binary is only available for a single architecture and cannot be
built from source for the other, you **must**:

1. **Add a prominent comment block** in the Dockerfile above the install
   step explaining:
   - Which architectures are supported and which are not.
   - Why multi-arch is not possible (e.g. closed-source, GPU-only, etc.).
   - The upstream issue / tracking URL (if any) requesting multi-arch.
2. **Use a conditional guard** so the build does not fail on unsupported
   architectures:
   ```dockerfile
   RUN ARCH=$(uname -m) && \
       if [ "$ARCH" = "x86_64" ]; then \
           # install the binary ... \
       else \
           echo "WARNING: tool-name is only available for x86_64." && \
           echo "WARNING: The tool will be unavailable on this platform." ; \
       fi
   ```
3. **Report to the user** in your response which platforms will lack the
   binary and suggest workarounds (e.g. emulation via `--platform`).

---

## 2. Mandatory Rules for Every Dockerfile Edit

### 2.1 Comment blocks

Every new binary install section **must** have a header comment explaining:
- What the binary is and which tool requires it.
- Which installation option (A / B / C / D) was chosen and why.
- Any platform caveats.

Follow the existing comment style in the Dockerfile (see the Diamond and
FoldSeek sections for reference).

### 2.2 Layer hygiene

- Combine related `RUN` steps to minimise image layers.
- Always clean up caches: `rm -rf /var/lib/apt/lists/*`, `/tmp/*`.
- Purge build-only dependencies (`cmake`, `g++`, etc.) in the same `RUN`
  layer if building from source.

### 2.3 No `apt-get install` of arch-specific packages without verification

Before using `apt-get install <package>`:
- Confirm the Debian/Ubuntu package is available for **both** `amd64` and
  `arm64` in the base image's package repository.
- Pure-Python and architecture-independent packages are fine.
- If the package is only available for one architecture, fall back to
  Option B or C above.

### 2.4 Pin versions

- Pin binary versions explicitly (e.g. `v2.1.9`, not `latest`).
- Pin base image tags (e.g. `python:3.12-slim`, not `python:latest`).

### 2.5 Multi-stage `COPY --from` hygiene

When using `COPY --from=<stage>`:
- Declare the stage alias at the **top** of the Dockerfile, before the main
  `FROM` line, grouped with other binary stages.
- Verify the binary path is architecture-independent in the source image.

### 2.6 Do not break existing services

- The final image must still expose port `8050` and run the `gunicorn` CMD.
- The `docker-compose.yml` `worker` service must still be able to run
  Celery from the same image.

---

## 3. Verification Checklist

After editing the Dockerfile, verify the following before concluding:

- [ ] Every new binary section has an explanatory comment block.
- [ ] The chosen installation method is the highest-priority option that
      works (A > B > C > D).
- [ ] Architecture detection uses `uname -m` with handlers for both
      `x86_64` and `aarch64`.
- [ ] Unsupported architectures either fail loudly (`exit 1`) or warn and
      skip, with a comment explaining why.
- [ ] No leftover build artifacts or caches in the final image.
- [ ] Versions are pinned, not floating.
- [ ] Existing `EXPOSE`, `CMD`, and `WORKDIR` directives are preserved.

> [!TIP]
> To test both architectures locally on an Apple Silicon Mac:
> ```bash
> docker build --platform linux/amd64 -t etk-test-amd64 .
> docker build --platform linux/arm64 -t etk-test-arm64 .
> ```

---

## 4. Existing Binary Reference

Current binaries installed in the Dockerfile and their methods:

| Binary | Method | Architectures | Notes |
|--------|--------|---------------|-------|
| Diamond | A — `COPY --from=buchfink/diamond:latest` | amd64, arm64 | Multi-arch image verified |
| FoldSeek | B — arch-conditional `wget` | amd64 (`avx2`), arm64 | Upstream image has path issues; static download used instead |

When adding a new binary, update this table in the agent file as well.
