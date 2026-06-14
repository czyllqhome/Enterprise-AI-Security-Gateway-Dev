from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from ..core.db import get_db
from ..schemas.logs import LogEntryResponse
from ..services.log_service import LogService


router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[LogEntryResponse])
def list_logs(db: Session = Depends(get_db)) -> list[LogEntryResponse]:
    return LogService(db).list_logs()
