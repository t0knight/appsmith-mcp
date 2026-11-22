import asyncio
import json

import websockets

from appsmith_mcp.config import BIDI_WS_URL
from appsmith_mcp.snippets import SAVE_WAIT_JS


def build_snippet_script(snippet, json_constants=None, wait_for_save=False):
    """Compose the page-context expression for a snippet: JSON constants become scoped
    consts, optionally chained through SAVE_WAIT_JS."""
    prelude = "".join(
        f"const {name} = {json.dumps(value)};\n"
        for name, value in (json_constants or {}).items()
    )
    if wait_for_save:
        body = f"return await ({SAVE_WAIT_JS})(await ({snippet}));"
    else:
        body = f"return {snippet};"
    return f"(async () => {{\n{prelude}{body}\n}})()"


class BiDiClient:
    def __init__(self):
        self.ws = None
        self.session_id = None
        self.context_id = None
        self.next_id = 1
        self.lock = asyncio.Lock()

    async def connect(self):
        if self.ws is not None and self.session_id is not None:
            return
        try:
            self.ws = await websockets.connect(BIDI_WS_URL, max_size=None)
        except OSError as e:
            self.ws = None
            raise RuntimeError(
                f"Can't reach the Firefox BiDi bridge at {BIDI_WS_URL} — no Firefox is listening on "
                f"that port. Launch it with `./launch.sh <port> <profile>`, log in, open the "
                f"Appsmith editor and retry. (Underlying error: {e})"
            ) from e
        try:
            result = await self._send("session.new", {"capabilities": {"alwaysMatch": {}}})
        except RuntimeError as e:
            if "Maximum number of active sessions" in str(e) or "session not created" in str(e):
                try:
                    await self.ws.close()
                except Exception:
                    pass
                self.ws = None
                raise RuntimeError(
                    "Firefox already has an active BiDi session from a previous MCP run "
                    "(only one is allowed). Close and relaunch Firefox with "
                    "`./launch.sh <port> <profile>`, then retry. "
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
        return next(
            (ctx.get("url") for ctx in tree["contexts"] if ctx["context"] == self.context_id),
            None,
        )

    async def run_snippet(self, snippet, json_constants=None, wait_for_save=False):
        """Run a fixed JS snippet. `json_constants` is a dict of name->python value;
        each value is JSON-serialized and injected as scoped consts. When
        `wait_for_save` is set, the result is passed through SAVE_WAIT_JS, which
        resolves once the page save-cycle has settled so a follow-up call can't
        race a rollback. The snippet itself is fixed code authored in this repo —
        never accept snippets from tool input."""
        return await self._evaluate(build_snippet_script(snippet, json_constants, wait_for_save))

    async def _send(self, method, params, timeout=60):
        async with self.lock:
            if self.ws is None:
                raise ConnectionError("not connected to Firefox")
            cmd_id = self.next_id
            self.next_id += 1
            try:
                await self.ws.send(json.dumps({"id": cmd_id, "method": method, "params": params}))
                while True:
                    msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=timeout))
                    if msg.get("id") == cmd_id:
                        if msg.get("type") == "error":
                            raise RuntimeError(f"BiDi error: {msg}")
                        return msg.get("result", {})
            except websockets.exceptions.ConnectionClosed as exc:
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
            ex = result.get("exceptionDetails", {})
            text = ex.get("text", "Unknown evaluation error")
            stack = ex.get("stackTrace", {}).get("callFrames", [])
            if stack:
                text += f"\n  at {stack[0].get('functionName', '<anonymous>')} ({stack[0].get('url')}:{stack[0].get('lineNumber')})"
            raise RuntimeError(f"Snippet error: {text}")
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
