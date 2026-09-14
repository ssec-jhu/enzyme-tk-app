#!/usr/bin/env bash
# docker-rebuild.sh — Reclaim first, then rebuild.
#
# Order matters twice over:
#   * An image held by a running container is never removed, so a plain
#     `docker image prune` before `compose up` spares the very build it is
#     replacing. `compose down --rmi local` releases the containers first, so
#     the space is actually freed.
#   * Freeing BEFORE the build is what lets this run on a full disk. Building
#     first needs room for the old and new image at once — and if the build
#     then fails for want of space, the cleanup never runs.
#
# Trade-off: the stack is down for the length of the build, and a failed build
# leaves no image to roll back to. Re-run from a known-good commit if that bites.
#
# Usage:
#   ./scripts/docker-rebuild.sh

set -euo pipefail

echo "── Docker disk usage before ──"
docker system df

echo ""
echo "── Stopping stack, dropping its built images ──"
# --rmi local drops the images compose built (enzyme-tk-app-*) and spares any
# pinned by an `image:` field, so redis is not re-pulled. Named volumes are
# untouched without -v: job-outputs survives.
docker compose down --rmi local

echo ""
echo "── Building and starting containers (detached) ──"
docker compose up --build -d --scale worker=1

echo ""
echo "── Reclaiming unused build cache ──"
# AFTER the build, so the layers it just reused are still referenced and the
# next rebuild stays warm. Run this BEFORE the build and it deletes everything,
# torch included: with the images already gone, the whole cache chain reads as
# unused. An `--filter until=<age>` would instead spare the stale context
# entries that are the real growth — they were hours old when they cost 18.8GB.
docker builder prune -f
# Sweep any <none> left by an interrupted build; --rmi local only knows tags.
docker image prune -f

echo ""
echo "── Docker disk usage after ──"
docker system df

echo ""
echo "Done ✓"
