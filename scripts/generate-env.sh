#!/usr/bin/env bash
# generate-env.sh — Generate the gitignored `.env` with fresh admin secrets.
#
# Writes a `.env` file to the repository root (one directory up from this
# script) using scripts/template.env, filling in freshly generated random
# values for ETK_ADMIN_TOKEN and ETK_SECRET_KEY. 
# NEVER commit the resulting `.env` file.
#
# Production mode is preserved across a rotation: re-running this to get fresh
# secrets will NOT silently switch a deployment back to local defaults. Pass a
# flag to change it deliberately.
#
# Usage:
#   ./scripts/generate-env.sh              # keep whatever mode .env already had
#   ./scripts/generate-env.sh --production # ...and switch production mode ON
#   ./scripts/generate-env.sh --local      # ...and switch production mode OFF

set -euo pipefail

if [[ $# -gt 1 ]]; then
    echo "Error: too many arguments (expected at most one of --production, --local)" >&2
    exit 1
fi

MODE_OVERRIDE=""
case "${1:-}" in
    --production) MODE_OVERRIDE="true" ;;
    --local)      MODE_OVERRIDE="false" ;;
    "")           ;;
    *)
        echo "Error: unknown option '${1}' (expected --production, --local, or nothing)" >&2
        exit 1
        ;;
esac

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

# Carry the existing production setting forward. Rotating secrets must never be
# the thing that quietly turns a public deployment back into an unlimited one,
# so the old value wins over the template's default and only an explicit flag
# overrides it. `|| true` because grep exits 1 on no match under `set -e`.
PRODUCTION_MODE="false"
if [[ -f "${TARGET}" ]]; then
    EXISTING="$(grep -E '^[[:space:]]*APP_IN_PRODUCTION_MODE=' "${TARGET}" | tail -n 1 || true)"
    # Read the value exactly as the app does, never more strictly. Compose strips an
    # inline comment and surrounding quotes before the app sees it, and
    # submission_limits.py lowercases what is left, so ="true", ='true', =TRUE and
    # =true # prod all switch the cap ON. Matching only bare lowercase true here would
    # drop a live cap on rotation — the exact silent regression this carry-forward
    # exists to prevent. (tr, not ${x,,}: macOS ships bash 3.2.)
    VALUE="$(printf '%s' "${EXISTING#*=}" | tr -d "\"'" | tr '[:upper:]' '[:lower:]')"
    if [[ "${VALUE%%#*}" =~ ^[[:space:]]*(1|true|yes|on)[[:space:]]*$ ]]; then
        PRODUCTION_MODE="true"
    fi
fi
if [[ -n "${MODE_OVERRIDE}" ]]; then
    PRODUCTION_MODE="${MODE_OVERRIDE}"
fi

echo "── Generating admin secrets ──"
ETK_ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
ETK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

echo "── Writing ${TARGET} ──"
# Use awk for a literal, escape-safe substitution of the placeholders.
awk -v token="${ETK_ADMIN_TOKEN}" -v key="${ETK_SECRET_KEY}" -v prod="${PRODUCTION_MODE}" '
    { gsub(/__ETK_ADMIN_TOKEN__/, token); gsub(/__ETK_SECRET_KEY__/, key) }
    # Uncomment the switch when production mode is wanted; otherwise the
    # template line stays commented and the app defaults to local.
    prod == "true" && /^# APP_IN_PRODUCTION_MODE=true$/ { print "APP_IN_PRODUCTION_MODE=true"; next }
    { print }
' "${TEMPLATE}" > "${TARGET}"

echo ""
echo "Done ✓  Created ${TARGET}"
if [[ "${PRODUCTION_MODE}" == "true" ]]; then
    echo "Production mode: ON  (per-session job cap enforced)"
else
    echo "Production mode: off (local defaults, no submission limits)"
    echo "  Turn it on with: ./scripts/generate-env.sh --production"
fi
echo "This file is gitignored — never commit it."
