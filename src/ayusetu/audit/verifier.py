"""
Audit Log Integrity Verifier
============================
Performs end-to-end mathematical verification of cryptographic audit chains.
Validates sequence monotonicity, canonical SHA-256 hashes, hash link continuity,
and station-offline batch integrity per PRD v2.0 §21.8.
"""

from typing import Dict, List, Optional, Set, Tuple

from ayusetu.audit.models import (
    AuditEventDTO,
    AuditVerificationResult,
    OfflineAuditSyncBatch,
)
from ayusetu.audit.chain import (
    GENESIS_HASH,
    compute_entry_hash,
    compute_offline_entry_hash,
)


class AuditVerifier:
    """
    Independent cryptographic verifier for the global audit log and offline batches.
    """

    @classmethod
    def verify_chain(
        cls,
        events: List[AuditEventDTO],
        expected_seed_hash: str = GENESIS_HASH,
    ) -> AuditVerificationResult:
        """
        Verify the mathematical integrity of a sequence of audit events.
        """
        if not events:
            return AuditVerificationResult(
                valid=True,
                checked_events=0,
                last_valid_sequence=0,
                head_hash=expected_seed_hash,
                failure=None,
            )

        prev_expected_hash = expected_seed_hash
        last_valid_seq = 0

        for idx, ev in enumerate(events):
            expected_seq = idx + 1

            # 1. Monotonic sequence validation
            if ev.seq != expected_seq:
                return AuditVerificationResult(
                    valid=False,
                    checked_events=idx + 1,
                    last_valid_sequence=last_valid_seq,
                    head_hash=prev_expected_hash,
                    failure={
                        "code": "SEQUENCE_GAP",
                        "sequence": ev.seq,
                        "expected_sequence": expected_seq,
                        "detail": f"Expected sequence {expected_seq} but found {ev.seq}",
                    },
                )

            # 2. Previous hash continuity
            if ev.prev_hash != prev_expected_hash:
                return AuditVerificationResult(
                    valid=False,
                    checked_events=idx + 1,
                    last_valid_sequence=last_valid_seq,
                    head_hash=prev_expected_hash,
                    failure={
                        "code": "PREV_HASH_MISMATCH",
                        "sequence": ev.seq,
                        "expected_prev_hash": prev_expected_hash,
                        "actual_prev_hash": ev.prev_hash,
                        "detail": f"Event {ev.seq} prev_hash broken; expected {prev_expected_hash[:16]}...",
                    },
                )

            # 3. Canonical entry hash recomputation
            computed_hash = compute_entry_hash(
                seq=ev.seq,
                ts=ev.ts,
                actor_id=ev.actor_id,
                actor_role=ev.actor_role,
                action=ev.action,
                resource_type=ev.resource_type,
                resource_id=ev.resource_id,
                outcome=ev.outcome,
                payload_hash=ev.payload_hash,
                prev_hash=ev.prev_hash,
                patient_id=ev.patient_id,
                encounter_id=ev.encounter_id,
                reason=ev.reason,
                src_device=ev.src_device,
                src_ip=ev.src_ip,
            )

            if computed_hash != ev.entry_hash:
                return AuditVerificationResult(
                    valid=False,
                    checked_events=idx + 1,
                    last_valid_sequence=last_valid_seq,
                    head_hash=prev_expected_hash,
                    failure={
                        "code": "ENTRY_HASH_TAMPERED",
                        "sequence": ev.seq,
                        "expected_entry_hash": computed_hash,
                        "actual_entry_hash": ev.entry_hash,
                        "detail": f"Event {ev.seq} hash tampered; payload or metadata modified",
                    },
                )

            prev_expected_hash = ev.entry_hash
            last_valid_seq = ev.seq

        return AuditVerificationResult(
            valid=True,
            checked_events=len(events),
            last_valid_sequence=last_valid_seq,
            head_hash=prev_expected_hash,
            failure=None,
        )

    @classmethod
    def verify_offline_batch(
        cls,
        batch: OfflineAuditSyncBatch,
        known_server_heads: Set[str],
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Verify the internal cryptographic validity and server linkage of an offline batch.
        Returns: (is_valid, failure_code, failure_reason)
        """
        if not batch.events:
            return True, None, None

        # 1. Seed head linkage check
        if batch.seed_head_hash not in known_server_heads:
            return (
                False,
                "UNKNOWN_SEED_HEAD",
                f"Seed head {batch.seed_head_hash[:16]}... is not a recognized server audit tip",
            )

        prev_expected_hash = batch.seed_head_hash

        for idx, ev in enumerate(batch.events):
            expected_local_seq = idx + 1

            # 2. Device identity consistency
            if ev.src_device != batch.device_id:
                return (
                    False,
                    "DEVICE_MISMATCH",
                    f"Event at index {idx} has device {ev.src_device} matching batch device {batch.device_id}",
                )

            # 3. Local sequence monotonicity
            if ev.local_seq != expected_local_seq:
                return (
                    False,
                    "LOCAL_SEQUENCE_GAP",
                    f"Expected local_seq {expected_local_seq} but found {ev.local_seq}",
                )

            # 4. Hash link continuity
            if ev.prev_hash != prev_expected_hash:
                return (
                    False,
                    "LOCAL_PREV_HASH_BROKEN",
                    f"Local event {ev.local_seq} prev_hash does not link to previous entry",
                )

            # 5. Local entry hash recomputation
            computed_hash = compute_offline_entry_hash(
                local_seq=ev.local_seq,
                ts=ev.ts,
                actor_id=ev.actor_id,
                actor_role=ev.actor_role,
                action=ev.action,
                resource_type=ev.resource_type,
                resource_id=ev.resource_id,
                outcome=ev.outcome,
                payload_hash=ev.payload_hash,
                prev_hash=ev.prev_hash,
                src_device=ev.src_device,
                patient_id=ev.patient_id,
                encounter_id=ev.encounter_id,
                reason=ev.reason,
            )

            if computed_hash != ev.entry_hash:
                return (
                    False,
                    "LOCAL_ENTRY_HASH_TAMPERED",
                    f"Local event {ev.local_seq} payload or hash has been tampered with",
                )

            prev_expected_hash = ev.entry_hash

        return True, None, None


audit_verifier = AuditVerifier()
