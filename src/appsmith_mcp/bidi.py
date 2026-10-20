import asyncio
import json

import websockets

from appsmith_mcp.config import BIDI_PORT, BIDI_WS_URL
from appsmith_mcp.snippets import SAVE_WAIT_JS


def build_snippet_script(snippet, json_constants=None, js_helpers=None, wait_for_save=False):
    """Compose the page-context expression for a snippet: JSON constants and raw JS helpers
    become scoped consts, optionally chained through SAVE_WAIT_JS."""
    prelude = "".join(
        f"const {name} = {json.dumps(value)};\n"
        for name, value in (json_constants or {}).items()
    )
    prelude += "".join(
        f"const {name} = ({code});\n"
        for name, code in (js_helpers or {}).items()
    )
    if wait_for_save:
        body = f"return await ({SAVE_WAIT_JS})(await ({snippet}));"
    else:
        body = f"return {snippet};"
    return f"(async () => {{\n{prelude}{body}\n}})()"


class BiDiClient:
    def __init__(self):
        self.ws = None
        self.context_id = None
        self.session_id = None
        self.next_id = 1
        self.lock = asyncio.Lock()

    async def connect(self):
        if self.ws is not None and self.session_id is not None:
            return
        try:
            self.ws = await websockets.connect(BIDI_WS_URL, max_size=None)
        except OSError as e:
            self.ws = None
            # Connection refused (WinError 1225 / ECONNREFUSED): no Firefox listening on the BiDi
            # port. Turn the cryptic OS error into an actionable instruction instead of failing raw.
            raise RuntimeError(
                f"Can't reach the Firefox BiDi bridge at {BIDI_WS_URL} — no Firefox is listening on "
                f"that port. Launch it, e.g. `./launch.sh <port> <profile>` (default port 9222; this "
                f"instance uses APPSMITH_BIDI_PORT if set) or `python login.py <.env file>` to relaunch "
                f"and log in, then open the Appsmith editor and retry. (Underlying error: {e})"
            ) from e
        try:
            result = await self._send("session.new", {"capabilities": {"alwaysMatch": {}}})
        except RuntimeError as e:
            # Firefox allows only ONE active BiDi session. If a previous MCP process was killed
            # without cleanly ending its session (the atexit session.end doesn't reliably run on
            # a Windows kill), the slot leaks and session.new fails here — and we can't end the
            # orphan from this connection. Turn the cryptic BiDi error into actionable guidance.
            if "Maximum number of active sessions" in str(e) or "session not created" in str(e):
                try:
                    await self.ws.close()
                except Exception:
                    pass
                self.ws = None
                raise RuntimeError(
                    "Firefox already has an active BiDi session from a previous MCP run "
                    "(only one is allowed). Close and relaunch Firefox — e.g. "
                    "./launch.sh <port> <profile> or `python login.py <.env file>` — then retry. "
                    "It can also be held by another Claude Code session running its own appsmith-mcp."
                ) from e
            raise
        self.session_id = result.get("sessionId")
        tree = await self._send("browsingContext.getTree", {})
        self.context_id = self._pick_editor_context(tree.get("contexts", []))

    @staticmethod
    def _pick_editor_context(contexts):
        """Choose the tab actually showing Appsmith rather than blindly taking contexts[0], so a
        stray/extra tab can't hijack the session. Prefers an editor tab, then the dashboard/app,
        then any real page, falling back to the first context."""
        if not contexts:
            raise RuntimeError("No browsing contexts (tabs) available in Firefox")

        def score(ctx):
            url = ctx.get("url") or ""
            if "/edit" in url:
                return 3
            if "/applications" in url or "/app/" in url:
                return 2
            if url and url != "about:blank":
                return 1
            return 0

        return max(contexts, key=score)["context"]

    async def reset(self):
        if self.ws is not None:
            # End the session before dropping the socket. Closing the websocket alone can
            # leave Firefox holding the session, and since it only allows one at a time
            # every later reconnect then fails with "Maximum number of active sessions".
            if self.session_id is not None:
                try:
                    await asyncio.wait_for(self._send("session.end", {}), timeout=3)
                except Exception:
                    pass
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.session_id = None
        self.context_id = None
        self.next_id = 1

    async def close(self):
        """Cleanly end the BiDi session and close the websocket so Firefox frees the slot."""
        if self.ws is not None:
            try:
                await self._send("session.end", {})
            except Exception:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.session_id = None
        self.context_id = None
        self.next_id = 1

    async def navigate(self, url):
        await self._send("browsingContext.navigate", {
            "context": self.context_id,
            "url": url,
            "wait": "complete",
        })

    async def reload(self):
        await self._send("browsingContext.reload", {
            "context": self.context_id,
            "wait": "complete",
        })

    async def get_url(self):
        """Return the URL currently loaded in the attached browsing context."""
        tree = await self._send("browsingContext.getTree", {})
        return tree["contexts"][0].get("url")

    async def run_snippet(self, snippet, json_constants=None, js_helpers=None, wait_for_save=False):
        """Run a fixed JS snippet. `json_constants` is a dict of name->python value;
        each value is JSON-serialized and injected as scoped consts. `js_helpers`
        is a dict of name->raw-JS-expression (e.g. a shared function); each is
        injected as a scoped const *without* JSON-encoding, so the snippet's IIFE
        can close over and call it. When `wait_for_save` is set, the result is
        passed through SAVE_WAIT_JS, which resolves once the page save-cycle has
        settled so a follow-up call can't race a rollback. Both `json_constants`
        and `js_helpers` are fixed code authored in this repo — never accept
        snippets from tool input."""
        return await self._evaluate(build_snippet_script(snippet, json_constants, js_helpers, wait_for_save))

    async def capture_screenshot(self, clip=None, origin=None):
        """Return a base64-encoded PNG of the attached browsing context. Reuses the single
        existing BiDi session (Firefox allows only one active session). `origin="document"`
        captures the whole scrollable page instead of the viewport; `clip={"type":"box",
        "x","y","width","height"}` restricts capture to a region (viewport coords)."""
        params = {"context": self.context_id}
        if origin:
            params["origin"] = origin
        if clip:
            params["clip"] = clip
        try:
            result = await self._send("browsingContext.captureScreenshot", params)
        except RuntimeError as exc:
            # `origin`/`clip` were added to captureScreenshot after the command shipped; fall
            # back to the bare form on Firefox builds that reject them.
            if "invalid argument" not in str(exc) or len(params) == 1:
                raise
            result = await self._send("browsingContext.captureScreenshot",
                                      {"context": self.context_id})
        return result.get("data")

    async def _send(self, method, params, timeout=60):
        async with self.lock:
            if self.ws is None:
                raise ConnectionError("not connected to Firefox")
            cmd_id = self.next_id
            self.next_id += 1
            try:
                await self.ws.send(json.dumps({"id": cmd_id, "method": method, "params": params}))
                while True:
                    # Bound the wait so a hung script.evaluate (e.g. an infinite loop in a
                    # snippet, or a navigation mid-eval) can't block the server forever —
                    # ensure_ready's reconnect path can then recover.
                    msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=timeout))
                    if msg.get("id") == cmd_id:
                        if msg.get("type") == "error":
                            raise RuntimeError(f"BiDi error: {msg}")
                        return msg.get("result", {})
            except websockets.ConnectionClosed as exc:
                # The browser went away mid-command; distinguish this from an Appsmith-side
                # failure so the caller knows the write may have half-landed. Drop the dead
                # socket so the next ensure_ready() reconnects instead of reusing it forever.
                self.ws = None
                self.session_id = None
                self.context_id = None
                self.next_id = 1
                raise ConnectionError(
                    f"the Firefox connection dropped while running `{method}` — the browser "
                    "was closed or crashed. Any batch in flight may have been applied "
                    "partially; re-read state before retrying."
                ) from exc

    async def _evaluate(self, expression):
        result = await self._send("script.evaluate", {
            "expression": expression,
            "target": {"context": self.context_id},
            "awaitPromise": True,
            "resultOwnership": "none",
        })
        if result.get("type") == "exception":
            raise RuntimeError(f"JS exception: {result.get('exceptionDetails')}")
        return self._unwrap_remote_value(result.get("result"))

    @staticmethod
    def _unwrap_remote_value(remote_value):
        """Convert a BiDi RemoteValue dict into a plain Python value."""
        if remote_value is None:
            return None
        t = remote_value.get("type")
        if t in ("string", "number", "boolean"):
            return remote_value.get("value")
        if t == "null":
            return None
        if t == "undefined":
            return None
        if t == "array":
            return [BiDiClient._unwrap_remote_value(x) for x in remote_value.get("value", [])]
        if t == "object":
            return {
                BiDiClient._unwrap_remote_value(k) if isinstance(k, dict) else k: BiDiClient._unwrap_remote_value(val)
                for k, val in remote_value.get("value", [])
            }
        return remote_value
