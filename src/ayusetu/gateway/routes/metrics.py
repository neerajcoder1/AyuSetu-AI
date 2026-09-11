"""
Prometheus Metrics REST Endpoint
================================
Exposes operational metrics in Prometheus text exposition format (version 0.0.4)
and JSON format for health monitoring systems.
"""

from fastapi import APIRouter, Response, status

from ayusetu.common.metrics import metrics_registry

router = APIRouter(tags=["Metrics"])


@router.get(
    "/metrics",
    response_class=Response,
    status_code=status.HTTP_200_OK,
    summary="Prometheus Metrics Exposition",
)
def get_prometheus_metrics() -> Response:
    """
    Returns Prometheus-compatible metrics for operational observability.
    Guarantees strict Zero-PHI across all labels.
    """
    content = metrics_registry.generate_prometheus_text()
    return Response(content=content, media_type="text/plain; version=0.0.4")


@router.get(
    "/metrics/json",
    status_code=status.HTTP_200_OK,
    summary="JSON Metrics Snapshot",
)
def get_metrics_json():
    """
    Returns a JSON snapshot of collected metrics.
    """
    return metrics_registry.get_metrics_snapshot()
