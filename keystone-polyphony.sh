#!/usr/bin/env bash
# keystone-polyphony.sh
# Legacy entry point for Keystone Polyphony.
# Redirects to the unified 'polyphony' CLI.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/polyphony" start "$@"
