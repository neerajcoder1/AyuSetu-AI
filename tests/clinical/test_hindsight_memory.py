"""Unit tests for Hindsight optional long-term memory layer.
Verifies adapter behavior, patient isolation, failure safety, and the critical invariant:
Hindsight context NEVER mutates session-scoped ClinicalMemory or deterministic extractions.
"""

import unittest
from unittest.mock import MagicMock, patch

from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot, DialogueState
from ayusetu.ai.clinical.hindsight import (
    HindsightConfig,
    HindsightMemoryRecord,
    HindsightQueryResult,
    HindsightInMemoryAdapter,
    HindsightHTTPAdapter,
    HindsightMemoryManager,
)
from ayusetu.ai.clinical.memory import ClinicalMemory
from ayusetu.ai.conversation.engine import DialogueEngine


class TestHindsightMemoryConfigAndFallback(unittest.TestCase):
    """Test configuration, disabled mode, and graceful fallbacks."""

    def test_disabled_by_default_when_flag_false(self):
        config = HindsightConfig(enabled=False)
        manager = HindsightMemoryManager(config=config)

        self.assertFalse(manager.config.enabled)
        self.assertIsNone(manager.retrieve_historical_context("P123", "headache"))

        # Storage when disabled / empty returns False without error
        res = manager.store_encounter_summary("P123", "S1", "")
        self.assertFalse(res)

    def test_fallback_to_in_memory_when_no_api_key(self):
        config = HindsightConfig(enabled=True, api_key=None, use_in_memory_fallback=True)
        manager = HindsightMemoryManager(config=config)

        self.assertTrue(manager.config.enabled)
        self.assertIsInstance(manager.adapter, HindsightInMemoryAdapter)


class TestHindsightInMemoryAdapter(unittest.TestCase):
    """Test in-memory adapter storage, retrieval, and patient isolation."""

    def setUp(self):
        self.config = HindsightConfig(enabled=True, use_in_memory_fallback=True)
        self.manager = HindsightMemoryManager(config=self.config)

    def test_store_and_retrieve_single_patient(self):
        success = self.manager.store_encounter_summary(
            patient_id="P_ALICE",
            session_id="S_001",
            summary_text="Patient has history of type 2 diabetes managed with metformin."
        )
        self.assertTrue(success)

        ctx = self.manager.retrieve_historical_context("P_ALICE", "diabetes")
        self.assertIsNotNone(ctx)
        self.assertIn("type 2 diabetes", ctx)

    def test_patient_isolation(self):
        """Ensure Patient A and Patient B data are strictly isolated."""
        self.manager.store_encounter_summary(
            patient_id="PATIENT_A",
            session_id="S_A1",
            summary_text="Patient A has chronic asthma."
        )

        self.manager.store_encounter_summary(
            patient_id="PATIENT_B",
            session_id="S_B1",
            summary_text="Patient B has hypertension."
        )

        ctx_a = self.manager.retrieve_historical_context("PATIENT_A", "asthma")
        ctx_b = self.manager.retrieve_historical_context("PATIENT_B", "hypertension")

        # Patient A should see asthma, not hypertension
        self.assertIn("asthma", ctx_a)
        self.assertNotIn("hypertension", ctx_a)

        # Patient B should see hypertension, not asthma
        self.assertIn("hypertension", ctx_b)
        self.assertNotIn("asthma", ctx_b)

        # Querying Patient B for unrelated symptoms never leaks Patient A data
        ctx_b_other = self.manager.retrieve_historical_context("PATIENT_B", "unrelated_symptom_xyz")
        if ctx_b_other:
            self.assertNotIn("asthma", ctx_b_other)
            self.assertNotIn("Patient A", ctx_b_other)


class TestHindsightNonMutationInvariant(unittest.TestCase):
    """
    CRITICAL INVARIANT TEST:
    Verifies that retrieving historical context from Hindsight NEVER mutates
    session-scoped ClinicalMemory or overwrites deterministic extractions.
    """

    def test_historical_memory_does_not_mutate_clinical_memory(self):
        # 1. Setup Hindsight with past medical history for patient "P_CAROL"
        config = HindsightConfig(enabled=True, use_in_memory_fallback=True)
        h_manager = HindsightMemoryManager(config=config)
        h_manager.store_encounter_summary(
            patient_id="P_CAROL",
            session_id="S_PREV",
            summary_text="Past record: Patient was treated for Hypertension in 2024."
        )

        # 2. Setup DialogueEngine with explicit ClinicalMemory and Hindsight
        session_memory = ClinicalMemory()
        engine = DialogueEngine(memory=session_memory, hindsight_manager=h_manager)
        state = engine.initialize()

        # 3. Patient utters: "I don't have any medical conditions" (Target: PAST_MEDICAL_HISTORY)
        state.missing_slots = [ClinicalSlot.PAST_MEDICAL_HISTORY]
        asr_output = ASROutput(
            text="I don't have any medical conditions",
            confidence=0.9,
            language="en"
        )

        # 4. Run turn
        response = engine.step(asr_output=asr_output, state=state, patient_id="P_CAROL")

        # 5. Verify ClinicalMemory: MUST be "none reported" from deterministic extraction, NOT hypertension
        pmh_entry = session_memory.get_slot(ClinicalSlot.PAST_MEDICAL_HISTORY)
        self.assertIsNotNone(pmh_entry)
        self.assertEqual(pmh_entry.value, "none reported")

        # 6. Verify DialogueState collected_info
        self.assertEqual(state.collected_info.get(ClinicalSlot.PAST_MEDICAL_HISTORY), "none reported")




class TestHindsightHTTPAdapterResilience(unittest.TestCase):
    """Test HTTP adapter resilience to network and API failures."""

    @patch("httpx.Client.get")
    @patch("httpx.Client.post")
    def test_http_adapter_handles_network_exceptions_gracefully(self, mock_post, mock_get):
        mock_get.side_effect = Exception("Connection refused / Network unreachable")
        mock_post.side_effect = Exception("Connection refused / Network unreachable")

        config = HindsightConfig(
            enabled=True,
            api_url="http://invalid.local/hindsight",
            api_key="test-key",
            use_in_memory_fallback=False
        )
        adapter = HindsightHTTPAdapter(config)

        # Querying during network error should return empty HindsightQueryResult safely
        result = adapter.retrieve_context("P999", "headache")
        self.assertIsInstance(result, HindsightQueryResult)
        self.assertEqual(len(result.records), 0)

        # Storing during network error should return False safely without crashing
        record = HindsightMemoryRecord(
            patient_id="P999",
            session_id="S999",
            content="Test summary"
        )
        stored = adapter.store_memory(record)
        self.assertFalse(stored)


if __name__ == "__main__":
    unittest.main()
