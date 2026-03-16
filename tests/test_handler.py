"""Tests for WebSocketHandler."""

from mangum_ws.handler import WebSocketHandler, INTERNAL_WS_PATH_PREFIX


def _make_event(route_key="$connect", connection_id="abc123", body=None, headers=None):
    event = {
        "requestContext": {
            "routeKey": route_key,
            "connectionId": connection_id,
        },
        "headers": headers or {},
        "isBase64Encoded": False,
    }
    if body is not None:
        event["body"] = body
    return event


def _make_context():
    class Ctx:
        function_name = "test"
        memory_limit_in_mb = 128
        invoked_function_arn = "arn:aws:lambda:us-east-1:123:function:test"
        aws_request_id = "req-1"
    return Ctx()


def _config():
    return {"TEXT_MIME_TYPES": [], "api_gateway_base_path": ""}


class TestInfer:
    def test_connect_event(self):
        event = _make_event(headers={"Sec-WebSocket-Key": "x"})
        assert WebSocketHandler.infer(event, _make_context(), _config()) is True

    def test_message_event(self):
        event = _make_event(route_key="sendmessage")
        assert WebSocketHandler.infer(event, _make_context(), _config()) is True

    def test_http_event_rejected(self):
        event = {"httpMethod": "GET", "path": "/"}
        assert WebSocketHandler.infer(event, _make_context(), _config()) is False


class TestScope:
    def test_path_mapping(self):
        event = _make_event(route_key="$connect", connection_id="conn-1")
        h = WebSocketHandler(event, _make_context(), _config())
        assert h.scope["path"] == f"{INTERNAL_WS_PATH_PREFIX}/connect/conn-1"
        assert h.scope["method"] == "POST"
        assert h.scope["type"] == "http"

    def test_headers_lowercased(self):
        event = _make_event(headers={"X-Custom": "val"})
        h = WebSocketHandler(event, _make_context(), _config())
        header_keys = [pair[0] for pair in h.scope["headers"]]
        assert b"x-custom" in header_keys

    def test_body_json_dict(self):
        event = _make_event(body={"action": "sendmessage", "data": "hello"})
        h = WebSocketHandler(event, _make_context(), _config())
        body = h.body
        assert b"sendmessage" in body


class TestResponse:
    def test_call_formats_response(self):
        event = _make_event()
        h = WebSocketHandler(event, _make_context(), _config())
        resp = h({"status": 200, "headers": [], "body": b"ok"})
        assert resp["statusCode"] == 200
        assert "headers" in resp
