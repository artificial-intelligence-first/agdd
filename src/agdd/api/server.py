"""FastAPI server for AGDD HTTP API."""
from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException as FastAPIHTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings, get_settings
from .routes import agents, github, runs

# Get settings
settings: Settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="AGDD API",
    description="HTTP API for AG-Driven Development agent orchestration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    debug=settings.API_DEBUG,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_request_size(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Reject requests that exceed the configured payload limit."""
    max_bytes = settings.API_MAX_REQUEST_BYTES
    header_value = request.headers.get("content-length")
    if header_value is not None:
        try:
            content_length = int(header_value)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"code": "invalid_payload", "message": "Invalid Content-Length header"},
            )
        if content_length > max_bytes:
            return JSONResponse(
                status_code=413,
                content={"code": "invalid_payload", "message": "Request body too large"},
            )

    response = await call_next(request)
    return response


@app.exception_handler(FastAPIHTTPException)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: FastAPIHTTPException | StarletteHTTPException
) -> JSONResponse:
    """
    Convert HTTPException to ApiError schema format.

    This ensures all errors follow the documented format:
    {"code": "...", "message": "...", "details": {...}}
    instead of FastAPI's default {"detail": ...}
    """
    # If detail is already a dict with code/message, use it directly (ApiError format)
    if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=getattr(exc, "headers", None),
        )

    # Otherwise convert string detail to ApiError format
    # Map status codes to error codes
    code_map = {
        400: "invalid_payload",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        413: "invalid_payload",
        429: "rate_limit_exceeded",
        500: "internal_error",
    }

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code_map.get(exc.status_code, "internal_error"),
            "message": str(exc.detail),
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Convert Pydantic validation errors to ApiError schema format.

    FastAPI's default validation error response is 422 with {"detail": [...]}.
    This handler converts to 400 with {"code": "invalid_payload", "message": "...", "details": {...}}
    to match the documented ApiError schema.
    """
    # Extract first error for message (most relevant)
    errors = exc.errors()
    first_error = errors[0] if errors else {}

    # Build human-readable message from first error
    field = " -> ".join(str(loc) for loc in first_error.get("loc", []))
    error_msg = first_error.get("msg", "Validation error")

    message = f"Validation error: {field}: {error_msg}" if field else error_msg

    return JSONResponse(
        status_code=400,  # Use 400 instead of 422 for consistency
        content={
            "code": "invalid_payload",
            "message": message,
            "details": {"validation_errors": errors},
        },
    )


# Include routers
app.include_router(agents.router, prefix=settings.API_PREFIX)
app.include_router(runs.router, prefix=settings.API_PREFIX)
app.include_router(github.router, prefix=settings.API_PREFIX)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# Main entry point for running with `python -m agdd.api.server`
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agdd.api.server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_DEBUG,
    )
