"""Tests for Gateway classes."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from mangum_ws.gateway import LocalGateway, Gateway


@pytest.mark.asyncio
async def test_local_gateway_send_to_connection():
    gw = LocalGateway()
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    cid = gw.register("conn-1", ws)

    ok = await gw.send_to_connection(cid, '{"msg": "hi"}')
    assert ok is True
    ws.send_text.assert_awaited_once_with('{"msg": "hi"}')


@pytest.mark.asyncio
async def test_local_gateway_gone_connection():
    gw = LocalGateway()
    ok = await gw.send_to_connection("nonexistent", "data")
    assert ok is False


@pytest.mark.asyncio
async def test_local_gateway_send_batch():
    gw = LocalGateway()
    ws1 = AsyncMock()
    ws1.send_text = AsyncMock()
    ws2 = AsyncMock()
    ws2.send_text = AsyncMock()

    gw.register("conn-1", ws1)
    gw.register("conn-2", ws2)

    gone = await gw.send({"conn-1", "conn-2", "conn-gone"}, {"type": "test"})
    assert "conn-gone" in gone
    assert "conn-1" not in gone
    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_gateway_unregister():
    gw = LocalGateway()
    ws = AsyncMock()
    gw.register("conn-1", ws)
    gw.unregister_ws(ws)
    assert "conn-1" not in gw._connections


@pytest.mark.asyncio
async def test_local_gateway_stale_ws_removed():
    gw = LocalGateway()
    ws = AsyncMock()
    ws.send_text = AsyncMock(side_effect=Exception("closed"))
    gw.register("conn-1", ws)

    ok = await gw.send_to_connection("conn-1", "data")
    assert ok is False
    assert "conn-1" not in gw._connections


def test_auto_returns_local_when_no_url():
    gw = Gateway.auto(endpoint_url=None)
    assert isinstance(gw, LocalGateway)
    assert gw.is_local is True


def test_register_generates_id():
    gw = LocalGateway()
    ws = MagicMock()
    cid = gw.register("", ws)
    assert cid.startswith("local_")


# ── LocalGateway.mount() lifecycle tests ─────────────────────


def test_mount_local_ws_lifecycle_callbacks():
    """on_connect, on_message, on_disconnect are called in order."""
    log: list[str] = []

    async def on_connect(cid: str) -> None:
        log.append(f"connect:{cid}")

    async def on_disconnect(cid: str) -> None:
        log.append(f"disconnect:{cid}")

    async def on_message(cid: str, data: dict) -> None:
        log.append(f"message:{cid}:{data}")

    app = FastAPI()
    gw = LocalGateway()
    gw.mount(app, path="/ws", on_connect=on_connect, on_disconnect=on_disconnect, on_message=on_message)

    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"event_id": "e1"}))

    # Verify lifecycle order
    assert len(log) == 3
    assert log[0].startswith("connect:local_")
    assert "event_id" in log[1]
    assert log[2].startswith("disconnect:local_")

    # All three callbacks received the same connection_id
    cid = log[0].split(":", 1)[1]
    assert log[2] == f"disconnect:{cid}"


def test_mount_local_ws_connection_id_stable():
    """Connection ID is assigned once and reused for all messages."""
    cids: list[str] = []

    async def on_message(cid: str, data: dict) -> None:
        cids.append(cid)

    app = FastAPI()
    gw = LocalGateway()
    gw.mount(app, path="/ws", on_message=on_message)

    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"a": 1}))
        ws.send_text(json.dumps({"a": 2}))
        ws.send_text(json.dumps({"a": 3}))

    assert len(cids) == 3
    assert cids[0] == cids[1] == cids[2]


def test_mount_local_ws_server_push():
    """Server can push messages to the client via the gateway."""
    received: list[str] = []

    async def on_message(cid: str, data: dict) -> None:
        # Echo back via gateway
        await gw.send_to_connection(cid, json.dumps({"echo": data}))

    app = FastAPI()
    gw = LocalGateway()
    gw.mount(app, path="/ws", on_message=on_message)

    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"hello": "world"}))
        resp = ws.receive_text()
        received.append(resp)

    assert len(received) == 1
    assert json.loads(received[0]) == {"echo": {"hello": "world"}}


def test_mount_local_ws_no_callbacks():
    """mount() works fine with no callbacks at all."""
    app = FastAPI()
    gw = LocalGateway()
    gw.mount(app, path="/ws")

    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"ping": True}))
    # No error means success


def test_mount_local_ws_invalid_json_skipped():
    """Non-JSON messages are silently skipped, not passed to on_message."""
    messages: list[dict] = []

    async def on_message(cid: str, data: dict) -> None:
        messages.append(data)

    app = FastAPI()
    gw = LocalGateway()
    gw.mount(app, path="/ws", on_message=on_message)

    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        ws.send_text("not json!!!")
        ws.send_text(json.dumps({"valid": True}))

    assert len(messages) == 1
    assert messages[0] == {"valid": True}
