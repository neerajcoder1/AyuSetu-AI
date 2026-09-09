"""
Request ID and Correlation Middleware
======================================
Assigns or propagates a validated unique correlation ID for every request.
Also guards against unhandled pipeline crashes, returning a safe PRD error envelope.
"""

import logging
import re
import uuid6
from contextvars import ContextVar
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ayusetu.gateway.errors import ErrorCode

logger = logging.getLogger("ayusetu.gateway.request_id")

# Context variable for structured logging across async tasks
request_id_ctx: ContextVar[str] = ContextVar("request_id_ctx", default="")

REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")


def get_current_request_id() -> str:
    """Retrieve current request ID from context."""
    return request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Ensures every request has a validated correlation ID.
    Propagates safe client-supplied IDs or generates a time-ordered UUID v7.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        client_req_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")

        # Validate incoming ID: alphanumeric, dashes, underscores, 8-64 chars
        if client_req_id and REQUEST_ID_REGEX.match(client_req_id):
            req_id = client_req_id
        else:
            req_id = str(uuid6.uuid7())

        # Set in context and request state
        token = request_id_ctx.set(req_id)
        request.state.request_id = req_id

        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        except Exception as exc:
            logger.error("Unhandled Exception caught at Gateway boundary [req_id=%s]: %s", req_id, str(exc), exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": ErrorCode.INTERNAL_ERROR.value,
                        "message": "An unexpected internal server error occurred. Please try again later.",
                        "request_id": req_id,
                        "details": None
                    }
                },
                headers={"X-Request-ID": req_id}
            )
        finally:
            request_id_ctx.reset(token)
