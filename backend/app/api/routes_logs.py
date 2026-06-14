from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from ..core.auth import require_admin
from ..core.db import get_db
from ..models.user import User
from ..schemas.logs import LogEntryResponse
from ..services.log_service import LogService


router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[LogEntryResponse])
def list_logs(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[LogEntryResponse]:
    return LogService(db).list_logs()
