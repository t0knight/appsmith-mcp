import asyncio
import unittest
from unittest import mock

import websockets.exceptions

from appsmith_mcp import server
from appsmith_mcp.bidi import BiDiClient


class _DeadSocket:
    async def send(self, _):
        pass
    async def recv(self):
        raise websockets.exceptions.ConnectionClosed(None, None)


class _FreshClient:
    def __init__(self):
        self.ws = None
        self.calls = []
    async def connect(self):
        self.calls.append("connect")
    async def run_snippet(self, _snippet, **_kwargs):
        self.calls.append("bootstrap")
        return True


class ReconnectTests(unittest.TestCase):
    def test_closed_connection_drops_socket_and_session(self):
        client = BiDiClient()
        client.ws = _DeadSocket()
        client.session_id = "s1"
        client.context_id = "c1"
        with self.assertRaises(ConnectionError):
            asyncio.run(client._send("browsingContext.getTree", {}))

        self.assertIsNone(client.ws)
        self.assertIsNone(client.session_id)
        self.assertIsNone(client.context_id)

    def test_ensure_ready_rebootstraps_after_reconnect(self):
        fresh_client = _FreshClient()
        with mock.patch.object(server, "client", fresh_client), mock.patch.object(server, "ready", True):
            asyncio.run(server.ensure_ready())

        self.assertEqual(fresh_client.calls, ["connect", "bootstrap"])
