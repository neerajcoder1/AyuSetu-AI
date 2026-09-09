"""
Audit Cryptographic Hash Chain
===============================
Deterministic SHA-256 hash chaining implementation per PRD v2.0 §21.8.
Uses RFC 8785 canonical JSON formatting (sorted keys, compact whitespace)
to guarantee deterministic hashing across languages and environments.
"""

import hashlib
import json
from typing import Any, Dict, Optional

# Authoritative Genesis Block constants
GENESIS_HASH: str = "0" * 64
GENESIS_SEQ: int = 0


def canonical_json(data: Any) -> bytes:
    """
    Produce canonical deterministic JSON serialization (RFC 8785).
    Keys are recursively sorted and separators are stripped of whitespace.
    """
    return json.dumps(
        data,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Compute SHA-256 digest formatted as lowercase hexadecimal string."""
    return hashlib.sha256(data).hexdigest()


def compute_payload_hash(safe_metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Compute SHA-256 hash of safe non-PHI metadata.
    Returns 64-char lowercase hex digest.
    """
    payload_obj = safe_metadata if safe_metadata is not None else {}
    return sha256_hex(canonical_json(payload_obj))


def compute_entry_hash(
    seq: int,
    ts: str,
    actor_id: str,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    outcome: str,
    payload_hash: str,
    prev_hash: str,
    patient_id: Optional[str] = None,
    encounter_id: Optional[str] = None,
    reason: Optional[str] = None,
    src_device: Optional[str] = None,
    src_ip: Optional[str] = None,
) -> str:
    """
    Compute deterministic entry hash of an audit event block.
    Integrates all canonical event fields and links strictly to prev_hash.
    """
    canonical_block = {
        "action": str(action),
        "actor_id": str(actor_id),
        "actor_role": str(actor_role),
        "encounter_id": str(encounter_id) if encounter_id else None,
        "outcome": str(outcome),
        "patient_id": str(patient_id) if patient_id else None,
        "payload_hash": str(payload_hash),
        "prev_hash": str(prev_hash),
        "reason": str(reason) if reason is not None else None,
        "resource_id": str(resource_id),
        "resource_type": str(resource_type),
        "seq": int(seq),
        "src_device": str(src_device) if src_device else None,
        "src_ip": str(src_ip) if src_ip else None,
        "ts": str(ts),
    }
    return sha256_hex(canonical_json(canonical_block))


def compute_offline_entry_hash(
    local_seq: int,
    ts: str,
    actor_id: str,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    outcome: str,
    payload_hash: str,
    prev_hash: str,
    src_device: str,
    patient_id: Optional[str] = None,
    encounter_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> str:
    """
    Compute deterministic local entry hash for an offline station audit event.
    """
    canonical_block = {
        "action": str(action),
        "actor_id": str(actor_id),
        "actor_role": str(actor_role),
        "encounter_id": str(encounter_id) if encounter_id else None,
        "local_seq": int(local_seq),
        "outcome": str(outcome),
        "patient_id": str(patient_id) if patient_id else None,
        "payload_hash": str(payload_hash),
        "prev_hash": str(prev_hash),
        "reason": str(reason) if reason is not None else None,
        "resource_id": str(resource_id),
        "resource_type": str(resource_type),
        "src_device": str(src_device),
        "ts": str(ts),
    }
    return sha256_hex(canonical_json(canonical_block))
