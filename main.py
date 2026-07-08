from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import base64
import time


app = FastAPI()


# -----------------------
# CORS
# -----------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)


# -----------------------
# Config
# -----------------------

TOTAL_ORDERS = 47
RATE_LIMIT = 17
WINDOW = 10


# -----------------------
# Storage
# -----------------------

orders = [
    {
        "id": i,
        "name": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


idempotency = {}

buckets = {}



# -----------------------
# Rate limiting
# -----------------------

@app.middleware("http")
async def rate_limit(request: Request, call_next):

    if request.method == "OPTIONS":
        return await call_next(request)


    client = request.headers.get("X-Client-Id")


    if client:

        now = time.time()

        if client not in buckets:
            buckets[client] = []


        buckets[client] = [
            t for t in buckets[client]
            if now - t < WINDOW
        ]


        if len(buckets[client]) >= RATE_LIMIT:

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded"
                },
                headers={
                    "Retry-After": "10"
                }
            )


        buckets[client].append(now)


    return await call_next(request)



# -----------------------
# POST /orders
# -----------------------

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


    if idempotency_key in idempotency:
        return idempotency[idempotency_key]


    order = {
        "id": str(len(idempotency) + 1),
        "status": "created"
    }


    idempotency[idempotency_key] = order


    return order



# -----------------------
# GET /orders
# -----------------------

@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None
):

    if limit < 1:
        limit = 1


    start = 0


    if cursor:
        try:
            start = int(
                base64.b64decode(cursor).decode()
            )
        except Exception:
            start = 0



    end = min(
        start + limit,
        TOTAL_ORDERS
    )


    items = orders[start:end]


    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(
            str(end).encode()
        ).decode()



    return {
        "items": items,
        "next_cursor": next_cursor
    }