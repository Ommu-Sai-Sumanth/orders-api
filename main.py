from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import time
import base64


app = FastAPI()


# -----------------------------
# CORS
# -----------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)


# -----------------------------
# Configuration
# -----------------------------

TOTAL_ORDERS = 47
RATE_LIMIT = 17
RATE_WINDOW = 10


# -----------------------------
# Storage
# -----------------------------

# Idempotency-Key -> order response
idempotency_store = {}

# Fixed catalog 1..47
orders = [
    {
        "id": i,
        "name": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


# X-Client-Id -> timestamps
client_requests = {}


# -----------------------------
# Rate limiting middleware
# -----------------------------

@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client_id = request.headers.get(
        "X-Client-Id",
        "anonymous"
    )

    now = time.time()

    if client_id not in client_requests:
        client_requests[client_id] = []


    # Keep only requests inside last 10 seconds
    client_requests[client_id] = [
        t for t in client_requests[client_id]
        if now - t < RATE_WINDOW
    ]


    if len(client_requests[client_id]) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded"
            },
            headers={
                "Retry-After": str(RATE_WINDOW)
            }
        )


    client_requests[client_id].append(now)

    return await call_next(request)



# -----------------------------
# POST /orders
# Idempotent creation
# -----------------------------

@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: Optional[str] = Header(
        None,
        alias="Idempotency-Key"
    )
):

    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Missing Idempotency-Key"
            }
        )


    # Return previous result
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]


    # Create new order
    new_order = {
        "id": str(len(idempotency_store) + 1),
        "status": "created"
    }


    idempotency_store[idempotency_key] = new_order

    return new_order



# -----------------------------
# GET /orders
# Cursor pagination
# -----------------------------

@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):

    if limit < 1:
        limit = 10


    start_index = 0


    # Decode cursor
    if cursor:
        try:
            start_index = int(
                base64.b64decode(cursor).decode()
            )
        except Exception:
            start_index = 0


    end_index = min(
        start_index + limit,
        TOTAL_ORDERS
    )


    items = orders[start_index:end_index]


    next_cursor = None

    if end_index < TOTAL_ORDERS:
        next_cursor = base64.b64encode(
            str(end_index).encode()
        ).decode()


    return {
        "items": items,
        "next_cursor": next_cursor
    }