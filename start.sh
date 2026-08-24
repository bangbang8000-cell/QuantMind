#!/usr/bin/env bash
# Backward-compatible entry point for the development launcher.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$PROJECT_DIR/scripts/dev/start.sh" "$@"
