import asyncio
import json

import websockets

from appsmith_mcp.config import BIDI_WS_URL
from appsmith_mcp.snippets import SAVE_WAIT_JS


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
        self.ws = await websockets.connect(BIDI_WS_URL, max_size=None)
        result = await self._send("session.new", {"capabilities": {"alwaysMatch": {}}})
        self.session_id = result.get("sessionId")
        tree = await self._send("browsingContext.getTree", {})
        self.context_id = tree["contexts"][0]["context"]

    async def reset(self):
        if self.ws is not None:
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

    async def run_snippet(self, snippet, json_constants=None, wait_for_save=False):
        """Run a fixed JS snippet. `json_constants` is a dict of name->python value;
        each value is JSON-serialized and injected as scoped consts. When
        `wait_for_save` is set, the result is passed through SAVE_WAIT_JS, which
        resolves once the page save-cycle has settled so a follow-up call can't
        race a rollback. The snippet itself is fixed code authored in this repo —
        never accept snippets from tool input."""
        prelude = "".join(
            f"const {name} = {json.dumps(value)};\n"
            for name, value in (json_constants or {}).items()
        )
        if wait_for_save:
            body = f"return await ({SAVE_WAIT_JS})(await ({snippet}));"
        else:
            body = f"return {snippet};"
        wrapped = f"(async () => {{\n{prelude}{body}\n}})()"
        return await self._evaluate(wrapped)

    async def _send(self, method, params):
        async with self.lock:
            cmd_id = self.next_id
            self.next_id += 1
            await self.ws.send(json.dumps({"id": cmd_id, "method": method, "params": params}))
            while True:
                msg = json.loads(await self.ws.recv())
                if msg.get("id") == cmd_id:
                    if msg.get("type") == "error":
                        raise RuntimeError(f"BiDi error: {msg}")
                    return msg.get("result", {})

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
