"""
Phase 9 Security Regression: Audit Immutability & Tamper Detection
==================================================================
Validates:
- Monotonic sequence numbering and SHA-256 hash chaining.
- Tamper detection when historical records or hashes are modified.
- Fail-closed behavior on corrupted chain head.
"""

import pytest
from ayusetu.audit.models import AuditEventCreate, AuditAction, AuditOutcome
from ayusetu.audit.service import audit_service
from ayusetu.audit.repository import AuditRepository


def test_audit_chain_monotonic_hash_linkage():
    """Verify each newly appended audit event references the previous event's entry_hash."""
    e1 = audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="physician",
        action=AuditAction.READ,
        resource_type="encounter",
        resource_id="018f0000-0000-7000-8000-000000000011",
        outcome=AuditOutcome.ALLOW,
    )
    e2 = audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="physician",
        action=AuditAction.CREATE,
        resource_type="encounter",
        resource_id="018f0000-0000-7000-8000-000000000011",
        outcome=AuditOutcome.ALLOW,
    )

    assert e2.seq == e1.seq + 1
    assert e2.prev_hash == e1.entry_hash
    assert e2.entry_hash != e1.entry_hash


def test_audit_tamper_detection_halts_append():
    """Verify tampering with persisted chain entry triggers security alert and halts append."""
    repo = AuditRepository()
    
    # Record initial valid event
    ev1 = repo.append(
        AuditEventCreate(
            actor_id="018f0000-0000-7000-8000-000000000001",
            actor_role="physician",
            action=AuditAction.CREATE,
            resource_type="encounter",
            resource_id="018f0000-0000-7000-8000-000000000011",
            outcome=AuditOutcome.ALLOW,
        )
    )

    # Tamper with the row in DB directly
    with repo._session_factory() as db:
        from ayusetu.common.models import AuditEvent
        latest = db.query(AuditEvent).order_by(AuditEvent.seq.desc()).first()
        if latest:
            latest.entry_hash = b"\x00" * 32
            db.commit()

    # Next append must fail closed due to integrity compromise
    with pytest.raises(RuntimeError) as exc:
        repo.append(
            AuditEventCreate(
                actor_id="018f0000-0000-7000-8000-000000000001",
                actor_role="physician",
                action=AuditAction.CREATE,
                resource_type="encounter",
                resource_id="018f0000-0000-7000-8000-000000000011",
                outcome=AuditOutcome.ALLOW,
            )
        )
    assert "integrity compromised" in str(exc.value).lower()
