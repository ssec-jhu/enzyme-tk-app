#!/usr/bin/env bash
# generate-env.sh — Generate the gitignored `.env` with fresh admin secrets.
#
# Writes a `.env` file to the repository root (one directory up from this
# script) using scripts/template.env, filling in freshly generated random
# values for ETK_ADMIN_TOKEN and ETK_SECRET_KEY. 
# NEVER commit the resulting `.env` file.
#
# Usage:
#   ./scripts/generate-env.sh

set -euo pipefail

# Resolve paths relative to this script so it works from any working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEMPLATE="${SCRIPT_DIR}/template.env"
TARGET="${ROOT_DIR}/.env"

if [[ ! -f "${TEMPLATE}" ]]; then
    echo "Error: template not found at ${TEMPLATE}" >&2
    exit 1
fi

# Guard an existing .env behind an interactive confirmation.
if [[ -f "${TARGET}" ]]; then
    echo "A .env file already exists at ${TARGET}"
    read -r -p "Overwrite it with newly generated secrets? [y/N] " reply
    if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
        echo "Aborted — existing .env left untouched."
        exit 0
    fi
fi

echo "── Generating admin secrets ──"
ETK_ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
ETK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

echo "── Writing ${TARGET} ──"
# Use awk for a literal, escape-safe substitution of the placeholders.
awk -v token="${ETK_ADMIN_TOKEN}" -v key="${ETK_SECRET_KEY}" '
    { gsub(/__ETK_ADMIN_TOKEN__/, token); gsub(/__ETK_SECRET_KEY__/, key); print }
' "${TEMPLATE}" > "${TARGET}"

echo ""
echo "Done ✓  Created ${TARGET}"
echo "This file is gitignored — never commit it."
