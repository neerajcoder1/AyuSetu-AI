import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List

def transcribe(audio_path: Path | str):
    """
    Lazy wrapper around the real ASR transcribe function.

    Keeps `voice_pipeline.transcribe` patchable by tests.
    """
    from ayusetu.ai.voice.asr import transcriber
    return transcriber.transcribe(audio_path)

from ayusetu.ai.conversation.engine import DialogueEngine, DialogueState
from ayusetu.ai.voice.tts.chatterbox import ChatterboxTTS
from ayusetu.ai.clinical.red_flags.engine import RedFlagEngine
from ayusetu.ai.clinical.red_flags.contracts import RedFlagEvent
from ayusetu.ai.clinical.document_ai.contracts import ExtractedEntity
from ayusetu.ai.clinical.summary.contracts import ClinicalSummary

# Session abstractions

@dataclass
class ConversationSession:
    """Container for a dialogue session.

    Attributes
    ----------
    session_id: str
        Unique identifier generated via ``uuid4``.
    state: DialogueState
        The mutable state owned by ``DialogueEngine``.
    engine: DialogueEngine
        Session-scoped engine that owns this session's ``ClinicalMemory``.
        Each session has its own engine instance so clinical data
        can never leak between patients.
    document_entities: List[ExtractedEntity]
        Session-scoped document entities extracted via Document AI.
    red_flag_events: List[RedFlagEvent]
        Session-scoped red flag events detected during conversation.
    summary: Optional[ClinicalSummary]
        Session-scoped clinical summary.
    """
    session_id: str
    state: DialogueState
    engine: DialogueEngine
    document_entities: List[ExtractedEntity] = field(default_factory=list)
    red_flag_events: List[RedFlagEvent] = field(default_factory=list)
    summary: Optional[ClinicalSummary] = None


class SessionManager:
    """In‑memory manager for conversation sessions.

    Not a global singleton; a ``VoicePipeline`` instance receives an
    instance via dependency injection. Sessions are stored in a simple
    dict keyed by their UUID4 string.
    """

    def __init__(self, dialogue_engine: Optional[DialogueEngine] = None):
        self._dialogue_engine = dialogue_engine
        self._sessions: Dict[str, ConversationSession] = {}

    def create_session(self, preferred_language: str = "hinglish") -> ConversationSession:
        """Create a new session with a fresh ``DialogueEngine`` and ``DialogueState``.

        Returns
        -------
        ConversationSession
            The newly created session containing its ID, state, and engine.
        """
        session_id = str(uuid.uuid4())
        if self._dialogue_engine is not None:
            try:
                engine = type(self._dialogue_engine)(
                    extractor=getattr(self._dialogue_engine, "extractor", None),
                    llm_provider=getattr(getattr(self._dialogue_engine, "wording_llm", None), "provider", None),
                    asr_confidence_threshold=getattr(getattr(self._dialogue_engine, "planner", None), "asr_confidence_threshold", 0.6),
                    extraction_confidence_threshold=getattr(getattr(self._dialogue_engine, "planner", None), "extraction_confidence_threshold", 0.7),
                )
            except TypeError:
                engine = type(self._dialogue_engine)()
        else:
            engine = DialogueEngine()

        state = engine.initialize()
        if isinstance(state, dict):
            state["preferred_language"] = preferred_language or "hinglish"
        else:
            setattr(state, "preferred_language", preferred_language or "hinglish")
        session = ConversationSession(session_id=session_id, state=state, engine=engine)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> ConversationSession:
        """Retrieve a session; raise ``KeyError`` if not found."""
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"Session ID {session_id!r} does not exist") from exc

    def end_session(self, session_id: str) -> None:
        """Discard a session and its state.

        Raises
        ------
        KeyError
            If the session ID is unknown.
        """
        if session_id not in self._sessions:
            raise KeyError(f"Session ID {session_id!r} does not exist")
        del self._sessions[session_id]

    def clear_all(self) -> None:
        """Remove all sessions – useful for tests."""
        self._sessions.clear()


logger = logging.getLogger(__name__)


class VoicePipeline:
    """Orchestrates the end‑to‑end voice interaction with optional session support.

    Public API:
        - create_session() -> str
        - get_state(session_id) -> DialogueState
        - get_session(session_id) -> ConversationSession
        - end_session(session_id) -> None
        - run(audio_path, session_id=None) -> Dict[str, Any]
    """

    def __init__(self, session_manager: Optional[SessionManager] = None):
        # Initialise reusable components once.
        self._dialogue_engine = DialogueEngine()
        self._tts_provider = ChatterboxTTS()
        self._red_flag_engine = RedFlagEngine()
        # Use provided SessionManager or instantiate a default one.
        self._session_manager = session_manager or SessionManager(self._dialogue_engine)

    # ---------------------------------------------------------------------
    # Session lifecycle helpers
    # ---------------------------------------------------------------------
    def create_session(self, preferred_language: str = "hinglish") -> str:
        """Create a new conversation session and return its ID."""
        session = self._session_manager.create_session(preferred_language=preferred_language)
        return session.session_id

    def get_state(self, session_id: str) -> DialogueState:
        """Retrieve the current DialogueState for a given session ID."""
        return self._session_manager.get_session(session_id).state

    def get_session(self, session_id: str) -> ConversationSession:
        """Retrieve the ConversationSession object for a given session ID."""
        return self._session_manager.get_session(session_id)

    def end_session(self, session_id: str) -> None:
        """Discard the session identified by ``session_id``."""
        self._session_manager.end_session(session_id)

    # ---------------------------------------------------------------------
    # Core pipeline execution
    # ---------------------------------------------------------------------
    def run(self, audio_path: Path | str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute the pipeline for a single audio turn.

        Parameters
        ----------
        audio_path: Path | str
            Path to an audio file.
        session_id: str | None, default=None
            If provided, the existing session's DialogueState is used.
            If ``None``, a temporary fresh state is created (no persistence).

        Returns
        -------
        dict
            Result containing transcription, ASR confidence, response, etc.
        """
        # Validate session early if supplied
        session: Optional[ConversationSession] = None
        if session_id is not None:
            # May raise KeyError if not found – this is the intended behavior
            session = self._session_manager.get_session(session_id)
            state = session.state
            engine = session.engine
        else:
            engine = self._dialogue_engine
            state = None  # will be created after ASR if needed

        # Import transcribe lazily so that test patches are effective
        asr_output = transcribe(audio_path)
        low_conf = asr_output.is_low_confidence()
        result: Dict[str, Any] = {
            "transcribed_text": asr_output.text,
            "detected_language": asr_output.language,
            "asr_confidence": asr_output.confidence,
            "low_confidence": low_conf,
            "response_text": None,
            "response_audio": None,
            "response_sample_rate": None,
            "response_duration": None,
            "session_id": session_id,
            "red_flags": [],
        }

        if low_conf:
            logger.info(
                "ASR confidence %.4f below threshold – skipping dialogue engine.",
                asr_output.confidence,
            )
            return result

        # If we do not already have a state (i.e., no session supplied), create a temporary one
        if state is None:
            state = engine.initialize()

        # 2️⃣ Dialogue Engine – mutates the provided state.
        response_text = engine.step(asr_output, state)
        result["response_text"] = response_text

        # Evaluate RedFlags on current turn context
        collected_info = state.get("collected_info", {}) if isinstance(state, dict) else getattr(state, "collected_info", {})
        context = {slot.value if hasattr(slot, "value") else str(slot): str(val) for slot, val in collected_info.items()}
        red_flags = self._red_flag_engine.evaluate(
            encounter_id=session_id or "ephemeral",
            context=context,
            utterance=asr_output.text,
        )
        if session is not None and red_flags:
            existing_ids = {rf.rule_id for rf in session.red_flag_events}
            for rf in red_flags:
                if rf.rule_id not in existing_ids:
                    session.red_flag_events.append(rf)
                    existing_ids.add(rf.rule_id)

        result["red_flags"] = [rf.model_dump(mode="json") for rf in red_flags]

        # 3️⃣ TTS synthesis in session preferred language if set, else detected language
        target_lang = getattr(state, "preferred_language", None) or asr_output.language
        if not target_lang or target_lang == "unknown":
            target_lang = "hinglish"
        tts_result = self._tts_provider.synthesize(text=response_text, language=target_lang)
        result.update(
            {
                "response_audio": tts_result.audio,
                "response_sample_rate": tts_result.sample_rate,
                "response_duration": tts_result.duration,
            }
        )
        return result

# End of file
