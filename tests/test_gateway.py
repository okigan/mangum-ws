"""Tests for Gateway classes."""

import pytest
from unittest.mock import AsyncMock, MagicMock

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
