"""
Test Suite: Offline Consent Cryptographic Hash Chain
=====================================================
Validates monotonic sequencing, SHA-256 hash chaining, deterministic canonicalization,
and tamper detection per PRD v2.0 §21.7 & §21.8.
"""

import pytest
from ayusetu.consent.offline_chain import (
    ConsentHashChain,
    ConsentHashChainEntry,
    canonical_json,
    GENESIS_HASH,
)


def test_canonical_json_deterministic():
    data1 = {"b": 2, "a": 1, "nested": {"y": True, "x": False}}
    data2 = {"a": 1, "nested": {"x": False, "y": True}, "b": 2}
    assert canonical_json(data1) == canonical_json(data2)


def test_offline_chain_append_and_verification():
    chain = ConsentHashChain()
    assert chain.verify_chain() is True

    # 1. Append entry 0
    p0 = {"patient_id": "p-001", "encounter_id": "e-001", "purposes": {"clinical": True, "abdm": False}}
    e0 = chain.append(p0, ts_str="2026-09-09T10:00:00Z")
    assert e0.seq == 0
    assert e0.prev_hash == GENESIS_HASH
    assert e0.entry_hash is not None
    assert chain.verify_chain() is True

    # 2. Append entry 1
    p1 = {"patient_id": "p-002", "encounter_id": "e-002", "purposes": {"clinical": True, "abdm": True}}
    e1 = chain.append(p1, ts_str="2026-09-09T10:05:00Z")
    assert e1.seq == 1
    assert e1.prev_hash == e0.entry_hash
    assert chain.verify_chain() is True

    # 3. Append entry 2
    p2 = {"patient_id": "p-003", "encounter_id": "e-003", "purposes": {"clinical": True, "qi": True}}
    e2 = chain.append(p2, ts_str="2026-09-09T10:10:00Z")
    assert e2.seq == 2
    assert e2.prev_hash == e1.entry_hash
    assert chain.verify_chain() is True


def test_offline_chain_tamper_detection_payload_modified():
    chain = ConsentHashChain()
    chain.append({"patient_id": "p-001", "action": "grant"}, ts_str="2026-09-09T10:00:00Z")
    chain.append({"patient_id": "p-002", "action": "grant"}, ts_str="2026-09-09T10:05:00Z")
    assert chain.verify_chain() is True

    # Tamper with entry 0's payload without recalculating hashes
    chain._entries[0].payload["action"] = "malicious_tamper"
    assert chain.verify_chain() is False


def test_offline_chain_tamper_detection_hash_modified():
    chain = ConsentHashChain()
    chain.append({"patient_id": "p-001"}, ts_str="2026-09-09T10:00:00Z")
    chain.append({"patient_id": "p-002"}, ts_str="2026-09-09T10:05:00Z")
    assert chain.verify_chain() is True

    # Tamper with prev_hash of entry 1
    chain._entries[1].prev_hash = "deadbeef" * 8
    assert chain.verify_chain() is False


def test_offline_chain_sync_marking():
    chain = ConsentHashChain()
    chain.append({"patient_id": "p-001"}, ts_str="2026-09-09T10:00:00Z")
    chain.append({"patient_id": "p-002"}, ts_str="2026-09-09T10:05:00Z")

    pending = chain.get_pending_sync_entries()
    assert len(pending) == 2

    # Mark seq 0 as synced
    chain.mark_synced([0])
    pending_after = chain.get_pending_sync_entries()
    assert len(pending_after) == 1
    assert pending_after[0].seq == 1
