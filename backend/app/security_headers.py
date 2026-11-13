"""Security headers on every response, and a Content Security Policy for the built frontend.

The CSP only allows what the app needs: its own scripts, the OpenStreetMap tile server and
the AWS elevation tiles for the map, and blob: workers (MapLibre). Swagger UI (/docs) loads
from a CDN, so the CSP is not applied to the API docs.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

TILE_HOSTS = "https://tile.openstreetmap.org https://s3.amazonaws.com"

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",  # React style attributes
        f"img-src 'self' data: blob: {TILE_HOSTS}",
        f"connect-src 'self' {TILE_HOSTS}",
        "worker-src 'self' blob:",
        "child-src blob:",
        "font-src 'self' data:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeaders(BaseHTTPMiddleware):
    def __init__(self, app: object, csp: bool = False) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.csp = csp

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in BASE_HEADERS.items():
            response.headers.setdefault(name, value)
        path = request.url.path
        if self.csp and not (path.startswith(("/docs", "/redoc")) or path == "/openapi.json"):
            response.headers.setdefault("Content-Security-Policy", CSP)
        if path.startswith("/api/") and request.method == "GET":
            # API data can change at any time and some of it is private: never cache it.
            response.headers.setdefault("Cache-Control", "no-store")
        return response
