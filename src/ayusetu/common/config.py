"""
AyuSetu Backend Configuration
=============================
Authoritative environment configuration per PRD v2.0 §22.9.
"""

from typing import Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    # --- Core Environment ---
    AYUSETU_ENV: str = Field(default="dev", description="Environment: dev | pilot | prod")
    DEBUG: bool = Field(default=False)
    
    # --- Database & Storage ---
    DATABASE_URL: str = Field(
        default="postgresql+psycopg2://ayusetu:ayusetu_dev_secret@localhost:5432/ayusetu_db",
        description="Sync / Primary database connection URL"
    )
    ASYNC_DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Optional Async database connection URL (e.g. postgresql+asyncpg://...)"
    )
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for ephemeral session state"
    )
    OBJECT_STORE_ENDPOINT: str = Field(default="http://localhost:9000", description="MinIO/S3 endpoint")
    KMS_ENDPOINT: Optional[str] = Field(default=None, description="KMS / Vault endpoint")

    # --- Clinical Behavior (Tunable without a deploy per PRD §22.9) ---
    SESSION_TTL_MINUTES: int = Field(default=30, description="Session TTL in minutes (authority in Redis)")
    QUESTION_BUDGET: int = Field(default=40, description="Max questions per intake")
    INTERVIEW_BUDGET_SECONDS: int = Field(default=480, description="Hard stop at 8 minutes")
    ASR_CONFIDENCE_FLOOR: float = Field(default=0.65, description="Confidence floor before closed re-ask")
    OCR_CONFIDENCE_AMBER: float = Field(default=0.80, description="Confidence floor for verified OCR text")
    STUCK_DETECT_SECONDS: int = Field(default=45, description="Attendant dispatch trigger for stuck station")
    TIER1_ESCALATE_SECONDS: int = Field(default=90, description="Nursing officer alert timer")
    TIER1_ESCALATE2_SECONDS: int = Field(default=180, description="Duty medical officer alert timer")
    COMPANION_LINK_TTL_MINUTES: int = Field(default=60, description="Companion magic link expiration")

    # --- Models & Fallbacks ---
    ASR_MODEL: str = Field(default="indicconformer-v2")
    ASR_FALLBACK: str = Field(default="bhashini")
    LLM_MODEL: str = Field(default="local")
    LLM_MAX_TOKENS: int = Field(default=1024)
    MODEL_SIGNING_PUBKEY: Optional[str] = None

    # --- Integrations ---
    ABDM_BASE_URL: Optional[str] = None
    ABDM_CLIENT_ID: Optional[str] = None
    ABDM_MODE: str = Field(default="mock", description="sandbox | prod | mock")
    HIS_ADAPTER: str = Field(default="none", description="fhir | hl7v2 | none")

    # --- Gateway & Networking ---
    GATEWAY_HOST: str = Field(default="0.0.0.0", description="Gateway bind host")
    GATEWAY_PORT: int = Field(default=8080, description="Gateway port per PRD §22.2")
    CORS_ALLOWED_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
        description="Strict CORS allowed origins"
    )

    # --- Request Size Limits (PRD §21.6) ---
    MAX_UPLOAD_BODY_BYTES: int = Field(default=25 * 1024 * 1024, description="25 MB for document uploads")
    MAX_JSON_BODY_BYTES: int = Field(default=256 * 1024, description="256 KB for JSON payloads")

    # --- Rate Limiting (PRD §21.6) ---
    RATE_LIMIT_DEVICE_RPM: int = Field(default=60, description="Per device sustained requests/min")
    RATE_LIMIT_DEVICE_BURST: int = Field(default=120, description="Per device burst limit")
    RATE_LIMIT_SESSION_TOTAL: int = Field(default=300, description="Per session total requests")
    RATE_LIMIT_PWA_RPM: int = Field(default=30, description="Per IP on public PWA requests/min")
    RATE_LIMIT_DOC_UPLOAD_TOTAL: int = Field(default=20, description="Document uploads per session")

    # --- Service Catalogue (PRD §22.2) ---
    SERVICE_DIALOGUE_URL: str = Field(default="http://localhost:8101")
    SERVICE_SPEECH_URL: str = Field(default="http://localhost:8102")
    SERVICE_DOCPIPE_URL: str = Field(default="http://localhost:8103")
    SERVICE_SUMMARY_URL: str = Field(default="http://localhost:8104")
    SERVICE_REDFLAG_URL: str = Field(default="http://localhost:8105")
    SERVICE_TERMINOLOGY_URL: str = Field(default="http://localhost:8106")
    SERVICE_MPI_URL: str = Field(default="http://localhost:8107")
    SERVICE_CONSENT_URL: str = Field(default="http://localhost:8108")
    SERVICE_AUDIT_URL: str = Field(default="http://localhost:8109")
    SERVICE_DEID_URL: str = Field(default="http://localhost:8110")

    # --- Security & Network ---
    MTLS_CA_BUNDLE: Optional[str] = None
    REQUEST_SIGNING_PUBKEYS: Optional[str] = None
    EGRESS_ALLOWLIST: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":

        """Enforce strict fail-closed security requirements in production environment."""
        if self.AYUSETU_ENV == "prod":
            if self.DEBUG:
                raise ValueError("DEBUG mode must be False in production (AYUSETU_ENV=prod)")
            if "ayusetu_dev_secret" in self.DATABASE_URL:
                raise ValueError("Default development database password 'ayusetu_dev_secret' is forbidden in production")
            if any("*" in origin for origin in self.CORS_ALLOWED_ORIGINS):
                raise ValueError("Wildcard CORS origins are forbidden in production")
        return self

    @property
    def async_db_url(self) -> str:
        if self.ASYNC_DATABASE_URL:
            return self.ASYNC_DATABASE_URL
        if self.DATABASE_URL.startswith("postgresql+psycopg2://"):
            return self.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        elif self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
        elif self.DATABASE_URL.startswith("sqlite://"):
            return self.DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://")
        return self.DATABASE_URL


settings = Settings()

