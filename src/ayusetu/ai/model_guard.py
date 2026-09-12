"""
Model Artifact Integrity & Checksum Verification Guard
======================================================
Authoritative model security module per PRD v3 §21.8 and SEC-T-10.
Enforces:
1. SHA-256 integrity verification of all ML model artifacts prior to loading.
2. Fail-closed refusal and MODEL_TAMPER_DETECTED incident dispatch on hash mismatch.
"""

import hashlib
import os
from typing import Dict, Optional
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode
from ayusetu.gateway.auth.event_hooks import dispatch_security_event


# Registry of approved model hashes (SHA-256)
DEFAULT_APPROVED_MODEL_HASHES: Dict[str, str] = {
    "whisper_hindi_onnx": "a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0",
    "indic_bert_ner": "b2c3d4e5f6a708192a3b4c5d6e7f8a90123456789abcdef0123456789abcdef1",
    "redflag_heuristic_rules": "c3d4e5f6a7b8091a2b3c4d5e6f7a8b90123456789abcdef0123456789abcdef2",
    "synthetic_clinical_manifest": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}


class ModelIntegrityGuard:
    """Validator for ML model weights and artifact integrity."""

    def __init__(self, registry: Optional[Dict[str, str]] = None) -> None:
        self._registry: Dict[str, str] = dict(registry or DEFAULT_APPROVED_MODEL_HASHES)

    def register_model_hash(self, model_id: str, sha256_hash: str) -> None:
        """Register or update an approved model hash."""
        self._registry[model_id] = sha256_hash.lower().strip()

    def compute_sha256(self, data_or_path: bytes | str) -> str:
        """Compute SHA-256 hash of byte payload or file path."""
        hasher = hashlib.sha256()
        if isinstance(data_or_path, str):
            if not os.path.exists(data_or_path):
                raise FileNotFoundError(f"Model file not found: {data_or_path}")
            with open(data_or_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
        elif isinstance(data_or_path, bytes):
            hasher.update(data_or_path)
        else:
            raise TypeError("Expected bytes or file path string")
        return hasher.hexdigest().lower()

    def verify_and_load(
        self,
        model_id: str,
        data_or_path: bytes | str,
        expected_hash: Optional[str] = None,
    ) -> bool:
        """
        Verify model checksum before loading into memory.
        Raises AyuSetuGatewayError (403) and raises security incident on tampering.
        """
        expected = expected_hash or self._registry.get(model_id)
        if not expected:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Model integrity verification failed: model '{model_id}' is not in approved registry",
                403,
            )

        actual_hash = self.compute_sha256(data_or_path)
        if actual_hash != expected.lower().strip():
            resource_name = data_or_path if isinstance(data_or_path, str) else f"memory_bytes_{model_id}"
            dispatch_security_event(
                event_type="MODEL_TAMPER_DETECTED",
                actor_id="model_integrity_guard",
                actor_role="system",
                target_resource=resource_name,
                reason=f"Model checksum mismatch for '{model_id}': computed={actual_hash} != expected={expected}",
                metadata={
                    "model_id": model_id,
                    "computed_hash": actual_hash,
                    "expected_hash": expected,
                },
            )
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"CRITICAL: Model artifact '{model_id}' integrity verification failed (checksum mismatch). Model load refused.",
                403,
            )

        return True


model_integrity_guard = ModelIntegrityGuard()
