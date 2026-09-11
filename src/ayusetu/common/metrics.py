"""
Operational Telemetry & Metrics Registry
=========================================
Lightweight, thread-safe in-memory Prometheus-compatible metrics registry per Phase 8.
Guarantees ZERO-PHI in all metric labels and enforces low-cardinality path templating.
"""

from collections import defaultdict
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# UUID & Hash regex patterns for low-cardinality route normalization
UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
HEX_PATTERN = re.compile(r"\b[0-9a-fA-F]{16,64}\b")
NUMERIC_ID_PATTERN = re.compile(r"/\d+(?=/|$)")


def normalize_route_path(path: str) -> str:
    """
    Normalizes variable path segments (UUIDs, hashes, numeric IDs) into static placeholders
    to enforce strict low-cardinality in metric dimensions.
    """
    if not path:
        return "/"
    # Clean query parameters if present
    path = path.split("?")[0]
    
    # Replace UUIDs with {id}
    normalized = UUID_PATTERN.sub("{id}", path)
    # Replace hashes with {token}
    normalized = HEX_PATTERN.sub("{token}", normalized)
    # Replace standalone numeric path IDs with {id}
    normalized = NUMERIC_ID_PATTERN.sub("/{id}", normalized)
    return normalized


class MetricsRegistry:
    """
    Thread-safe in-memory metrics registry for Prometheus text exposition and JSON telemetry.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Counters: metric_name -> (label_tuple -> count)
        self._counters: Dict[str, Dict[Tuple[Tuple[str, str], ...], float]] = defaultdict(lambda: defaultdict(float))
        # Histogram buckets & sums: metric_name -> (label_tuple -> {"count": int, "sum": float, "buckets": dict})
        self._histograms: Dict[str, Dict[Tuple[Tuple[str, str], ...], Dict[str, Any]]] = defaultdict(dict)
        self._default_duration_buckets = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def inc_counter(self, name: str, labels: Optional[Dict[str, str]] = None, value: float = 1.0) -> None:
        """Increment a counter by value with labels."""
        label_key = tuple(sorted(labels.items())) if labels else ()
        with self._lock:
            self._counters[name][label_key] += value

    def observe_duration(
        self,
        name: str,
        duration_seconds: float,
        labels: Optional[Dict[str, str]] = None,
        buckets: Optional[Tuple[float, ...]] = None,
    ) -> None:
        """Observe a duration in a histogram with duration buckets."""
        label_key = tuple(sorted(labels.items())) if labels else ()
        b_list = buckets or self._default_duration_buckets

        with self._lock:
            if label_key not in self._histograms[name]:
                self._histograms[name][label_key] = {
                    "count": 0,
                    "sum": 0.0,
                    "buckets": {b: 0 for b in b_list},
                }
            entry = self._histograms[name][label_key]
            entry["count"] += 1
            entry["sum"] += duration_seconds
            for b in b_list:
                if duration_seconds <= b:
                    entry["buckets"][b] += 1

    def record_http_request(self, method: str, path: str, status_code: int, duration_seconds: float) -> None:
        """Record an incoming HTTP request in standard HTTP metrics."""
        norm_path = normalize_route_path(path)
        labels = {
            "method": method.upper(),
            "path": norm_path,
            "status": str(status_code),
        }
        self.inc_counter("ayusetu_http_requests_total", labels)
        
        hist_labels = {
            "method": method.upper(),
            "path": norm_path,
        }
        self.observe_duration("ayusetu_http_request_duration_seconds", duration_seconds, hist_labels)

    def record_security_event(self, event_type: str, outcome: str) -> None:
        """Record an operational security event (AUTH_FAILED, IDOR_ATTEMPT, etc.)."""
        labels = {
            "event_type": str(event_type).upper(),
            "outcome": str(outcome).upper(),
        }
        self.inc_counter("ayusetu_security_events_total", labels)

    def record_redflag_trigger(self, tier: int, rule_id: str) -> None:
        """Record red-flag rule evaluation trigger."""
        labels = {
            "tier": str(tier),
            "rule_id": str(rule_id),
        }
        self.inc_counter("ayusetu_redflag_triggers_total", labels)

    def record_deid_export(self, purpose: str, outcome: str) -> None:
        """Record de-identified cohort export outcome."""
        labels = {
            "purpose": str(purpose).lower(),
            "outcome": str(outcome).upper(),
        }
        self.inc_counter("ayusetu_deid_exports_total", labels)

    def record_dependency_health(self, dependency: str, status: str) -> None:
        """Record dependency health check outcome."""
        labels = {
            "dependency": str(dependency).lower(),
            "status": str(status).lower(),
        }
        self.inc_counter("ayusetu_dependency_health_total", labels)

    def generate_prometheus_text(self) -> str:
        """Generate standard Prometheus text exposition format (version 0.0.4)."""
        lines: List[str] = [
            "# HELP ayusetu_http_requests_total Total count of HTTP requests processed by the gateway",
            "# TYPE ayusetu_http_requests_total counter",
        ]

        with self._lock:
            # 1. Output counters
            for name, series_dict in sorted(self._counters.items()):
                if name != "ayusetu_http_requests_total":
                    lines.append(f"# HELP {name} Operational counter metric")
                    lines.append(f"# TYPE {name} counter")

                for label_key, val in sorted(series_dict.items()):
                    if label_key:
                        label_str = ",".join(f'{k}="{v}"' for k, v in label_key)
                        lines.append(f"{name}{{{label_str}}} {val}")
                    else:
                        lines.append(f"{name} {val}")

            # 2. Output histograms
            for name, series_dict in sorted(self._histograms.items()):
                lines.append(f"# HELP {name} Duration histogram in seconds")
                lines.append(f"# TYPE {name} histogram")

                for label_key, h_data in sorted(series_dict.items()):
                    base_labels = dict(label_key)
                    # Buckets
                    for b_val, count in sorted(h_data["buckets"].items()):
                        b_labels = dict(base_labels)
                        b_labels["le"] = str(b_val)
                        l_str = ",".join(f'{k}="{v}"' for k, v in sorted(b_labels.items()))
                        lines.append(f"{name}_bucket{{{l_str}}} {count}")
                    
                    # +Inf bucket
                    inf_labels = dict(base_labels)
                    inf_labels["le"] = "+Inf"
                    l_str = ",".join(f'{k}="{v}"' for k, v in sorted(inf_labels.items()))
                    lines.append(f"{name}_bucket{{{l_str}}} {h_data['count']}")

                    # Sum and Count
                    if base_labels:
                        l_str = ",".join(f'{k}="{v}"' for k, v in sorted(base_labels.items()))
                        lines.append(f"{name}_sum{{{l_str}}} {h_data['sum']:.6f}")
                        lines.append(f"{name}_count{{{l_str}}} {h_data['count']}")
                    else:
                        lines.append(f"{name}_sum {h_data['sum']:.6f}")
                        lines.append(f"{name}_count {h_data['count']}")

        return "\n".join(lines) + "\n"

    def get_metrics_snapshot(self) -> Dict[str, Any]:
        """Return JSON dictionary snapshot of current metrics."""
        with self._lock:
            counters_summary = {}
            for name, series_dict in self._counters.items():
                counters_summary[name] = {
                    ",".join(f"{k}={v}" for k, v in lk): val for lk, val in series_dict.items()
                }
            return {
                "timestamp": time.time(),
                "counters": counters_summary,
                "histograms": {
                    name: {
                        ",".join(f"{k}={v}" for k, v in lk): {
                            "count": d["count"],
                            "sum": d["sum"],
                        }
                        for lk, d in s.items()
                    }
                    for name, s in self._histograms.items()
                },
            }

    def clear_for_testing(self) -> None:
        """Reset metrics state for test isolation."""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()


# Global metrics registry singleton
metrics_registry = MetricsRegistry()
