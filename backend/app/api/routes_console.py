from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.auth import require_admin
from ..core.db import get_db
from ..models.user import User
from ..schemas.console import (
    BusinessSensitiveScannerConfigUpdateRequest,
    ConsoleScannersResponse,
    ConsoleScannersUpdateRequest,
    ConsoleSummaryResponse,
    LastScanResponse,
    ManagementDashboardResponse,
    ScannerPerformanceResponse,
    TokenUsageMonitoringResponse,
)
from ..services.console_service import ConsoleService


router = APIRouter(prefix="/api/console", tags=["console"])


@router.get("/performance", response_model=ScannerPerformanceResponse)
def get_scanner_performance(
    window_hours: int = Query(default=24, ge=1, le=720),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ScannerPerformanceResponse:
    return ConsoleService(db).get_scanner_performance(window_hours=window_hours)


@router.get("/summary", response_model=ConsoleSummaryResponse)
def get_summary(
    username: str | None = Query(default=None, max_length=128),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConsoleSummaryResponse:
    return ConsoleService(db).get_summary(username=username)


@router.get("/scanners", response_model=ConsoleScannersResponse)
def get_scanners(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConsoleScannersResponse:
    return ConsoleService(db).get_scanners()


@router.put("/scanners", response_model=ConsoleScannersResponse)
def update_scanners(
    payload: ConsoleScannersUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConsoleScannersResponse:
    try:
        return ConsoleService(db).update_scanners(payload.enabled_scanners, strict_mode=payload.strict_mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/scanners/business-sensitive", response_model=ConsoleScannersResponse)
def update_business_sensitive_scanner_config(
    payload: BusinessSensitiveScannerConfigUpdateRequest,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConsoleScannersResponse:
    try:
        return ConsoleService(db).update_business_sensitive_config(provider=payload.provider, model=payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/last-scan", response_model=LastScanResponse)
def get_last_scan(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LastScanResponse:
    return ConsoleService(db).get_last_scan()


@router.get("/dashboard", response_model=ManagementDashboardResponse)
def get_dashboard(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ManagementDashboardResponse:
    return ConsoleService(db).get_management_dashboard()


@router.get("/token-usage", response_model=TokenUsageMonitoringResponse)
def get_token_usage(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TokenUsageMonitoringResponse:
    return ConsoleService(db).get_token_usage_monitoring()
