#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="$(sed -n 's/^BIDI_PORT *= *\([0-9]*\).*/\1/p' "$SCRIPT_DIR/src/appsmith_mcp/config.py")"
: "${PORT:?could not read BIDI_PORT from src/appsmith_mcp/config.py}"

# Firefox can't enable the remote-debugging port on an already-running instance, so quit
# it first, then relaunch with the port. Platform-specific because there's no portable way
# to kill/launch a GUI app.
case "$(uname -s)" in
    Darwin)
        pkill -f firefox || true
        sleep 2
        open -na Firefox --args --remote-debugging-port "$PORT"
        ;;
    Linux)
        if ! command -v firefox >/dev/null 2>&1; then
            echo "firefox not found in PATH" >&2
            exit 1
        fi
        pkill -f firefox || true
        sleep 2
        firefox --remote-debugging-port "$PORT" >/dev/null 2>&1 &
        ;;
    MINGW* | MSYS* | CYGWIN*)
        taskkill //F //IM firefox.exe >/dev/null 2>&1 || true
        sleep 2
        for ff in \
            "/c/Program Files/Mozilla Firefox/firefox.exe" \
            "/c/Program Files (x86)/Mozilla Firefox/firefox.exe"; do
            if [[ -x "$ff" ]]; then
                "$ff" --remote-debugging-port "$PORT" &
                exit 0
            fi
        done
        echo "Firefox not found under Program Files" >&2
        exit 1
        ;;
    *)
        echo "Unsupported OS: $(uname -s). Launch Firefox manually with --remote-debugging-port $PORT" >&2
        exit 1
        ;;
esac
