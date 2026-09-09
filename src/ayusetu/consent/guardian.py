"""
Guardian & Consent Authority Verification Boundary
===================================================
Enforces DPDP §9(1) / PRD §21.7 rules:
- Under-18 patients require verifiable guardian consent.
- Companions assisting the patient cannot independently grant consent.
- Guardian verification is mandatory for minors.

PRODUCTION INTEGRATION BOUNDARY:
This module enforces the domain and security policy for guardian consent.
Client-supplied `is_verified` booleans are NEVER trusted as authoritative proof.
Production deployment MUST replace `GuardianVerificationAdapter` with authoritative
government identity verification systems (e.g. Aadhaar guardian verification / Court guardianship).
"""

from typing import Optional, Set, Tuple
from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.consent.models import GuardianContext, GuardianRelationship


class GuardianVerificationAdapter:
    """
    Development/Testing Guardian Verification Adapter.
    
    Enforces server-side verification rather than trusting client-submitted flags.
    Production deployment MUST replace this adapter with authoritative external
    identity and relationship registries.
    """
    _verified_registry: Set[Tuple[str, str]] = set()  # (guardian_id, patient_id)

    @classmethod
    def register_verified_guardian(cls, guardian_id: str, patient_id: str) -> None:
        """Register a verified guardian-patient relationship for development/testing."""
        cls._verified_registry.add((guardian_id.strip(), patient_id.strip()))

    @classmethod
    def unregister_guardian(cls, guardian_id: str, patient_id: str) -> None:
        cls._verified_registry.discard((guardian_id.strip(), patient_id.strip()))

    @classmethod
    def is_verified_guardian(cls, guardian_id: Optional[str], patient_id: Optional[str]) -> bool:
        """
        Verify if guardian is authoritative for patient.
        Always evaluates server-side trusted state; client input is ignored.
        """
        if not guardian_id or not patient_id:
            return False
        return (guardian_id.strip(), patient_id.strip()) in cls._verified_registry

    @classmethod
    def clear(cls) -> None:
        cls._verified_registry.clear()


class ConsentAuthorityValidator:
    """Validates whether the acting caller has legal authority to grant/withdraw consent."""

    @staticmethod
    def validate_grant_authority(
        principal: Optional[Principal],
        patient_id: str,
        is_minor: bool,
        guardian_context: Optional[GuardianContext],
    ) -> None:
        """
        Validate consent authority. Raises AyuSetuGatewayError if unauthorized.
        """
        # 1. Under-18 Minor Policy Enforcement
        if is_minor:
            if not guardian_context:
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    "Guardian consent is required for under-18 patients per DPDP regulations",
                    403
                )

            # Trust boundary: Server-side verification check via adapter (client boolean ignored)
            is_verified = GuardianVerificationAdapter.is_verified_guardian(
                guardian_context.guardian_id, patient_id
            )
            if not is_verified:
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    f"Guardian '{guardian_context.guardian_id}' is not verified for patient '{patient_id}'. "
                    "Verifiable guardian consent is required for minors",
                    403
                )

            if not isinstance(guardian_context.relationship, GuardianRelationship):
                try:
                    GuardianRelationship(guardian_context.relationship)
                except ValueError:
                    raise AyuSetuGatewayError(
                        ErrorCode.POLICY_DENIED,
                        f"Unrecognized guardian relationship: {guardian_context.relationship}",
                        403
                    )

            # If principal is a Companion, verify they are the registered guardian
            if principal and principal.role == Role.COMPANION:
                if not GuardianVerificationAdapter.is_verified_guardian(principal.actor_id, patient_id):
                    raise AyuSetuGatewayError(
                        ErrorCode.POLICY_DENIED,
                        "Companion is not the verified legal guardian for this minor patient",
                        403
                    )

            # Valid verified guardian present for minor
            return

        # 2. Adult Patient & Companion Boundary
        if principal:
            # If the caller is acting in Companion role, they cannot independently grant consent for an adult
            if principal.role == Role.COMPANION:
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    "Companion role cannot independently grant consent on behalf of an adult patient",
                    403
                )

            # Staff roles (Auditor, MRD) cannot grant consent for patients
            if principal.role in (Role.AUDITOR, Role.MRD):
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    f"Role '{principal.role.value}' is not authorized to grant patient consent",
                    403
                )
