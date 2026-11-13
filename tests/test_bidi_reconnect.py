import asyncio
import unittest
from unittest import mock

import websockets.exceptions

from appsmith_mcp import server
from appsmith_mcp.bidi import BiDiClient


class _SocketMorto:
    async def send(self, _):
        pass
    async def recv(self):
        raise websockets.exceptions.ConnectionClosed(None, None)


class _ClienteNovo:
    def __init__(self):
        self.chamadas = []
    async def connect(self):
        self.chamadas.append("connect")


class ReconexaoTests(unittest.TestCase):
    def test_conexao_fechada_descarta_socket_e_sessao(self):
        client = BiDiClient()
        client.ws = _SocketMorto()
        client.session_id = "s1"
        client.context_id = "c1"
        with self.assertRaises(ConnectionError):
            asyncio.run(client._send("browsingContext.getTree", {}))

        self.assertIsNone(client.ws)
        self.assertIsNone(client.session_id)
        self.assertIsNone(client.context_id)

    def test_ensure_ready_refaz_bootstrap_apos_reconectar(self):
        cliente = _ClienteNovo()
        with mock.patch.object(server, "client", cliente), mock.patch.object(server, "ready", True):
            asyncio.run(server.ensure_ready())
        
        self.assertEqual(cliente.chamadas, ["connect"])
