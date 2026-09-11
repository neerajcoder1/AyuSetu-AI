"""
Zero-PHI Access Logging & Observability Middleware
===================================================
Captures request lifecycle metrics, response status codes, and latency.
Emits structured JSON access logs with zero request body or credential leakage.
"""

import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ayusetu.common.metrics import metrics_registry, normalize_route_path
from ayusetu.gateway.middleware.request_id import get_current_request_id

logger = logging.getLogger("ayusetu.gateway.access")


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    Middleware recording HTTP telemetry and structured access logs.
    Guarantees that raw request bodies, Authorization headers, and session tokens are never logged.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        req_id = getattr(request.state, "request_id", "") or get_current_request_id() or "-"
        path = request.url.path
        method = request.method

        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = time.perf_counter() - start_time
            latency_ms = duration_seconds * 1000.0
            norm_path = normalize_route_path(path)

            # Record telemetry in metrics registry
            metrics_registry.record_http_request(
                method=method,
                path=path,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )

            # Emit structured access log (excluding sensitive bodies and headers)
            client_host = request.client.host if request.client else "unknown"
            extra_info = {
                "http_method": method,
                "route": norm_path,
                "status_code": status_code,
                "latency_ms": round(latency_ms, 2),
                "client_host": client_host,
                "request_id": req_id,
            }

            logger.info(
                "HTTP %s %s -> %d (%.2fms)",
                method,
                norm_path,
                status_code,
                latency_ms,
                extra={"extra_data": extra_info, "request_id": req_id},
            )
