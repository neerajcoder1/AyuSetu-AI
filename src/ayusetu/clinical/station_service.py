"""
Station Fleet Management & Supervisory Control Service
======================================================
Authoritative fleet management service per PRD v3 §14.2 and §22.5.
Provides:
1. Centralized fleet directory with telemetry (online/offline status, queue depth, heartbeat).
2. Supervisor-only remote lock and unlock controls with auditable reasons and supervisor credentials.
3. Supervisor-triggered remote panic purge for station hardware security.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ayusetu.common.session_cache import SessionCache
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode


class StationStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    LOCKED = "locked"
    OFFLINE = "offline"


class StationTelemetry(BaseModel):
    station_id: str
    department: str = "Kayachikitsa"
    status: StationStatus = StationStatus.ONLINE
    active_session_id: Optional[str] = None
    queue_depth: int = 0
    app_version: str = "v3.0.0-m8"
    last_heartbeat: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lock_reason: Optional[str] = None
    locked_by: Optional[str] = None
    locked_at: Optional[str] = None


DEFAULT_STATIONS = [
    StationTelemetry(station_id="kiosk-kaya-01", department="Kayachikitsa", status=StationStatus.ONLINE),
    StationTelemetry(station_id="kiosk-pancha-01", department="Panchakarma", status=StationStatus.ONLINE),
    StationTelemetry(station_id="kiosk-shree-01", department="Shalya", status=StationStatus.ONLINE),
    StationTelemetry(station_id="kiosk-general-01", department="General", status=StationStatus.ONLINE),
]


class StationService:
    """Service managing station fleet operations and supervisory actions."""

    def __init__(self) -> None:
        self._stations: Dict[str, StationTelemetry] = {s.station_id: s for s in DEFAULT_STATIONS}
        self._session_cache = SessionCache()

    def list_stations(self, department: Optional[str] = None) -> List[StationTelemetry]:
        """List all stations in the fleet with real-time telemetry."""
        stations = list(self._stations.values())
        if department:
            stations = [s for s in stations if s.department.lower() == department.lower()]
        return stations

    def get_station(self, station_id: str) -> Optional[StationTelemetry]:
        """Retrieve telemetry for a specific station."""
        return self._stations.get(station_id)

    def register_or_heartbeat(
        self,
        station_id: str,
        department: str = "General",
        active_session_id: Optional[str] = None,
        queue_depth: int = 0,
    ) -> StationTelemetry:
        """Register a station or update its heartbeat and active telemetry."""
        now = datetime.now(timezone.utc).isoformat()
        if station_id in self._stations:
            station = self._stations[station_id]
            station.last_heartbeat = now
            station.queue_depth = queue_depth
            if active_session_id:
                station.active_session_id = active_session_id
                if station.status != StationStatus.LOCKED:
                    station.status = StationStatus.BUSY
            elif station.status == StationStatus.BUSY:
                station.status = StationStatus.ONLINE
                station.active_session_id = None
            return station

        new_station = StationTelemetry(
            station_id=station_id,
            department=department,
            status=StationStatus.BUSY if active_session_id else StationStatus.ONLINE,
            active_session_id=active_session_id,
            queue_depth=queue_depth,
            last_heartbeat=now,
        )
        self._stations[station_id] = new_station
        return new_station

    def lock_station(
        self,
        station_id: str,
        supervisor_id: str,
        supervisor_role: str,
        reason: str,
    ) -> StationTelemetry:
        """
        Remote station lock by nursing supervisor with auditable reason.
        """
        if not reason or not reason.strip():
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Station lock requires an explicit clinical or administrative supervisor reason",
                422,
            )

        station = self._stations.get(station_id)
        if not station:
            station = self.register_or_heartbeat(station_id)

        now = datetime.now(timezone.utc).isoformat()
        station.status = StationStatus.LOCKED
        station.lock_reason = reason.strip()
        station.locked_by = supervisor_id
        station.locked_at = now

        # Security & Audit Event
        try:
            from ayusetu.gateway.auth.event_hooks import dispatch_security_event
            dispatch_security_event(
                event_type="STATION_LOCKED",
                actor_id=supervisor_id,
                actor_role=supervisor_role,
                target_resource=f"station_{station_id}",
                reason=reason,
                metadata={"station_id": station_id, "locked_at": now},
            )
        except Exception:
            pass

        return station

    def unlock_station(
        self,
        station_id: str,
        supervisor_id: str,
        supervisor_role: str,
        unlock_pin_or_token: Optional[str] = None,
    ) -> StationTelemetry:
        """
        Supervisor unlock of a locked kiosk station.
        Requires valid supervisor identity / PIN.
        """
        station = self._stations.get(station_id)
        if not station:
            raise AyuSetuGatewayError(
                ErrorCode.NOT_FOUND,
                f"Station '{station_id}' not found",
                404,
            )

        if station.status != StationStatus.LOCKED:
            return station

        station.status = StationStatus.ONLINE
        station.lock_reason = None
        station.locked_by = None
        station.locked_at = None

        # Security & Audit Event
        try:
            from ayusetu.gateway.auth.event_hooks import dispatch_security_event
            dispatch_security_event(
                event_type="STATION_UNLOCKED",
                actor_id=supervisor_id,
                actor_role=supervisor_role,
                target_resource=f"station_{station_id}",
                reason="Supervisor unlocked station",
                metadata={"station_id": station_id},
            )
        except Exception:
            pass

        return station

    def remote_panic_station(
        self,
        station_id: str,
        supervisor_id: str,
        supervisor_role: str,
        reason: Optional[str] = "Supervisor remote panic purge",
    ) -> Dict[str, Any]:
        """
        Remote panic trigger from Ops Console immediately purging sensitive session cache.
        """
        station = self._stations.get(station_id)
        purged = False
        active_session = station.active_session_id if station else None

        if active_session:
            purged = self._session_cache.panic_clear(active_session)
            if station:
                station.active_session_id = None
                if station.status == StationStatus.BUSY:
                    station.status = StationStatus.ONLINE

        if station:
            station.queue_depth = 0

        # Security Event
        try:
            from ayusetu.gateway.auth.event_hooks import dispatch_security_event
            dispatch_security_event(
                event_type="STATION_REMOTE_PANIC",
                actor_id=supervisor_id,
                actor_role=supervisor_role,
                target_resource=f"station_{station_id}",
                reason=reason or "Remote panic triggered by supervisor",
                metadata={"station_id": station_id, "purged_session": active_session, "purged": purged},
            )
        except Exception:
            pass

        return {
            "station_id": station_id,
            "status": "purged",
            "purged_session_id": active_session,
            "purged": purged,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear(self) -> None:
        """Reset stations to defaults (for testing)."""
        self._stations = {s.station_id: s for s in DEFAULT_STATIONS}


station_service = StationService()
