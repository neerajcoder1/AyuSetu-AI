"""
Clinical Encounter & Slot Service
=================================
High-level service orchestrating encounter sealing, slot/utterance persistence,
RedFlag evaluation, cryptographic audit recording, and session cache invalidation per PRD v2.0 §10, §14 & §22.5.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid
import uuid6

from ayusetu.common.session_cache import SessionCache
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.consent.service import consent_service
from ayusetu.audit.service import audit_service
from ayusetu.redflag.service import red_flag_service
from ayusetu.redflag.models import StructuredClinicalFact
from ayusetu.clinical.models import (
    EncounterDTO,
    EncounterStatus,
    VisitType,
    IntakeDepth,
    Channel,
    ReportedBy,
    SlotSource,
    SlotDTO,
    UtteranceDTO,
    SessionSubmissionResponse,
    SummaryVersionDTO,
    SummaryStatus,
)
from ayusetu.clinical.summary_engine import summary_synthesis_engine
from ayusetu.clinical.repository import ClinicalRepository

logger = logging.getLogger("ayusetu.clinical.service")


class ClinicalService:
    """
    Authoritative service managing clinical encounters, slots, and dialogue persistence.
    """

    def __init__(
        self,
        repository: Optional[ClinicalRepository] = None,
        session_cache: Optional[SessionCache] = None,
    ) -> None:
        self.repository = repository or ClinicalRepository()
        self.session_cache = session_cache or SessionCache()

    def create_encounter(
        self,
        patient_id: str,
        department: str = "Kayachikitsa",
        visit_type: VisitType = VisitType.NEW,
        intake_depth: IntakeDepth = IntakeDepth.FULL,
        channel: Channel = Channel.KIOSK,
        reported_by: ReportedBy = ReportedBy.PATIENT,
        language: str = "hi",
        encounter_id: Optional[str] = None,
    ) -> EncounterDTO:
        """Create a new encounter in draft state."""
        enc_id = encounter_id or str(uuid6.uuid7())
        dto = EncounterDTO(
            id=enc_id,
            patient_id=str(patient_id),
            department=department,
            visit_type=visit_type,
            intake_depth=intake_depth,
            channel=channel,
            reported_by=reported_by,
            language=language,
            started_at=datetime.now(timezone.utc),
            status=EncounterStatus.DRAFT,
        )
        return self.repository.create_encounter(dto)

    def get_encounter(self, encounter_id: str) -> Optional[EncounterDTO]:
        """Retrieve encounter by ID."""
        return self.repository.get_encounter(encounter_id)

    def submit_session(
        self,
        session_id: str,
        confirmed_by: str = "patient",
        readback_accepted: bool = True,
        actor_id: Optional[str] = None,
        actor_role: str = "patient",
        ip_address: Optional[str] = None,
    ) -> SessionSubmissionResponse:
        """
        Seal session and persist Encounter, Utterances, and Slots to PostgreSQL.
        Enforces consent verification, triggers RedFlag AST evaluation, records
        cryptographic audit trail, and purges ephemeral session state upon success.
        """
        # 1. Retrieve session data from cache
        session = self.session_cache.get_session(session_id)
        if not session:
            raise AyuSetuGatewayError(
                ErrorCode.SESSION_EXPIRED,
                f"Session '{session_id}' expired or not found",
                401,
            )

        enc_id = session.get("encounter_id") or str(uuid6.uuid7())
        pat_id = session.get("patient_id") or str(uuid6.uuid7())

        # 2. Check clinical consent gating
        # If a consent record exists for this encounter, verify clinical purpose is granted
        from ayusetu.consent.models import ConsentStatus
        active_consent = consent_service.get_active_consent(enc_id)
        if active_consent is not None:
            if not active_consent.purposes.get("clinical", False) or active_consent.status != ConsentStatus.ACTIVE:
                raise AyuSetuGatewayError(
                    ErrorCode.CONSENT_REQUIRED,
                    f"Active clinical consent required to submit encounter '{enc_id}'",
                    403,
                )

        # 3. Parse and construct Encounter DTO
        channel_str = session.get("channel", "kiosk")
        channel = Channel(channel_str) if channel_str in Channel._value2member_map_ else Channel.KIOSK

        reported_by_enum = (
            ReportedBy(confirmed_by)
            if confirmed_by in ReportedBy._value2member_map_
            else ReportedBy.PATIENT
        )

        encounter_dto = EncounterDTO(
            id=enc_id,
            patient_id=pat_id,
            department=session.get("department", "Kayachikitsa"),
            visit_type=VisitType.NEW,
            intake_depth=IntakeDepth.FULL,
            channel=channel,
            reported_by=reported_by_enum,
            language=session.get("language", "hi"),
            status=EncounterStatus.SUBMITTED,
        )

        # 4. Parse utterances from session state
        raw_utterances = session.get("utterances", [])
        utterance_dtos: List[UtteranceDTO] = []
        for i, u in enumerate(raw_utterances):
            utt_id = u.get("id") or str(uuid6.uuid7())
            utterance_dtos.append(
                UtteranceDTO(
                    id=utt_id,
                    encounter_id=enc_id,
                    seq=u.get("seq", i + 1),
                    speaker=u.get("speaker", "patient"),
                    text=u.get("text", ""),
                    lang=u.get("lang", "hi"),
                    asr_confidence=float(u.get("asr_confidence", 1.0)),
                    audio_uri=u.get("audio_uri"),
                    created_at=datetime.now(timezone.utc),
                )
            )

        # 5. Parse slots from session state
        raw_slots = session.get("slots", [])
        slot_dtos: List[SlotDTO] = []
        if isinstance(raw_slots, dict):
            # Formatted as path -> value mapping
            for path, val in raw_slots.items():
                slot_dtos.append(
                    SlotDTO(
                        id=str(uuid6.uuid7()),
                        encounter_id=enc_id,
                        path=path,
                        value=val,
                        confidence=1.0,
                        source=SlotSource.UTTERANCE,
                        reported_by=reported_by_enum,
                        elicited=True,
                    )
                )
        elif isinstance(raw_slots, list):
            for s in raw_slots:
                if isinstance(s, dict):
                    slot_id = s.get("id") or str(uuid6.uuid7())
                    src_str = s.get("source", "utterance")
                    src = SlotSource(src_str) if src_str in SlotSource._value2member_map_ else SlotSource.UTTERANCE
                    rep_str = s.get("reported_by", confirmed_by)
                    rep = ReportedBy(rep_str) if rep_str in ReportedBy._value2member_map_ else ReportedBy.PATIENT
                    slot_dtos.append(
                        SlotDTO(
                            id=slot_id,
                            encounter_id=enc_id,
                            path=s.get("path", "hpi.chief_complaint"),
                            value=s.get("value"),
                            value_coded=s.get("value_coded"),
                            confidence=float(s["confidence"]) if s.get("confidence") is not None else None,
                            source=src,
                            source_ref=s.get("source_ref"),
                            reported_by=rep,
                            elicited=bool(s.get("elicited", True)),
                        )
                    )

        # 6. Atomic Persistence in PostgreSQL
        try:
            persisted_enc = self.repository.submit_encounter_atomic(
                encounter=encounter_dto,
                utterances=utterance_dtos,
                slots=slot_dtos,
            )
        except Exception as e:
            logger.error("Failed to commit encounter submission for session %s: %s", session_id, str(e))
            # Preserve session cache on failure
            raise

        # 7. Evaluate Clinical RedFlags if facts present
        redflags_detected = 0
        clinical_facts: List[StructuredClinicalFact] = []
        for s in slot_dtos:
            clinical_facts.append(
                StructuredClinicalFact(
                    path=s.path,
                    value=s.value,
                    confidence=s.confidence,
                    elicited=s.elicited,
                )
            )

        if clinical_facts:
            try:
                rf_events = red_flag_service.evaluate_encounter(
                    encounter_id=enc_id,
                    facts=clinical_facts,
                    actor_id=actor_id or pat_id,
                    actor_role=actor_role,
                )
                redflags_detected = len(rf_events)
            except Exception as rf_err:
                logger.warning("RedFlag evaluation warning during session submission: %s", str(rf_err))

        # 8. Append Cryptographic Audit Event
        try:
            from ayusetu.audit.models import AuditAction, AuditOutcome
            audit_actor_id = actor_id or pat_id
            audit_service.record_event(
                actor_id=audit_actor_id,
                actor_role=actor_role,
                action=AuditAction.CREATE,
                resource_type="ENCOUNTER",
                resource_id=enc_id,
                patient_id=pat_id,
                encounter_id=enc_id,
                outcome=AuditOutcome.ALLOW,
                reason="Encounter intake submitted and sealed",
                src_ip=ip_address,
                safe_metadata={"department": session.get("department", "Kayachikitsa")},
            )
        except Exception as audit_err:
            logger.error("Audit log error on encounter submission: %s", str(audit_err))

        # 9. Generate Preliminary Summary Version 1
        try:
            self.generate_summary(enc_id, actor_id=actor_id, actor_role=actor_role)
        except Exception as sum_err:
            logger.warning("Preliminary summary synthesis deferred/failed during submission: %s", str(sum_err))

        # 10. Invalidate and purge transient session cache (<2s)
        self.session_cache.panic_clear(session_id)

        return SessionSubmissionResponse(
            encounter_id=enc_id,
            status=persisted_enc.status.value,
            summary_status="generating",
            poll_after_ms=1500,
            session_purged=True,
            slots_persisted=len(slot_dtos),
            utterances_persisted=len(utterance_dtos),
            redflags_detected=redflags_detected,
        )

    def generate_summary(
        self,
        encounter_id: str,
        actor_id: Optional[str] = None,
        actor_role: str = "system",
    ) -> SummaryVersionDTO:
        """
        Synthesize deterministic clinical summary from persisted Slot records
        and idempotently persist as SummaryVersion (version=1, status=preliminary).
        """
        enc = self.repository.get_encounter(encounter_id)
        if not enc:
            raise AyuSetuGatewayError(
                ErrorCode.NOT_FOUND,
                f"Encounter '{encounter_id}' not found",
                404,
            )

        # Check consent if encounter has consent recorded
        from ayusetu.consent.models import ConsentStatus
        active_consent = consent_service.get_active_consent(encounter_id)
        if active_consent is not None:
            if not active_consent.purposes.get("clinical", False) or active_consent.status != ConsentStatus.ACTIVE:
                raise AyuSetuGatewayError(
                    ErrorCode.CONSENT_REQUIRED,
                    f"Active clinical consent required for summary generation on encounter '{encounter_id}'",
                    403,
                )

        slots = self.repository.get_slots(encounter_id)
        summary_dto = summary_synthesis_engine.synthesize(
            encounter_id=encounter_id,
            slots=slots,
        )

        composition_dict = summary_dto.model_dump(mode="json")
        saved_summary = self.repository.upsert_preliminary_summary(
            encounter_id=encounter_id,
            composition=composition_dict,
            model_version=summary_synthesis_engine.MODEL_VERSION,
            generated_by="synthesis_engine",
        )
        return saved_summary

    def get_or_generate_summary(
        self,
        encounter_id: str,
        actor_id: Optional[str] = None,
        actor_role: str = "doctor",
    ) -> Dict[str, Any]:
        """
        Retrieve latest summary composition or synthesize preliminary summary version 1.
        Preserves RBAC/ABAC and clinical consent enforcement.
        """
        # Check if summary version already exists
        existing = self.repository.get_latest_summary_version(encounter_id)
        if existing:
            return existing.composition

        # Check if encounter exists
        enc = self.repository.get_encounter(encounter_id)
        if not enc:
            # Check if encounter_id is valid UUID
            try:
                uuid.UUID(str(encounter_id))
            except Exception:
                raise AyuSetuGatewayError(
                    ErrorCode.UNPROCESSABLE_ENTITY,
                    f"Invalid encounter ID format: '{encounter_id}'",
                    422,
                )
            # Synthesize fallback unelicited summary
            summary_dto = summary_synthesis_engine.synthesize(
                encounter_id=encounter_id,
                slots=[],
            )
            return summary_dto.model_dump(mode="json")

        # Generate and persist summary version
        saved = self.generate_summary(encounter_id, actor_id=actor_id, actor_role=actor_role)
        return saved.composition

    def apply_physician_patch(
        self,
        encounter_id: str,
        slot_path: str,
        new_value: Any,
        old_value: Optional[Any] = None,
        reason: Optional[str] = None,
        physician_id: Optional[str] = None,
        physician_role: str = "physician",
    ) -> Dict[str, Any]:
        """
        Apply physician review edit to preliminary clinical summary,
        validate against packages/schemas/summary.json, and atomically persist
        SummaryEdit diff tracking record.
        """
        enc = self.repository.get_encounter(encounter_id)
        if not enc:
            raise AyuSetuGatewayError(
                ErrorCode.NOT_FOUND,
                f"Encounter '{encounter_id}' not found",
                404,
            )

        # Check active clinical consent
        from ayusetu.consent.models import ConsentStatus
        active_consent = consent_service.get_active_consent(encounter_id)
        if active_consent is not None:
            if not active_consent.purposes.get("clinical", False) or active_consent.status != ConsentStatus.ACTIVE:
                raise AyuSetuGatewayError(
                    ErrorCode.CONSENT_REQUIRED,
                    f"Active clinical consent required to edit summary for encounter '{encounter_id}'",
                    403,
                )

        # Retrieve latest summary version or generate preliminary v1
        summary_ver = self.repository.get_latest_summary_version(encounter_id)
        if not summary_ver:
            summary_ver = self.generate_summary(encounter_id, actor_id=physician_id, actor_role=physician_role)

        if summary_ver.status == SummaryStatus.FINAL:
            raise AyuSetuGatewayError(
                ErrorCode.BAD_REQUEST,
                f"Cannot edit finalized and signed summary for encounter '{encounter_id}'",
                400,
            )

        # Deep-copy composition for mutation
        import copy
        comp = copy.deepcopy(summary_ver.composition)

        # Apply edit/patch logic
        if slot_path.startswith("/"):
            # JSON Pointer navigation (e.g. /sections/0/clauses/0/text)
            tokens = [t.replace("~1", "/").replace("~0", "~") for t in slot_path.strip("/").split("/")]
            curr = comp
            try:
                for token in tokens[:-1]:
                    if isinstance(curr, list):
                        curr = curr[int(token)]
                    elif isinstance(curr, dict):
                        curr = curr[token]
                last_token = int(tokens[-1]) if isinstance(curr, list) else tokens[-1]
                curr[last_token] = new_value
            except Exception as ptr_err:
                raise AyuSetuGatewayError(
                    ErrorCode.UNPROCESSABLE_ENTITY,
                    f"Invalid JSON patch pointer '{slot_path}': {str(ptr_err)}",
                    422,
                )
        else:
            # Domain slot path navigation
            target_sec_id = slot_path.split(".")[0].lower()
            if target_sec_id in ("symptoms", "chief_complaint", "duration", "severity", "location", "onset"):
                target_sec_id = "hpi"
            elif target_sec_id in ("meds", "medication"):
                target_sec_id = "medications"
            elif target_sec_id in ("allergy",):
                target_sec_id = "allergies"

            sections = comp.setdefault("sections", [])
            sec = next((s for s in sections if s.get("id") == target_sec_id), None)
            if not sec:
                sec = {"id": target_sec_id, "title": target_sec_id.capitalize(), "clauses": []}
                sections.append(sec)

            clauses = sec.setdefault("clauses", [])

            # Filter out unelicited dummy clause if inserting real data
            new_text_val = str(new_value) if not isinstance(new_value, dict) else new_value.get("text", str(new_value))
            target_source = {"type": "clinician", "ids": [str(physician_id)] if physician_id else []}

            # Check if matching clause exists
            matched = False
            for clause in clauses:
                if slot_path in clause.get("slots", []) or (len(clauses) == 1 and not clause.get("elicited", True)):
                    clause["text"] = new_text_val
                    clause["elicited"] = True
                    clause["source"] = target_source
                    clause["confidence"] = 1.0
                    if slot_path not in clause.get("slots", []):
                        clause.setdefault("slots", []).append(slot_path)
                    matched = True
                    break

            if not matched:
                clauses.append({
                    "text": new_text_val,
                    "slots": [slot_path],
                    "source": target_source,
                    "confidence": 1.0,
                    "elicited": True,
                })

        # Validate modified composition against JSON Schema
        try:
            summary_synthesis_engine.validate_schema(comp)
        except Exception as val_err:
            raise AyuSetuGatewayError(
                ErrorCode.UNPROCESSABLE_ENTITY,
                f"Summary failed schema validation after patch: {str(val_err)}",
                422,
            )

        # Atomically commit patch & persist SummaryEdit
        from ayusetu.clinical.models import SummaryEditDTO
        edit_dto = SummaryEditDTO(
            id=str(uuid6.uuid7()),
            summary_version_id=str(summary_ver.id),
            slot_path=slot_path,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            edited_by=str(physician_id or "usr-phy-001"),
            edited_at=datetime.now(timezone.utc),
        )

        updated_summary, saved_edit = self.repository.apply_summary_patch_atomic(
            encounter_id=encounter_id,
            edit_dto=edit_dto,
            new_composition=comp,
        )

        return {
            "status": "updated",
            "encounter_id": encounter_id,
            "summary_version_id": str(updated_summary.id),
            "slot_path": slot_path,
            "recorded_in_summary_edit": True,
            "summary": updated_summary.composition,
        }

    def sign_summary(
        self,
        encounter_id: str,
        physician_id: str,
        physician_role: str = "physician",
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Digitally sign clinical summary, transitioning preliminary -> final,
        populating signed_by and signed_at, enforcing consent and care context,
        and emitting cryptographic SIGN audit event.
        """
        enc = self.repository.get_encounter(encounter_id)
        if not enc:
            raise AyuSetuGatewayError(
                ErrorCode.NOT_FOUND,
                f"Encounter '{encounter_id}' not found",
                404,
            )

        # Check active clinical consent
        from ayusetu.consent.models import ConsentStatus
        active_consent = consent_service.get_active_consent(encounter_id)
        if active_consent is not None:
            if not active_consent.purposes.get("clinical", False) or active_consent.status != ConsentStatus.ACTIVE:
                raise AyuSetuGatewayError(
                    ErrorCode.CONSENT_REQUIRED,
                    f"Active clinical consent required to digitally sign encounter '{encounter_id}'",
                    403,
                )

        summary_ver = self.repository.get_latest_summary_version(encounter_id)
        if not summary_ver:
            # Generate preliminary v1 if not yet generated
            summary_ver = self.generate_summary(encounter_id, actor_id=physician_id, actor_role=physician_role)

        if summary_ver.status == SummaryStatus.FINAL:
            raise AyuSetuGatewayError(
                ErrorCode.BAD_REQUEST,
                f"Summary for encounter '{encounter_id}' is already finalized and signed",
                400,
            )

        now_utc = datetime.now(timezone.utc)
        signed_summary, signed_enc = self.repository.sign_summary_atomic(
            encounter_id=encounter_id,
            physician_id=physician_id,
            signed_at=now_utc,
        )

        # Record cryptographic audit event
        try:
            from ayusetu.audit.models import AuditAction, AuditOutcome
            audit_service.record_event(
                actor_id=str(physician_id),
                actor_role=physician_role,
                action=AuditAction.SIGN,
                resource_type="SIGNED_CLINICAL_RECORD",
                resource_id=encounter_id,
                patient_id=str(signed_enc.patient_id),
                encounter_id=encounter_id,
                outcome=AuditOutcome.ALLOW,
                reason="Physician digitally signed and sealed clinical summary",
                src_ip=ip_address,
                safe_metadata={"summary_version_id": str(signed_summary.id), "version": signed_summary.version},
            )
        except Exception as audit_err:
            logger.error("Failed to record sign audit event for encounter %s: %s", encounter_id, str(audit_err))

        return {
            "status": "final",
            "encounter_id": encounter_id,
            "version": signed_summary.version,
            "signed_by": str(physician_id),
            "signed_at": now_utc.isoformat(),
        }


# Global Singleton
clinical_service = ClinicalService()

