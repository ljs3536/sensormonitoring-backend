from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from database_rdb import SessionLocal, get_db, PredictionLog, ModelRegistry # 모델명은 실제와 맞춤
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/api/proto/logs", tags=["ProtoLogs"])

# 응답 스키마
class LogResponse(BaseModel):
    LOG_ID: int
    MODEL_ID: int
    MAC_ADDR: str
    PROBABILITY: float
    RESULT: str
    REG_DT: str # datetime을 isoformat 문자열로

@router.get("/list")
async def get_prediction_logs(
    mac_addr: Optional[str] = Query(None),
    model_id: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(PredictionLog)
    
    if mac_addr and mac_addr != "전체":
        query = query.filter(PredictionLog.MAC_ADDR == mac_addr)
    if model_id and model_id != "전체":
        query = query.filter(PredictionLog.MODEL_ID == model_id)
    if result and result != "전체":
        query = query.filter(PredictionLog.RESULT == result)
        
    query = query.order_by(PredictionLog.REG_DT.desc())
    
    total = query.count()
    items = query.offset((page - 1) * size).limit(size).all()
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size
    }