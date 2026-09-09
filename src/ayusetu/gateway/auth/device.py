"""
Device & Station Authentication Boundary
=========================================
Handles hardware-bound device certificates, client fingerprints,
and certificate revocation list (CRL) checking per PRD v2.0 §21.3 & §21.6.

IMPORTANT TRUST BOUNDARY & ARCHITECTURE NOTES:
- Development/Test CRL Abstraction:
  The in-memory `_revoked_device_fingerprints` registry is an intentional
  development/test CRL abstraction for this prototype. It allows gateway
  authorization to enforce device revocation checks today.
  Production deployment MUST connect this boundary to the actual station
  mTLS/PKI certificate lifecycle and authoritative revocation mechanism (e.g. OCSP / CRL).
  Revocation state is intentionally in-memory for this prototype.

- Device Fingerprint Trust Boundary:
  The current `X-Device-Fingerprint` header mechanism is a development/prototype
  convention.
  "Production deployment must obtain the authenticated device identity from
  the mTLS/client-certificate layer rather than trusting a user-controlled
  fingerprint header."
"""

from typing import Optional, Set
from pydantic import BaseModel

# ==============================================================================
# Development-Only In-Memory CRL Abstraction
# ==============================================================================
# In-memory registry of revoked device certificates/fingerprints for dev/testing.
# Production must integrate with authoritative PKI/mTLS certificate status provider.
_revoked_device_fingerprints: Set[str] = set()


class DeviceContext(BaseModel):
    """Authenticated device identity."""
    device_id: str
    device_fingerprint: str
    station_type: str = "kiosk"  # 'kiosk' | 'assisted_tablet' | 'cockpit_terminal'
    is_revoked: bool = False


class DeviceAuthenticator:
    """
    Validates device certificates and enforces hardware-level revocation.
    
    In development/testing, checks incoming device fingerprint against the
    in-memory CRL abstraction.
    In production, this interface will validate hardware-backed mTLS client certificates.
    """

    @classmethod
    def revoke_device(cls, device_fingerprint: str) -> None:
        """Add device certificate fingerprint to revocation registry (Dev/Test CRL)."""
        _revoked_device_fingerprints.add(device_fingerprint)

    @classmethod
    def unrevoke_device(cls, device_fingerprint: str) -> None:
        """Remove device from revocation registry (for testing/re-enrolment)."""
        _revoked_device_fingerprints.discard(device_fingerprint)

    @classmethod
    def is_revoked(cls, device_fingerprint: str) -> bool:
        """Check if device certificate is revoked in the CRL abstraction."""
        return device_fingerprint in _revoked_device_fingerprints

    @classmethod
    def validate_device(cls, device_fingerprint: Optional[str]) -> Optional[DeviceContext]:
        """
        Validate incoming client certificate / device fingerprint.
        Returns DeviceContext if valid, None if missing, raises PermissionError if revoked.
        """
        if not device_fingerprint:
            return None

        clean_fp = device_fingerprint.strip()
        if cls.is_revoked(clean_fp):
            raise PermissionError(f"Device certificate has been revoked: {clean_fp[:8]}...")

        return DeviceContext(
            device_id=clean_fp,
            device_fingerprint=clean_fp,
            station_type="kiosk",
            is_revoked=False
        )
