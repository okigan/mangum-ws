# mangum-ws

WebSocket support for [Mangum](https://github.com/jordanerber/mangum) -- run FastAPI behind AWS API Gateway WebSocket API on Lambda.

## Problem

Mangum doesn't natively support API Gateway WebSocket API events (`$connect`, `$disconnect`, custom routes). This library bridges that gap with a single `MangumWS` object that handles both directions:

- **Inbound**: converts API Gateway WebSocket events into HTTP POST requests to your FastAPI routes (via a Mangum custom handler)
- **Outbound**: sends messages back to connected clients (via boto3 in production, or in-memory for local dev)

## Install

```bash
pip install mangum-ws
# With AWS support (boto3):
pip install mangum-ws[aws]
```

## Quick Start

```python
import json
import os
from fastapi import FastAPI, Request
from mangum import Mangum
from mangum_ws import MangumWS

app = FastAPI()

# One object, auto-selects AWS or local based on endpoint URL
ws = MangumWS(endpoint_url=os.getenv("APIGW_MANAGEMENT_URL"))

# Mount local dev WebSocket endpoint (no-op in production)
async def on_ws_connect(connection_id: str):
    print(f"Connected: {connection_id}")

async def on_ws_disconnect(connection_id: str):
    print(f"Disconnected: {connection_id}")

async def on_ws_message(connection_id: str, data: dict):
    # Your subscribe logic here
    pass

ws.mount(app, path="/",
    on_connect=on_ws_connect,
    on_disconnect=on_ws_disconnect,
    on_message=on_ws_message,
)

# --- Internal routes (hit via Mangum in prod, or local WS in dev) ---

@app.post("/internal/websocket/connect/{connection_id}")
async def ws_connect(connection_id: str):
    pass  # Connection opened

@app.post("/internal/websocket/disconnect/{connection_id}")
async def ws_disconnect(connection_id: str):
    pass  # Connection closed -- clean up subscriptions

@app.post("/internal/websocket/sendmessage/{connection_id}")
async def ws_message(connection_id: str, request: Request):
    body = json.loads(await request.body())
    # Subscribe this connection to a topic, etc.

# --- Sending messages back to clients ---

async def notify(connection_ids: set[str], payload: dict):
    gone = await ws.send(connection_ids=connection_ids, data=payload)
    # Remove gone connection IDs from your subscription store
    return gone

# Lambda handler -- ws.handler is the Mangum custom handler class
handler = Mangum(app, custom_handlers=[ws.handler])
```

## How It Works

### Route Mapping

API Gateway WebSocket routes are mapped to internal HTTP POST routes:

| API Gateway Route | FastAPI Route |
|---|---|
| `$connect` | `POST /internal/websocket/connect/{connectionId}` |
| `$disconnect` | `POST /internal/websocket/disconnect/{connectionId}` |
| `sendmessage` | `POST /internal/websocket/sendmessage/{connectionId}` |

### Gateway

`MangumWS` auto-selects the right gateway backend:

- **`AwsGateway`** -- wraps `boto3.client("apigatewaymanagementapi")` to push messages via `post_to_connection`
- **`LocalGateway`** -- holds in-memory WebSocket references; mounts a real `@app.websocket()` endpoint for local testing

Both return gone connection IDs from `send()` so you can clean up your subscription store.

## API

### `MangumWS(endpoint_url=None)`

Main entry point. Returns an `AwsGateway`-backed instance if `endpoint_url` is provided, `LocalGateway`-backed otherwise.

### `ws.handler`

The Mangum custom handler class. Pass to `Mangum(app, custom_handlers=[ws.handler])`.

### `ws.send(connection_ids, data) -> set[str]`

Send `data` (dict or string) to all `connection_ids`. Returns the set of gone (disconnected) connection IDs.

### `ws.send_to_connection(connection_id, data) -> bool`

Send to a single connection. Returns `False` if the connection is gone.

### `ws.mount(app, path="/", *, on_connect=None, on_disconnect=None, on_message=None)`

Mount a WebSocket endpoint on the FastAPI app for local development. No-op in production (so you can call it unconditionally).

The three callbacks mirror the API Gateway WebSocket lifecycle and the corresponding `/internal/websocket/*` routes:

- **`on_connect(connection_id)`** -- called once when a client connects (matches `$connect`)
- **`on_disconnect(connection_id)`** -- called when a client disconnects (matches `$disconnect`)
- **`on_message(connection_id, json_data)`** -- called for each JSON message (matches custom routes like `sendmessage`)

All callbacks are optional `async` functions.

### `ws.is_local`

`True` when backed by `LocalGateway` (local dev), `False` when backed by `AwsGateway`.

## License

MIT
