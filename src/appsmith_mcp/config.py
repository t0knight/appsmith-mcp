import os

# Default BiDi debugging port. Keep this a plain `BIDI_PORT = <int>` literal on
# its own line — launch.sh greps it to know which port to start Firefox on.
BIDI_PORT = 9222
# Override the port per process to run several MCP instances at once, each
# attached to its own Firefox window (one per Appsmith instance), e.g.
# APPSMITH_BIDI_PORT=9223.
BIDI_PORT = int(os.environ.get("APPSMITH_BIDI_PORT", BIDI_PORT))
BIDI_WS_URL = f"ws://127.0.0.1:{BIDI_PORT}/session"
FIREFOX_PROFILE = os.environ.get("APPSMITH_FIREFOX_PROFILE")
