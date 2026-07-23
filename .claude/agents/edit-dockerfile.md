---
name: edit-dockerfile
description: Use PROACTIVELY when adding, removing, or modifying binary dependencies, system packages, or build steps in the Dockerfile for the EnzymeTK app.
tools: Read, Edit, Bash
---

# Edit Dockerfile Agent

Every change must preserve **multi-architecture** compatibility (`linux/amd64` + `linux/arm64`). All images are Linux containers — "Windows support" means Docker Desktop / WSL2, not native Windows images.

---

## 1. Platform Reference

Read the `Dockerfile` first — it is the source of truth for what is currently installed. Use its existing install sections as patterns for new additions.

### Base image

`python:3.12-slim` — **Debian 12 (Bookworm)**, `glibc`-based.

### Architecture identifiers

| Docker `--platform` | `uname -m` | `dpkg --print-architecture` | Common binary suffixes |
|---------------------|-----------|---------------------------|----------------------|
| `linux/amd64` | `x86_64` | `amd64` | `x86_64`, `amd64`, `linux64` |
| `linux/arm64` | `aarch64` | `arm64` | `aarch64`, `arm64` |

### What the slim image provides

| Included | NOT included (install + clean up in same `RUN` layer) |
|----------|------------------------------------------------------|
| `apt-get`, `python3`, `pip` | `gcc`, `g++`, `cmake`, `make`, `wget`, `curl`, `git` |

### Verifying Debian package availability

Before using `apt-get install <package>`, confirm it exists for **both** `amd64` and `arm64` at:
`https://packages.debian.org/bookworm/<package>`

---

## 2. Installation Priority

When a new external binary is needed, pick the **first** option that works:

1. **A — Multi-arch Docker image** (preferred): Use a multi-stage `COPY --from=<upstream>`. Verify the upstream image has a multi-arch manifest for both `linux/amd64` and `linux/arm64` (`docker manifest inspect <image:tag>`). Confirm the binary path inside the image is the same on both architectures — some images use arch-specific paths or wrapper scripts; if so, fall back to B.

2. **B — Arch-conditional static binary download**: Use `uname -m` to branch between `x86_64` and `aarch64` download URLs. Pin to a **specific release version** (not `latest`). The slim image lacks `wget`/`curl` — install them, download, then purge, all in one `RUN` layer.

3. **C — Build from source** (last resort): Install build deps, build with static linking when possible, copy the binary out, purge build deps — all in **one** `RUN` layer. Slow and fragile; avoid unless A and B are impossible.

4. **D — Single-arch only**: If the binary only supports one architecture, use a conditional guard (`uname -m`) that **warns and skips** on unsupported platforms instead of failing the build. Add a comment block explaining why multi-arch is not available and link the upstream tracking issue if one exists.

---

## 3. Rules

- [ ] Read the existing Dockerfile and follow its patterns before writing new install steps.
- [ ] Every binary install section has a header comment: what it is, which tool needs it, which option (A–D) was chosen and why.
- [ ] Combine related `RUN` steps. Clean up `/var/lib/apt/lists/*` and `/tmp/*`. Purge build-only deps in the same layer.
- [ ] Pin all versions — base image tags, binary releases, `COPY --from` image tags. No `latest` or floating tags.
- [ ] `COPY --from` stage aliases go at the **top** of the Dockerfile, before the main `FROM` line.
- [ ] Preserve `EXPOSE 8050`, `gunicorn` CMD, and `WORKDIR`. The `docker-compose.yml` worker service must still run Celery from the same image.
- [ ] Test both architectures:
  ```bash
  docker build --platform linux/amd64 -t etk-test-amd64 .
  docker build --platform linux/arm64 -t etk-test-arm64 .
  ```
