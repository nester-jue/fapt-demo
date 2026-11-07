import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import engine
from routes.auth import router as auth_router
from routes.admin_users import router as admin_users_router
from routes.assets import router as assets_router
from routes.admin_assets import router as admin_assets_router
from routes.token_issuances import router as token_issuances_router
from routes.transfers import router as transfers_router
from routes.portfolio import router as portfolio_router
from routes.workflows import router as workflows_router
from routes.marketplace import router as marketplace_router
from routes.property_management import router as property_management_router
from routes.notifications import router as notifications_router
from routes.integrity import router as integrity_router


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("nexa.api")

app = FastAPI(
    title="NEXA Tokenisation Platform",
    description="Asset Tokenisation Demonstration API",
    version="1.0.0"
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173"
    ).split(",")
    if origin.strip()
]
if not cors_origins or "*" in cors_origins:
    raise RuntimeError(
        "Configure at least one explicit CORS origin; '*' is not permitted."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(assets_router)
app.include_router(admin_assets_router)
app.include_router(token_issuances_router)
app.include_router(transfers_router)
app.include_router(portfolio_router)
app.include_router(workflows_router)
app.include_router(marketplace_router)
app.include_router(property_management_router)
app.include_router(notifications_router)
app.include_router(integrity_router)

MAX_REQUEST_BODY_BYTES = 11 * 1024 * 1024


@app.middleware("http")
async def limit_declared_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            request_size = int(content_length)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header."},
            )
        if request_size < 0 or request_size > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body exceeds the allowed size."},
            )

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/")
def home():
    return {
        "system": "NEXA Tokenisation Platform",
        "status": "running",
        "message": "Welcome to NEXA Tokenisation Demo"
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database health check failed.")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "service": "NEXA Backend"},
        )
    return {
        "status": "healthy",
        "service": "NEXA Backend"
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    _request: Request,
    _error: Exception,
):
    logger.exception("Unhandled API error.")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred."},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _request: Request,
    error: RequestValidationError,
):
    errors = [
        {
            "loc": item.get("loc", ()),
            "msg": item.get("msg", "Invalid value."),
            "type": item.get("type", "value_error"),
        }
        for item in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})