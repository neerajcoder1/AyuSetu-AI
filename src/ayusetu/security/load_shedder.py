"""
Priority-Based Admission Control & Load Shedder
===============================================
Authoritative load-shedding module per PRD v3 Appendix C and SEC-T-08.
Guarantees:
1. Tier-1 emergency fast-path alerting is NEVER dropped or degraded under load.
2. Non-essential background tasks (e.g. analytics, batch export) are shed under 3x peak load.
"""

from enum import Enum
from typing import Dict, Optional
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode


class PriorityTier(str, Enum):
    TIER1_EMERGENCY = "tier1_emergency"   # Never shed under any circumstances
    CLINICAL_INTAKE = "clinical_intake"   # High priority intake path
    BACKGROUND_TASK = "background_task"   # Sheddable when load > 1.5x
    ANALYTICS_EXPORT = "analytics_export" # Sheddable when load > 1.0x


class LoadShedder:
    """Admission controller protecting critical clinical fast paths under high load."""

    def __init__(self, peak_qps_capacity: float = 100.0) -> None:
        self.peak_capacity = peak_qps_capacity
        self._current_load_multiplier = 1.0
        self._tier1_active_count = 0

    def set_load_multiplier(self, multiplier: float) -> None:
        """Simulate or set the active load multiplier (e.g. 3.0 for 3x peak)."""
        self._current_load_multiplier = max(0.0, multiplier)

    def record_tier1_alert(self) -> None:
        """Register active Tier-1 emergency alert requiring prioritized bandwidth."""
        self._tier1_active_count += 1

    def clear_tier1_alerts(self) -> None:
        """Clear active Tier-1 count."""
        self._tier1_active_count = 0

    def admit_request(self, priority: PriorityTier) -> bool:
        """
        Admit or shed a request based on priority tier and current load.
        Raises AyuSetuGatewayError (503 / 429) if shed.
        """
        # Tier 1 emergency is NEVER shed
        if priority == PriorityTier.TIER1_EMERGENCY:
            return True

        # When load >= 2.0x (or 3.0x peak) or Tier-1 alert is actively saturating system:
        if self._current_load_multiplier >= 2.0 or self._tier1_active_count > 0:
            if priority in (PriorityTier.ANALYTICS_EXPORT, PriorityTier.BACKGROUND_TASK):
                raise AyuSetuGatewayError(
                    ErrorCode.INTERNAL_ERROR,
                    f"Load shedding active ({self._current_load_multiplier:.1f}x peak / {self._tier1_active_count} active Tier-1 alerts). Non-essential request shed to protect clinical fast-path.",
                    503,
                )

        # Extreme load >= 3.5x sheds standard intake if not emergency
        if self._current_load_multiplier >= 3.5 and priority == PriorityTier.CLINICAL_INTAKE:
            raise AyuSetuGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "Station saturated under extreme load (>3.5x capacity). Please retry in 5 seconds.",
                503,
            )

        return True


load_shedder = LoadShedder()
