"""FastAPI server for AGDD HTTP API."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
async def enforce_request_size(request: Request, call_next):
    """Reject requests that exceed the configured payload limit."""
    max_bytes = settings.API_MAX_REQUEST_BYTES
    header_value = request.headers.get("content-length")
    if header_value is not None:
        try:
            content_length = int(header_value)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header"},
            )
        if content_length > max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large"},
            )

    response = await call_next(request)
    return response

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
