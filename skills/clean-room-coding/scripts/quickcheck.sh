#!/usr/bin/env bash
# Deterministic pre-flight check for a Clean Room Coding project: installation
# health, licence discovery on Zone R, and the isolation/evidence audit.
# Usage: quickcheck.sh [project-path]
set -euo pipefail

PROJECT_PATH="${1:-.}"

echo "== cleanroom doctor =="
cleanroom --project "$PROJECT_PATH" doctor

echo
echo "== cleanroom licence (Zone R) =="
cleanroom --project "$PROJECT_PATH" licence || true

echo
echo "== cleanroom audit (isolation + evidence chain) =="
cleanroom --project "$PROJECT_PATH" audit
