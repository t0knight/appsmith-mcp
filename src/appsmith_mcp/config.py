import os

BIDI_PORT = int(os.environ.get("APPSMITH_BIDI_PORT", "9222"))
BIDI_WS_URL = f"ws://127.0.0.1:{BIDI_PORT}/session"

# run_command and execute_js_functions can bypass the read-only execution policy, so they stay
# blocked unless the user starts the server with this variable set.
ALLOW_UNSAFE_EXECUTION = os.environ.get(
    "APPSMITH_ALLOW_UNSAFE_EXECUTION", ""
).strip().lower() in {"1", "true", "yes"}
