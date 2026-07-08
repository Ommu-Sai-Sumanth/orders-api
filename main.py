from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import time
import base64


app = FastAPI()


# -------------------------
# CORS
# -------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)


# -------------------------
# Configuration
# -------------------------

TOTAL_ORDERS = 47
RATE_LIMIT = 17
RATE_WINDOW = 10


# -------------------------
# Storage
# -------------------------

# Stores idempotency key -> created order
idempotency_store = {}

# Fixed order catalog 1..47
orders = {
    i: {
        "id": i,
        "name": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
}

# Client ID -> request timestamps
rate_limit_store = {}


# -------------------------
# Rate limiting middleware
# -------------------------

@app.middleware("http")
async def rate_limiter(request: Request, call_next):

    client_id = request.headers.get(
        "X-Client-Id",
        "anonymous"
    )

    now = time.time()

    if client_id not in rate_limit_store:
        rate_limit_store[client_id] = []

    # Remove requests outside 10 second window
    rate_limit_store[client_id] = [
        timestamp
        for timestamp in rate_limit_store[client_id]
        if now - timestamp < RATE_WINDOW
    ]

    # Check limit
    if len(rate_limit_store[client_id]) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded"
            },
            headers={
                "Retry-After": str(RATE_WINDOW)
            }
        )

    rate_limit_store[client_id].append(now)

    return await call_next(request)


# -------------------------
# Idempotent order creation
# -------------------------

@app.post("/orders", status_code=201)
def create_order(
    Idempotency_Key: Optional[str] = Header(None)
):

    if not Idempotency_Key:
        raise HTTPException(
            status_code=400,
            detail="Missing Idempotency-Key"
        )


    # Return existing order for same key
    if Idempotency_Key in idempotency_store:
        return idempotency_store[Idempotency_Key]


    # Create new order
    order_id = str(
        1000 + len(idempotency_store)
    )

    order = {
        "id": order_id,
        "status": "created"
    }

    idempotency_store[Idempotency_Key] = order

    return order


# -------------------------
# Cursor pagination
# -------------------------

@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):

    if limit < 1:
        limit = 10


    # Decode cursor
    if cursor:
        try:
            start_id = int(
                base64.b64decode(cursor).decode()
            )
        except Exception:
            start_id = 1
    else:
        start_id = 1


    # Prevent invalid start
    if start_id > TOTAL_ORDERS:
        return {
            "items": [],
            "next_cursor": None
        }


    end_id = min(
        start_id + limit - 1,
        TOTAL_ORDERS
    )


    items = [
        orders[i]
        for i in range(start_id, end_id + 1)
    ]


    if end_id < TOTAL_ORDERS:
        next_cursor = base64.b64encode(
            str(end_id + 1).encode()
        ).decode()
    else:
        next_cursor = None


    return {
        "items": items,
        "next_cursor": next_cursor
    }