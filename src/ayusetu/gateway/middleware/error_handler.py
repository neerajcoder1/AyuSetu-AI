"""
Centralized Error Handler
=========================
Formats all exceptions to the PRD v2.0 §22.8 error taxonomy.
Ensures zero stack trace, DB schema, or PII leakage to clients.
"""

import logging
from typing import Any, Dict
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_503_SERVICE_UNAVAILABLE,
)
try:
    from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT as HTTP_STATUS_422
except ImportError:
    from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY as HTTP_STATUS_422


from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError

logger = logging.getLogger("ayusetu.gateway.error")


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    details: Any = None,
    headers: Dict[str, str] = None,
) -> JSONResponse:
    content = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "details": details,
        }
    }
    resp_headers = headers or {}
    if request_id:
        resp_headers["X-Request-ID"] = request_id
    return JSONResponse(status_code=status_code, content=content, headers=resp_headers)


async def ayusetu_gateway_error_handler(request: Request, exc: AyuSetuGatewayError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", "")
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code.value,
        message=exc.message,
        request_id=req_id,
        details=exc.details,
        headers=exc.headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    req_id = getattr(request.state, "request_id", "")
    
    status_code = exc.status_code
    if status_code == HTTP_400_BAD_REQUEST:
        code = ErrorCode.BAD_REQUEST.value
    elif status_code == HTTP_401_UNAUTHORIZED:
        code = ErrorCode.SESSION_EXPIRED.value
    elif status_code == HTTP_403_FORBIDDEN:
        code = ErrorCode.POLICY_DENIED.value
    elif status_code == HTTP_404_NOT_FOUND:
        code = ErrorCode.NOT_FOUND.value
    elif status_code == HTTP_STATUS_422:
        code = ErrorCode.UNPROCESSABLE_ENTITY.value
    elif status_code == HTTP_503_SERVICE_UNAVAILABLE:
        code = ErrorCode.SERVICE_UNAVAILABLE.value
    else:
        code = ErrorCode.INTERNAL_ERROR.value

    return build_error_response(
        status_code=status_code,
        code=code,
        message=str(exc.detail),
        request_id=req_id,
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", "")
    sanitized_errors = []
    for err in exc.errors():
        loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "header")]
        sanitized_errors.append({
            "field": ".".join(loc) if loc else "root",
            "message": err.get("msg", "Invalid value"),
            "type": err.get("type", "validation_error")
        })

    return build_error_response(
        status_code=HTTP_STATUS_422,
        code=ErrorCode.UNPROCESSABLE_ENTITY.value,
        message="Request validation failed. Please check payload schema.",
        request_id=req_id,
        details=sanitized_errors,
    )



async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    req_id = getattr(request.state, "request_id", "")
    logger.error("Unhandled Exception [req_id=%s]: %s", req_id, str(exc), exc_info=True)
    return build_error_response(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_ERROR.value,
        message="An unexpected internal server error occurred. Please try again later.",
        request_id=req_id,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all centralized error handlers on the FastAPI application."""
    app.add_exception_handler(AyuSetuGatewayError, ayusetu_gateway_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
