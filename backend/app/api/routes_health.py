from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..services.guardrails.llm_guard_service import get_guardrail_service
from ..services.system_setting_service import SystemSettingService


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)) -> dict[str, Any]:
    setting_service = SystemSettingService(db)
    enabled_scanners = setting_service.get_enabled_scanners()
    readiness = get_guardrail_service().get_readiness(
        enabled_scanners,
        db=db,
        strict_mode=setting_service.get_scanner_strict_mode(),
    )
    if not readiness["ready"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=readiness,
            headers={"Retry-After": "5"},
        )
    return {"status": "ready", **readiness}
