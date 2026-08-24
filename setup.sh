#!/usr/bin/env bash
# Backward-compatible entry point for the legacy source setup workflow.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
exec bash "$PROJECT_DIR/scripts/legacy/setup.sh" "$@"
