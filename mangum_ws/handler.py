"""Custom Mangum handler for AWS API Gateway WebSocket API.

Translates API Gateway WebSocket events ($connect, $disconnect, custom routes)
into HTTP POST requests so FastAPI can handle them with regular route handlers.

Route mapping:
    $connect    → POST /internal/websocket/connect/{connectionId}
    $disconnect → POST /internal/websocket/disconnect/{connectionId}
    sendmessage → POST /internal/websocket/sendmessage/{connectionId}
"""

from __future__ import annotations

import json

from mangum.handlers.utils import (
    handle_base64_response_body,
    handle_multi_value_headers,
    maybe_encode_body,
)
from mangum.types import LambdaConfig, LambdaContext, LambdaEvent, Response, Scope


INTERNAL_WS_PATH_PREFIX = "/internal/websocket"


class WebSocketHandler:
    """Mangum custom handler that converts API Gateway WebSocket events into
    ASGI HTTP scopes routed to ``/internal/websocket/{route_key}/{connection_id}``.
    """

    @classmethod
    def infer(cls, event: LambdaEvent, context: LambdaContext, config: LambdaConfig) -> bool:
        """Return *True* if *event* looks like an API Gateway WebSocket event."""
        if (
            "requestContext" in event
            and "routeKey" in event["requestContext"]
            and (
                "Sec-WebSocket-Key" in event.get("headers", {})
                or "connectionId" in event["requestContext"]
            )
        ):
            return True
        return False

    def __init__(self, event: LambdaEvent, context: LambdaContext, config: LambdaConfig) -> None:
        self.event = event
        self.context = context
        self.config = config

    # ── ASGI scope ──────────────────────────────────────────────

    @property
    def body(self) -> bytes:
        body = self.event.get("body", b"")
        if type(body) is dict:
            body = json.dumps(body)
        return maybe_encode_body(
            body,
            is_base64=self.event.get("isBase64Encoded", False),
        )

    @property
    def scope(self) -> Scope:
        request_context = self.event["requestContext"]
        route_key = request_context.get("routeKey", "").replace("$", "")
        connection_id = request_context.get("connectionId", "")

        formatted_headers: list[list[bytes]] = []
        for key, value in self.event.get("headers", {}).items():
            formatted_headers.append([key.lower().encode(), value.encode()])

        return {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "headers": formatted_headers,
            "path": f"{INTERNAL_WS_PATH_PREFIX}/{route_key}/{connection_id}",
            "raw_path": None,
            "root_path": "",
            "scheme": "https",
            "query_string": [],
            "server": None,
            "client": ("0.0.0.0", 0),
            "asgi": {"version": "3.0", "spec_version": "2.0"},
            "aws.event": self.event,
            "aws.context": None,
        }

    # ── Response serialisation ──────────────────────────────────

    def __call__(self, response: Response) -> dict:
        finalized_headers, multi_value_headers = handle_multi_value_headers(
            response["headers"]
        )
        finalized_body, is_base64_encoded = handle_base64_response_body(
            response["body"], finalized_headers, []
        )
        return {
            "statusCode": response["status"],
            "headers": finalized_headers,
            "multiValueHeaders": multi_value_headers,
            "body": finalized_body,
            "isBase64Encoded": is_base64_encoded,
        }
