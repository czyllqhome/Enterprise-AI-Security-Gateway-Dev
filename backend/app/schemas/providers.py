from datetime import datetime

from pydantic import BaseModel, Field


class ProviderCredentialUpsertRequest(BaseModel):
    provider: str
    api_key: str = ""
    base_url: str | None = None
    default_model: str | None = None
    models: list[str] | None = None


class ProviderCredentialResponse(BaseModel):
    provider: str
    display_name: str
    configured: bool
    requires_api_key: bool
    masked_api_key: str | None
    base_url: str
    default_model: str
    models: list[str]
    updated_at: datetime | None = None


class ProviderCatalogResponse(BaseModel):
    providers: list[ProviderCredentialResponse]
