"""
Request Body Size Limit Middleware
===================================
Enforces request size boundaries per PRD v2.0 §21.6 (25 MB uploads, 256 KB otherwise).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
try:
    from starlette.status import HTTP_413_CONTENT_TOO_LARGE as HTTP_STATUS_413
except ImportError:
    from starlette.status import HTTP_413_REQUEST_ENTITY_TOO_LARGE as HTTP_STATUS_413

from ayusetu.common.config import settings
from ayusetu.gateway.errors import ErrorCode


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Guards the gateway against resource exhaustion via oversized payloads.
    """

    def _is_upload_path(self, path: str) -> bool:
        """Check if request targets a document or audio upload endpoint."""
        upload_markers = ["/documents", "/upload", "/turn", "/audio"]
        return any(marker in path.lower() for marker in upload_markers)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Check Content-Length header if present
        content_length = request.headers.get("content-length")
        is_upload = self._is_upload_path(request.url.path)
        max_bytes = settings.MAX_UPLOAD_BODY_BYTES if is_upload else settings.MAX_JSON_BODY_BYTES

        if content_length is not None:
            try:
                length = int(content_length)
                if length > max_bytes:
                    req_id = getattr(request.state, "request_id", "")
                    return JSONResponse(
                        status_code=HTTP_STATUS_413,
                        content={
                            "error": {
                                "code": ErrorCode.PAYLOAD_TOO_LARGE.value,
                                "message": f"Request body exceeds maximum allowed size ({max_bytes} bytes)",
                                "request_id": req_id,
                                "details": {"max_bytes": max_bytes, "received_bytes": length},
                            }
                        },
                        headers={"X-Request-ID": req_id} if req_id else None
                    )

            except ValueError:
                pass

        return await call_next(request)
