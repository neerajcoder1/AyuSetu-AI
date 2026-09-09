"""
Audit Cryptographic Hash Chain Unit Tests
=========================================
Tests deterministic RFC 8785 canonical JSON, genesis block constants,
payload hashing, entry hashing, and tampering detection.
"""

import json
from ayusetu.audit.chain import (
    GENESIS_HASH,
    GENESIS_SEQ,
    canonical_json,
    compute_payload_hash,
    compute_entry_hash,
    compute_offline_entry_hash,
)


def test_genesis_constants():
    """Verify genesis block rule: sequence 0 and 64 zeros hash."""
    assert GENESIS_SEQ == 0
    assert len(GENESIS_HASH) == 64
    assert GENESIS_HASH == "0" * 64


def test_canonical_json_deterministic():
    """Verify dictionary key ordering does not affect canonical JSON output."""
    d1 = {"z": 1, "a": 2, "m": {"y": 10, "b": 20}}
    d2 = {"a": 2, "m": {"b": 20, "y": 10}, "z": 1}

    bytes1 = canonical_json(d1)
    bytes2 = canonical_json(d2)

    assert bytes1 == bytes2
    assert bytes1 == b'{"a":2,"m":{"b":20,"y":10},"z":1}'


def test_payload_hash_deterministic():
    """Verify payload hash calculation is consistent and deterministic."""
    meta1 = {"encounter_id": "018f0000-0000-7000-8000-000000000001", "action": "CREATE"}
    meta2 = {"action": "CREATE", "encounter_id": "018f0000-0000-7000-8000-000000000001"}

    hash1 = compute_payload_hash(meta1)
    hash2 = compute_payload_hash(meta2)

    assert len(hash1) == 64
    assert hash1 == hash2


def test_entry_hash_deterministic():
    """Verify entry hash generates identical cryptographic hash for identical inputs."""
    h1 = compute_entry_hash(
        seq=1,
        ts="2026-09-09T12:00:00+00:00",
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action="READ",
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000002",
        outcome="ALLOW",
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        prev_hash=GENESIS_HASH,
    )

    h2 = compute_entry_hash(
        seq=1,
        ts="2026-09-09T12:00:00+00:00",
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action="READ",
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000002",
        outcome="ALLOW",
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        prev_hash=GENESIS_HASH,
    )

    assert len(h1) == 64
    assert h1 == h2


def test_entry_hash_tamper_detection():
    """Verify that changing any canonical field changes the entry hash."""
    base_args = {
        "seq": 1,
        "ts": "2026-09-09T12:00:00+00:00",
        "actor_id": "018f0000-0000-7000-8000-000000000001",
        "actor_role": "Physician",
        "action": "READ",
        "resource_type": "Encounter",
        "resource_id": "018f0000-0000-7000-8000-000000000002",
        "outcome": "ALLOW",
        "payload_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "prev_hash": GENESIS_HASH,
    }

    original_hash = compute_entry_hash(**base_args)

    # 1. Tamper action
    tampered = dict(base_args, action="UPDATE")
    assert compute_entry_hash(**tampered) != original_hash

    # 2. Tamper outcome
    tampered = dict(base_args, outcome="DENY")
    assert compute_entry_hash(**tampered) != original_hash

    # 3. Tamper actor_id
    tampered = dict(base_args, actor_id="018f0000-0000-7000-8000-999999999999")
    assert compute_entry_hash(**tampered) != original_hash

    # 4. Tamper sequence
    tampered = dict(base_args, seq=2)
    assert compute_entry_hash(**tampered) != original_hash

    # 5. Tamper prev_hash
    tampered = dict(base_args, prev_hash="f" * 64)
    assert compute_entry_hash(**tampered) != original_hash
