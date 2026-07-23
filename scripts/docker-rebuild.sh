#!/usr/bin/env bash
# docker-rebuild.sh — Prune Docker disk space and rebuild containers.
#
# Usage:
#   ./scripts/docker-rebuild.sh

set -euo pipefail

echo "── Docker disk usage before cleanup ──"
docker system df

echo ""
echo "── Pruning unused images and build cache ──"
docker image prune -af
docker builder prune -af

echo ""
echo "── Docker disk usage after cleanup ──"
docker system df

echo ""
echo "── Building and starting containers (detached) ──"

# docker compose up --build -d
docker compose up --build -d --scale worker=1

echo ""
echo "Done ✓"
