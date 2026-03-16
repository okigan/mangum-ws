"""Tests for the MangumWS facade."""

import pytest
from unittest.mock import AsyncMock

from mangum_ws import MangumWS
from mangum_ws.handler import WebSocketHandler
from mangum_ws.gateway import LocalGateway


def test_local_by_default():
    ws = MangumWS()
    assert ws.is_local is True


def test_handler_is_websocket_handler():
    ws = MangumWS()
    assert ws.handler is WebSocketHandler


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


def test_mount_noop_when_not_local():
    """mount() should not raise on non-local gateways."""
    pytest.importorskip("boto3")
    from fastapi import FastAPI
    app = FastAPI()
    ws = MangumWS(endpoint_url="https://example.com")
    # Should not raise
    ws.mount(app, path="/ws")
