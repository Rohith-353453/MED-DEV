from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    api_prefix: str = "/api"
    database_url: str = "sqlite+aiosqlite:///./healthcopilot.db"
    auto_create_schema: bool = True
    auth_mode: str = "mock"
    mock_user_sub: str = "local-demo-user"
    max_upload_mb: int = Field(default=10, ge=1, le=100)
    upload_dir: str = "./uploads"
    storage_provider: str = "local"
    azure_storage_account_url: str | None = None
    azure_storage_connection_string: str | None = None
    azure_storage_container: str = "medical-documents"
    queue_provider: str = "local"
    azure_storage_queue_account_url: str | None = None
    azure_storage_queue_name: str = "document-processing"
    queue_message_visibility_seconds: int = Field(default=3600, ge=60, le=604800)
    processing_lease_seconds: int = Field(default=3300, ge=60, le=604800)
    ocr_provider: str = "mock"
    azure_document_intelligence_endpoint: str | None = None
    azure_document_intelligence_key: str | None = None
    azure_document_intelligence_api_version: str = "2024-11-30"
    llm_provider: str = "mock"
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_extraction_deployment: str | None = None
    azure_openai_summary_deployment: str | None = None
    azure_openai_extraction_max_tokens: int = Field(default=4096, ge=256, le=16384)
    azure_openai_summary_max_tokens: int = Field(default=1500, ge=128, le=8000)
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_api_key: str | None = None
    entra_tenant_id: str | None = None
    entra_issuer: str | None = None
    entra_jwks_uri: str | None = None
    entra_api_audience: str | None = None
    entra_required_scope: str = "access_as_user"
    firebase_project_id: str | None = None
    frontend_origins: str = "http://localhost:5173"
    applicationinsights_connection_string: str | None = None
    max_document_pages: int = Field(default=2, ge=1, le=100)
    azure_document_intelligence_max_mb: int = Field(default=4, ge=1, le=100)

    @field_validator(
        "auth_mode",
        "storage_provider",
        "queue_provider",
        "ocr_provider",
        "llm_provider",
    )
    @classmethod
    def lowercase_provider(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]

    @property
    def extraction_deployment(self) -> str | None:
        return self.azure_openai_extraction_deployment or self.azure_openai_deployment

    @property
    def summary_deployment(self) -> str | None:
        return self.azure_openai_summary_deployment or self.azure_openai_deployment

    def validate_deployment_security(self) -> None:
        if self.auth_mode not in {"mock", "entra", "firebase"}:
            raise RuntimeError("AUTH_MODE must be 'mock', 'entra', or 'firebase'.")
        if self.storage_provider not in {"local", "azure"}:
            raise RuntimeError("STORAGE_PROVIDER must be either 'local' or 'azure'.")
        if self.queue_provider not in {"local", "azure"}:
            raise RuntimeError("QUEUE_PROVIDER must be either 'local' or 'azure'.")
        if self.processing_lease_seconds >= self.queue_message_visibility_seconds:
            raise RuntimeError(
                "PROCESSING_LEASE_SECONDS must be lower than QUEUE_MESSAGE_VISIBILITY_SECONDS."
            )
        if (
            self.ocr_provider not in {"mock", "azure"}
            or self.llm_provider not in {"mock", "azure"}
        ):
            raise RuntimeError("OCR_PROVIDER and LLM_PROVIDER must be either 'mock' or 'azure'.")
        if (
            self.app_env.lower() not in {"local", "development", "test"}
            and self.auth_mode == "mock"
        ):
            raise RuntimeError("Mock authentication is forbidden outside local/development/test.")
        if self.auth_mode == "entra" and not all(
            [self.entra_tenant_id, self.entra_issuer, self.entra_api_audience]
        ):
            raise RuntimeError(
                "Entra mode requires tenant ID, issuer, and API audience configuration."
            )
        if self.auth_mode == "firebase" and not self.firebase_project_id:
            raise RuntimeError("Firebase auth mode requires FIREBASE_PROJECT_ID.")
        if self.storage_provider == "azure" and not (
            self.azure_storage_connection_string or self.azure_storage_account_url
        ):
            raise RuntimeError(
                "Azure Blob Storage requires a connection string or account URL."
            )
        if self.queue_provider == "azure" and not (
            self.azure_storage_connection_string or self.azure_storage_queue_account_url
        ):
            raise RuntimeError("Azure Queue Storage requires a connection string or account URL.")
        if self.ocr_provider == "azure" and not self.azure_document_intelligence_endpoint:
            raise RuntimeError("Azure OCR requires AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT.")
        if self.llm_provider == "azure" and not all(
            [self.azure_openai_endpoint, self.extraction_deployment, self.summary_deployment]
        ):
            raise RuntimeError(
                "Azure OpenAI requires AZURE_OPENAI_ENDPOINT and either a shared deployment "
                "(AZURE_OPENAI_DEPLOYMENT) or both task-specific deployments."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
