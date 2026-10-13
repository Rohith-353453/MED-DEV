from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp


def wrap_with_cors(app: ASGIApp, allowed_origins: list[str]) -> CORSMiddleware:
    """Wrap the entire ASGI app so CORS headers also cover unhandled errors."""
    return CORSMiddleware(
        app=app,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
