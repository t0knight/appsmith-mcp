#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# usage: ./launch.sh [PORT] [PROFILE]
#
#   PORT     BiDi remote-debugging port. Defaults to the BIDI_PORT literal in
#            src/appsmith_mcp/config.py (9222).
#   PROFILE  Optional dedicated Firefox profile name. When given, an ADDITIONAL
#            isolated Firefox instance is launched (its own profile dir +
#            --no-remote) that keeps its own Appsmith login — so you can run
#            several windows at once, one per Appsmith instance / BiDi port, each
#            logged into a different Appsmith. The profile is persistent: log in
#            once and the session sticks across relaunches.
#
# Examples (two instances side by side):
#   ./launch.sh 9222 appsmith             # -> matches MCP "appsmith"
#   ./launch.sh 9223 appsmith-2           # -> matches MCP "appsmith-2" (env APPSMITH_BIDI_PORT=9223)
#
# Without a PROFILE the legacy single-instance behavior runs: kill any running
# Firefox and relaunch on PORT using the default profile.

PORT="${1:-}"
if [[ -z "$PORT" ]]; then
    PORT="$(sed -n 's/^BIDI_PORT *= *\([0-9][0-9]*\).*/\1/p' "$SCRIPT_DIR/src/appsmith_mcp/config.py" | head -n1)"
fi
PORT="${PORT:-9222}"

PROFILE="${2:-}"

# Build the Firefox arg list. With a profile we add an isolated, persistent
# profile dir and --no-remote so this instance doesn't merge into an existing one.
# -remote-allow-system-access is required by newer Firefox for BiDi script.evaluate
# in the system realm (without it: "System access is required").
FF_ARGS=(--remote-debugging-port "$PORT" -remote-allow-system-access)
if [[ -n "$PROFILE" ]]; then
    PROFILE_DIR="$SCRIPT_DIR/.firefox-profiles/$PROFILE"
    mkdir -p "$PROFILE_DIR"
    case "$(uname -s)" in
        MINGW* | MSYS* | CYGWIN*) PROFILE_DIR="$(cygpath -w "$PROFILE_DIR")" ;;
    esac
    FF_ARGS=(--profile "$PROFILE_DIR" --no-remote "${FF_ARGS[@]}")
fi

# Firefox can't enable the remote-debugging port on an already-running instance, so in
# single-instance mode we quit it first, then relaunch with the port. Platform-specific
# because there's no portable way to kill/launch a GUI app. In profile mode we do NOT
# kill anything, so a second instance can run alongside the first.
case "$(uname -s)" in
    Darwin)
        if [[ -z "$PROFILE" ]]; then
            pkill -f firefox || true
            sleep 2
        fi
        open -na Firefox --args "${FF_ARGS[@]}"
        ;;
    Linux)
        if ! command -v firefox >/dev/null 2>&1; then
            echo "firefox not found in PATH" >&2
            exit 1
        fi
        if [[ -z "$PROFILE" ]]; then
            pkill -f firefox || true
            sleep 2
        fi
        firefox "${FF_ARGS[@]}" >/dev/null 2>&1 &
        ;;
    MINGW* | MSYS* | CYGWIN*)
        if [[ -z "$PROFILE" ]]; then
            taskkill //F //IM firefox.exe >/dev/null 2>&1 || true
            sleep 2
        fi
        for ff in \
            "/c/Program Files/Mozilla Firefox/firefox.exe" \
            "/c/Program Files (x86)/Mozilla Firefox/firefox.exe"; do
            if [[ -x "$ff" ]]; then
                "$ff" "${FF_ARGS[@]}" &
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
