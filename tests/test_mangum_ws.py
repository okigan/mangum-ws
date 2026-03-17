"""Tests for the MangumWS facade."""

import json

import pytest
from unittest.mock import AsyncMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from mangum_ws import MangumWS
from mangum_ws.handler import WebSocketHandler, INTERNAL_WS_PATH_PREFIX


def test_local_by_default():
    ws = MangumWS()
    assert ws.is_local is True


def test_handler_is_websocket_handler():
    ws = MangumWS()
    assert ws.handler is WebSocketHandler


# ── decorator registration ──────────────────────────────────


def test_decorators_register_handlers():
    ws = MangumWS()

    @ws.on_connect
    async def handle_connect(cid: str): pass

    @ws.on_disconnect
    async def handle_disconnect(cid: str): pass

    @ws.on_message
    async def handle_message(cid: str, data: dict): pass

    assert ws._on_connect_fn is handle_connect
    assert ws._on_disconnect_fn is handle_disconnect
    assert ws._on_message_fn is handle_message


def test_decorators_return_original_function():
    ws = MangumWS()

    async def my_handler(cid: str): pass

    result = ws.on_connect(my_handler)
    assert result is my_handler


# ── router ──────────────────────────────────────────────────


def test_router_contains_internal_routes():
    ws = MangumWS()

    @ws.on_connect
    async def h(cid: str): pass

    router = ws.router
    paths = [route.path for route in router.routes]
    assert f"{INTERNAL_WS_PATH_PREFIX}/connect/{{connection_id}}" in paths
    assert f"{INTERNAL_WS_PATH_PREFIX}/disconnect/{{connection_id}}" in paths
    assert f"{INTERNAL_WS_PATH_PREFIX}/sendmessage/{{connection_id}}" in paths


def test_router_connect_calls_handler():
    log: list[str] = []
    ws = MangumWS()

    @ws.on_connect
    async def handle_connect(cid: str):
        log.append(f"connect:{cid}")

    app = FastAPI()
    app.include_router(ws.router)
    client = TestClient(app)

    resp = client.post(f"{INTERNAL_WS_PATH_PREFIX}/connect/conn-42")
    assert resp.status_code == 200
    assert log == ["connect:conn-42"]


def test_router_disconnect_calls_handler():
    log: list[str] = []
    ws = MangumWS()

    @ws.on_disconnect
    async def handle_disconnect(cid: str):
        log.append(f"disconnect:{cid}")

    app = FastAPI()
    app.include_router(ws.router)
    client = TestClient(app)

    resp = client.post(f"{INTERNAL_WS_PATH_PREFIX}/disconnect/conn-42")
    assert resp.status_code == 200
    assert log == ["disconnect:conn-42"]


def test_router_sendmessage_calls_handler():
    log: list[str] = []
    ws = MangumWS()

    @ws.on_message
    async def handle_message(cid: str, data: dict):
        log.append(f"message:{cid}:{data}")

    app = FastAPI()
    app.include_router(ws.router)
    client = TestClient(app)

    resp = client.post(
        f"{INTERNAL_WS_PATH_PREFIX}/sendmessage/conn-42",
        content=json.dumps({"event_id": "e1"}),
    )
    assert resp.status_code == 200
    assert log == ["message:conn-42:{'event_id': 'e1'}"]


def test_router_works_without_handlers():
    """Router should return 200 even with no handlers registered."""
    ws = MangumWS()
    app = FastAPI()
    app.include_router(ws.router)
    client = TestClient(app)

    assert client.post(f"{INTERNAL_WS_PATH_PREFIX}/connect/c1").status_code == 200
    assert client.post(f"{INTERNAL_WS_PATH_PREFIX}/disconnect/c1").status_code == 200
    assert client.post(
        f"{INTERNAL_WS_PATH_PREFIX}/sendmessage/c1",
        content=json.dumps({}),
    ).status_code == 200


# ── mount + decorators integration ──────────────────────────


def test_mount_uses_registered_handlers():
    """mount() should use the decorator-registered handlers for local WS."""
    log: list[str] = []
    ws = MangumWS()

    @ws.on_connect
    async def handle_connect(cid: str):
        log.append(f"connect:{cid}")

    @ws.on_disconnect
    async def handle_disconnect(cid: str):
        log.append(f"disconnect:{cid}")

    @ws.on_message
    async def handle_message(cid: str, data: dict):
        log.append(f"message:{cid}")

    app = FastAPI()
    ws.mount(app, path="/ws")

    client = TestClient(app)
    with client.websocket_connect("/ws") as sock:
        sock.send_text(json.dumps({"event_id": "e1"}))

    assert len(log) == 3
    assert log[0].startswith("connect:")
    assert log[1].startswith("message:")
    assert log[2].startswith("disconnect:")


# ── send ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_delegates_to_gateway():
    ws = MangumWS()
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock()
    ws._gateway.register("conn-1", mock_ws)

    gone = await ws.send({"conn-1", "conn-gone"}, {"type": "test"})
    assert "conn-gone" in gone
    assert "conn-1" not in gone
    mock_ws.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_to_connection_delegates():
    ws = MangumWS()
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock()
    ws._gateway.register("conn-1", mock_ws)

    ok = await ws.send_to_connection("conn-1", '{"msg": "hi"}')
    assert ok is True


# ── mount noop on AwsGateway ────────────────────────────────


def test_mount_noop_when_not_local():
    """mount() should not raise on non-local gateways."""
    pytest.importorskip("boto3")
    app = FastAPI()
    ws = MangumWS(endpoint_url="https://example.com")
    ws.mount(app, path="/ws")  # no-op, should not raise
