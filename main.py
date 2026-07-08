from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import time
import base64


app = FastAPI()


# Allow browser grader access


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------
# Configuration
# ----------------------------

TOTAL_ORDERS = 47
RATE_LIMIT = 17
RATE_WINDOW = 10


# ----------------------------
# Storage
# ----------------------------

# Idempotency storage
idempotency_store = {}

# Fake order database
orders = {
    i: {
        "id": i,
        "name": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
}


# Rate limit storage
client_requests = {}


# ----------------------------
# Rate limiter middleware
# ----------------------------

@app.middleware("http")
async def rate_limit(request: Request, call_next):

    client_id = request.headers.get(
        "X-Client-Id",
        "anonymous"
    )

    now = time.time()

    if client_id not in client_requests:
        client_requests[client_id] = []

    # remove expired requests
    client_requests[client_id] = [
        t for t in client_requests[client_id]
        if now - t < RATE_WINDOW
    ]

    if len(client_requests[client_id]) >= RATE_LIMIT:
        response = HTTPException(
            status_code=429,
            detail="Rate limit exceeded"
        )

        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=429,
            content={
                "error": "Too many requests"
            },
            headers={
                "Retry-After": str(RATE_WINDOW)
            }
        )

    client_requests[client_id].append(now)

    return await call_next(request)


# ----------------------------
# Idempotent POST /orders
# ----------------------------

@app.post("/orders", status_code=201)
def create_order(
    Idempotency_Key: Optional[str] = Header(None)
):

    if not Idempotency_Key:
        raise HTTPException(
            status_code=400,
            detail="Missing Idempotency-Key"
        )


    # Existing request
    if Idempotency_Key in idempotency_store:
        return idempotency_store[Idempotency_Key]


    # Create new order
    new_id = len(idempotency_store) + 1000

    order = {
        "id": str(new_id),
        "status": "created"
    }


    idempotency_store[Idempotency_Key] = order

    return order



# ----------------------------
# Cursor pagination
# ----------------------------

@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):

    if limit <= 0:
        limit = 10


    # Decode cursor
    if cursor:
        try:
            start = int(
                base64.b64decode(cursor).decode()
            )
        except:
            start = 1
    else:
        start = 1


    end = min(
        start + limit - 1,
        TOTAL_ORDERS
    )


    items = [
        orders[i]
        for i in range(start, end + 1)
    ]


    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(
            str(end + 1).encode()
        ).decode()
    else:
        next_cursor = None


    return {
        "items": items,
        "next_cursor": next_cursor
    }