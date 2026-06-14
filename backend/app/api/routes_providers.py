from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.db import get_db
from ..schemas.providers import ProviderCatalogResponse, ProviderCredentialResponse, ProviderCredentialUpsertRequest
from ..services.provider_credential_service import (
    ProviderCredentialNotFoundError,
    ProviderCredentialService,
    UnsupportedProviderError,
)


router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=ProviderCatalogResponse)
def list_providers(db: Session = Depends(get_db)) -> ProviderCatalogResponse:
    return ProviderCatalogResponse(providers=ProviderCredentialService(db).list_providers())


@router.get("/{provider}", response_model=ProviderCredentialResponse)
def get_provider(provider: str, db: Session = Depends(get_db)) -> ProviderCredentialResponse:
    try:
        return ProviderCredentialService(db).get_provider(provider)
    except UnsupportedProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("", response_model=ProviderCredentialResponse, status_code=status.HTTP_201_CREATED)
def upsert_provider(
    payload: ProviderCredentialUpsertRequest,
    db: Session = Depends(get_db),
) -> ProviderCredentialResponse:
    try:
        return ProviderCredentialService(db).upsert_provider(payload)
    except UnsupportedProviderError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider: str, db: Session = Depends(get_db)) -> None:
    try:
        ProviderCredentialService(db).delete_provider(provider)
    except (ProviderCredentialNotFoundError, UnsupportedProviderError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
