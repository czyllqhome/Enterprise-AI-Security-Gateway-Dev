from typing import Literal

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, Query

from ..core.auth import require_admin
from ..core.db import get_db
from ..models.user import User
from ..schemas.logs import LogEntryResponse
from ..services.log_service import LogService


router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[LogEntryResponse])
def list_logs(
    decision: Literal["allowed", "review", "blocked"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[LogEntryResponse]:
    return LogService(db).list_logs(decision=decision, limit=limit, offset=offset)
