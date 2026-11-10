"""批量成绩导入路由（F5）：AC24–AC25。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import BatchRequest, BatchResponse, BatchResultItem
from app.security import Principal, require_staff
from app.services import score_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scores", tags=["batch"])


@router.post("/batch", response_model=BatchResponse)
def batch_import(
    payload: BatchRequest,
    db: Session = Depends(get_db),
    _principal: Principal = Depends(require_staff),
) -> BatchResponse:
    """批量录入成绩：逐条独立事务，单条失败不影响其他条（AC24/AC25）。"""
    records = [item.model_dump() for item in payload.records]
    succeeded, failed, results = score_service.batch_create(
        db, records=records, operator_id=payload.operator_id
    )
    logger.info("批量导入完成: succeeded=%d failed=%d", succeeded, failed)
    return BatchResponse(
        succeeded=succeeded,
        failed=failed,
        results=[BatchResultItem(**item) for item in results],
    )
