from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.provider_catalog import ProviderDefinition, get_provider_catalog
from ..models.provider_credential import ProviderCredential
from ..schemas.providers import ProviderCredentialResponse, ProviderCredentialUpsertRequest


class ProviderCredentialNotFoundError(Exception):
    pass


class UnsupportedProviderError(Exception):
    pass


class ProviderCredentialService:
    def __init__(self, db: Session):
        self.db = db
        self.catalog = get_provider_catalog()

    def list_providers(self) -> list[ProviderCredentialResponse]:
        stored = {
            item.provider: item
            for item in self.db.scalars(select(ProviderCredential).order_by(ProviderCredential.provider)).all()
        }
        providers: list[ProviderCredentialResponse] = []

        for provider_name, definition in self.catalog.items():
            credential = stored.get(provider_name)
            providers.append(self._build_response(definition, credential))

        return providers

    def get_provider(self, provider: str) -> ProviderCredentialResponse:
        definition = self._get_definition(provider)
        credential = self._get_credential_record(provider)
        return self._build_response(definition, credential)

    def get_credential_record(self, provider: str) -> ProviderCredential | None:
        self._get_definition(provider)
        return self._get_credential_record(provider)

    def require_credential(self, provider: str) -> ProviderCredential:
        definition = self._get_definition(provider)
        if not definition.requires_api_key:
            credential = self.get_credential_record(provider)
            if credential is not None:
                return credential
            return ProviderCredential(
                provider=definition.provider,
                display_name=definition.display_name,
                api_key="",
                base_url=definition.default_base_url,
                default_model=definition.default_models[0],
                models_json=list(definition.default_models),
            )
        credential = self.get_credential_record(provider)
        if credential is None:
            raise ProviderCredentialNotFoundError(f"No API key is configured for provider '{provider}'.")
        return credential

    def upsert_provider(self, payload: ProviderCredentialUpsertRequest) -> ProviderCredentialResponse:
        definition = self._get_definition(payload.provider)
        normalized_models = self._normalize_models(payload.models, definition)
        default_model = (payload.default_model or "").strip() or normalized_models[0]
        base_url = (payload.base_url or "").strip() or definition.default_base_url

        credential = self._get_credential_record(definition.provider)
        if credential is None:
            credential = ProviderCredential(
                provider=definition.provider,
                display_name=definition.display_name,
                api_key=payload.api_key.strip(),
                base_url=base_url,
                default_model=default_model,
                models_json=normalized_models,
            )
            self.db.add(credential)
        else:
            credential.display_name = definition.display_name
            credential.api_key = payload.api_key.strip()
            credential.base_url = base_url
            credential.default_model = default_model
            credential.models_json = normalized_models

        self.db.commit()
        self.db.refresh(credential)
        return self._build_response(definition, credential)

    def delete_provider(self, provider: str) -> None:
        self._get_definition(provider)
        credential = self._get_credential_record(provider)
        if credential is None:
            raise ProviderCredentialNotFoundError(f"No saved API key was found for provider '{provider}'.")
        self.db.delete(credential)
        self.db.commit()

    def _build_response(
        self,
        definition: ProviderDefinition,
        credential: ProviderCredential | None,
    ) -> ProviderCredentialResponse:
        if credential is None:
            return ProviderCredentialResponse(
                provider=definition.provider,
                display_name=definition.display_name,
                configured=not definition.requires_api_key,
                requires_api_key=definition.requires_api_key,
                masked_api_key=None,
                base_url=definition.default_base_url,
                default_model=definition.default_models[0],
                models=list(definition.default_models),
                updated_at=None,
            )

        models = self._normalize_models(credential.models_json, definition)
        default_model = credential.default_model if credential.default_model in models else models[0]
        return ProviderCredentialResponse(
            provider=credential.provider,
            display_name=definition.display_name,
            configured=bool(credential.api_key) or not definition.requires_api_key,
            requires_api_key=definition.requires_api_key,
            masked_api_key=self._mask_api_key(credential.api_key) if credential.api_key else None,
            base_url=credential.base_url,
            default_model=default_model,
            models=models,
            updated_at=credential.updated_at,
        )

    def _normalize_models(self, models: list[str] | None, definition: ProviderDefinition) -> list[str]:
        normalized = [(item or "").strip() for item in (models or [])]
        normalized = [item for item in normalized if item]
        return normalized or list(definition.default_models)

    def _get_credential_record(self, provider: str) -> ProviderCredential | None:
        stmt = select(ProviderCredential).where(ProviderCredential.provider == provider.lower())
        return self.db.scalar(stmt)

    def _get_definition(self, provider: str) -> ProviderDefinition:
        normalized = provider.lower().strip()
        definition = self.catalog.get(normalized)
        if definition is None:
            raise UnsupportedProviderError(f"Unsupported provider: {provider}")
        return definition

    def _mask_api_key(self, api_key: str) -> str:
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return f"{api_key[:4]}{'*' * max(4, len(api_key) - 8)}{api_key[-4:]}"
