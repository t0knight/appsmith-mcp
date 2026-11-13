#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# usage: ./launch.sh [PORT] [PROFILE]
#
#   PORT     BiDi remote-debugging port (default: APPSMITH_BIDI_PORT or 9222).
#   PROFILE  Optional persistent Firefox profile for an isolated instance.
#
# Examples:
#   ./launch.sh
#   ./launch.sh 9222 appsmith-dev
#   ./launch.sh 9223 appsmith-staging
#
# Without PROFILE, the legacy single-instance behavior is preserved: Firefox is
# restarted with its default profile. With PROFILE, an additional isolated
# instance is launched without terminating other Firefox processes.

PORT="${1:-${APPSMITH_BIDI_PORT:-9222}}"
if [[ ! "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    echo "Invalid BiDi port: $PORT (expected 1-65535)" >&2
    exit 1
fi

PROFILE="${2:-}"
if [[ -n "$PROFILE" && ! "$PROFILE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "Invalid profile name. Use letters, digits, dots, underscores, or hyphens." >&2
    exit 1
fi

FF_ARGS=(--remote-debugging-port "$PORT")
if [[ -n "$PROFILE" ]]; then
    PROFILE_DIR="$SCRIPT_DIR/.firefox-profiles/$PROFILE"
    mkdir -p "$PROFILE_DIR"
    case "$(uname -s)" in
        MINGW* | MSYS* | CYGWIN*) PROFILE_DIR="$(cygpath -w "$PROFILE_DIR")" ;;
    esac
    FF_ARGS=(--profile "$PROFILE_DIR" --no-remote "${FF_ARGS[@]}")
fi

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
