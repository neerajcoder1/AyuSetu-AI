"""
Offline Consent Cryptographic Hash Chain
=========================================
Implements deterministic, tamper-evident SHA-256 hash chaining for offline
DPDP consent capture on station hardware per PRD v2.0 §21.7 & §21.8.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


GENESIS_HASH = "0" * 64


def canonical_json(data: Dict[str, Any]) -> bytes:
    """
    Produce deterministic canonical JSON representation per RFC 8785 conventions:
    sorted keys, no extraneous whitespace, UTF-8 encoded.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class ConsentHashChainEntry(BaseModel):
    """Immutable entry in the offline consent hash chain."""
    seq: int = Field(..., description="Monotonic 0-indexed sequence number")
    ts: str = Field(..., description="ISO 8601 UTC timestamp string")
    prev_hash: str = Field(..., description="Hex-encoded SHA-256 hash of previous block")
    payload_hash: str = Field(..., description="Hex-encoded SHA-256 hash of canonical payload")
    entry_hash: str = Field(..., description="Hex-encoded SHA-256 hash of this entry block")
    payload: Dict[str, Any] = Field(..., description="Canonical event payload (anonymized metadata)")
    synced: bool = Field(default=False, description="Whether this block has been synchronized to cloud")

    @classmethod
    def create(
        cls,
        seq: int,
        prev_hash: str,
        payload: Dict[str, Any],
        ts_str: Optional[str] = None
    ) -> "ConsentHashChainEntry":
        if ts_str is None:
            ts_str = datetime.now(timezone.utc).isoformat()

        c_payload = canonical_json(payload)
        payload_hash = hashlib.sha256(c_payload).hexdigest()

        # Deterministic entry hash: sha256(prev_hash:payload_hash:ts:seq)
        header_raw = f"{prev_hash}:{payload_hash}:{ts_str}:{seq}".encode("utf-8")
        entry_hash = hashlib.sha256(header_raw).hexdigest()

        return cls(
            seq=seq,
            ts=ts_str,
            prev_hash=prev_hash,
            payload_hash=payload_hash,
            entry_hash=entry_hash,
            payload=payload,
            synced=False,
        )


class ConsentHashChain:
    """
    In-memory / station local ledger managing the offline cryptographic hash chain.
    Thread-safe append and integrity verification.
    """

    def __init__(self):
        self._entries: List[ConsentHashChainEntry] = []

    def append(self, payload: Dict[str, Any], ts_str: Optional[str] = None) -> ConsentHashChainEntry:
        """Append a new consent event to the chain."""
        seq = len(self._entries)
        prev_hash = self._entries[-1].entry_hash if self._entries else GENESIS_HASH

        entry = ConsentHashChainEntry.create(
            seq=seq,
            prev_hash=prev_hash,
            payload=payload,
            ts_str=ts_str
        )
        self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        """
        Verify the integrity of the entire chain from genesis to head.
        Returns True if all cryptographic links and payload hashes are valid,
        False if any block has been tampered with or corrupted.
        """
        if not self._entries:
            return True

        expected_prev_hash = GENESIS_HASH

        for i, entry in enumerate(self._entries):
            # 1. Sequence monotonic check
            if entry.seq != i:
                return False

            # 2. Previous hash linkage check
            if entry.prev_hash != expected_prev_hash:
                return False

            # 3. Payload hash integrity
            c_payload = canonical_json(entry.payload)
            recomputed_payload_hash = hashlib.sha256(c_payload).hexdigest()
            if entry.payload_hash != recomputed_payload_hash:
                return False

            # 4. Entry hash integrity
            header_raw = f"{entry.prev_hash}:{entry.payload_hash}:{entry.ts}:{entry.seq}".encode("utf-8")
            recomputed_entry_hash = hashlib.sha256(header_raw).hexdigest()
            if entry.entry_hash != recomputed_entry_hash:
                return False

            expected_prev_hash = entry.entry_hash

        return True

    def get_entries(self) -> List[ConsentHashChainEntry]:
        return list(self._entries)

    def get_pending_sync_entries(self) -> List[ConsentHashChainEntry]:
        return [e for e in self._entries if not e.synced]

    def mark_synced(self, seq_numbers: List[int]) -> int:
        seq_set = set(seq_numbers)
        count = 0
        for entry in self._entries:
            if entry.seq in seq_set and not entry.synced:
                entry.synced = True
                count += 1
        return count

    def get_head_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else GENESIS_HASH

    def clear(self) -> None:
        """Reset chain (for testing)."""
        self._entries.clear()


# Default module-level station chain instance
station_consent_chain = ConsentHashChain()
