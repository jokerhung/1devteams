import asyncio
import json

import pytest

from app.acp.jsonrpc import ACPProcessExited, JsonRpcConnection


async def test_junk_id_dispatch_and_concurrent_handler():
    release = asyncio.Event()
    completed = asyncio.Event()

    async def peer(reader, writer):
        message = json.loads(await reader.readline())
        writer.write(b"garbage\n[]\n\n")
        writer.write(
            json.dumps({"jsonrpc": "2.0", "id": "reverse", "method": "slow", "params": {}}).encode() + b"\n"
        )
        writer.write(
            json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"ok": True}}).encode() + b"\n"
        )
        await writer.drain()
        response = json.loads(await reader.readline())
        assert response["id"] == "reverse" and response["result"] == {"done": True}
        completed.set()
        writer.close()
        await writer.wait_closed()

    async def handler(method, params):
        await release.wait()
        return {"done": True}

    async def notify(method, params):
        pass

    server = await asyncio.start_server(peer, "127.0.0.1", 0)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
        rpc = JsonRpcConnection(reader, writer, handler, notify)
        assert await asyncio.wait_for(rpc.request("test", {}), 2) == {"ok": True}
        release.set()
        await asyncio.wait_for(completed.wait(), 2)
        await rpc.close()


async def test_eof_rejects_pending():
    async def peer(reader, writer):
        await reader.readline()
        writer.close()
        await writer.wait_closed()

    async def handler(method, params):
        return {}

    async def notify(method, params):
        pass

    server = await asyncio.start_server(peer, "127.0.0.1", 0)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
        rpc = JsonRpcConnection(reader, writer, handler, notify)
        with pytest.raises(ACPProcessExited):
            await rpc.request("test", {}, timeout=2)
        assert not rpc.pending
        await rpc.close()
