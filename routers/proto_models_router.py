# sensor-backend/proto_models_router.py
from fastapi import APIRouter, Depends, Body, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc, text
from database_rdb import get_db,ModelRegistry, PredictionLog, SensorData as SensorModel # SQLAlchemy 모델
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import httpx
from config import settings

# ai 호출
import httpx
from config import settings

router = APIRouter(
    prefix="/api/proto/models",  # 이 라우터의 모든 API는 이 주소로 시작함
    tags=["Proto"]        # Swagger(Docs)에서 묶어주는 그룹 이름
)

#  1. 전체 모델 목록 조회 API
@router.get("/")
async def get_model_registry(
    page: int = 1,
    size: int = 10,    
    db: Session = Depends(get_db)
):
    offset = (page -1) * size
    query = db.query(ModelRegistry).filter(ModelRegistry.STATUS != 'DELETE')
    # 센서별, 버전 역순(최신순)으로 정렬하여 가져옵니다.
    total_count = query.count()
    # 최신 버전순 정렬 후 페이징 처리
    models = query.order_by(ModelRegistry.VERSION.desc()).offset(offset).limit(size).all()
    
    return {
        "items": models,
        "total": total_count,
        "page": page,
        "size": size
    }

#  2. 특정 모델을 ACTIVE로 교체하는 API
@router.post("/{model_id}/activate")
async def activate_model(model_id: int, db: Session = Depends(get_db)):
    target_model = db.query(ModelRegistry).filter(ModelRegistry.MODEL_ID == model_id).first()
    
    if not target_model:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")

    # 1) 해당 센서의 기존 'ACTIVE' 모델들을 모두 'INACTIVE'로 강등
    db.query(ModelRegistry).filter(
        ModelRegistry.MAC_ADDR == target_model.MAC_ADDR,
        ModelRegistry.STATUS == "ACTIVE"
    ).update({"STATUS": "INACTIVE"})

    # 2) 선택한 모델을 'ACTIVE'로 승격
    target_model.STATUS = "ACTIVE"
    db.commit()

    return {"message": f"[{target_model.MAC_ADDR}] 센서의 모델이 v{target_model.VERSION}으로 성공적으로 교체되었습니다."}

# 1. 모델 상세 정보 단건 조회 API
@router.get("/{model_id}")
async def get_model_detail(model_id: int, db: Session = Depends(get_db)):
    model = db.query(ModelRegistry).filter(ModelRegistry.MODEL_ID == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="모델을 찾을 수 없습니다.")
    
    return {
        "model_id": model.MODEL_ID,
        "mac_addr": model.MAC_ADDR,
        "model_type": model.MODEL_TYPE,
        "version": model.VERSION,
        "status": model.STATUS,
        "eval_metrics": model.EVAL_METRICS,
        "reg_dt": model.REG_DT.strftime("%Y-%m-%d %H:%M:%S") if model.REG_DT else "-",
        "memo": model.MEMO
    }

# 2. 모델 실전 예측 통계 (히스토그램용) API
@router.get("/{model_id}/stats")
async def get_model_prediction_stats(model_id: int, db: Session = Depends(get_db)):
    # 0~10%, 10~20% ... 구간별 예측 건수 집계
    stats = db.execute(text("""
        SELECT 
            FLOOR(PROBABILITY / 10) * 10 AS bin_start,
            COUNT(*) as count
        FROM tb_prediction_log
        WHERE MODEL_ID = :mid
        GROUP BY bin_start
        ORDER BY bin_start
    """), {"mid": model_id}).fetchall()

    # 프론트엔드에서 그리기 쉽게 0부터 90까지 빈 배열을 만들고 채워 넣음
    result = {str(i): 0 for i in range(0, 100, 10)}
    for s in stats:
        bin_val = int(s[0])
        # 혹시 100%가 나오면 90 구간에 포함
        if bin_val >= 100: bin_val = 90 
        result[str(bin_val)] = s[1]

    return {"stats": result}

@router.delete("/")
async def bulk_delete_models(ids: List[int], db: Session = Depends(get_db)):
    db.query(ModelRegistry).filter(ModelRegistry.MODEL_ID.in_(ids)).update(
        {"STATUS": "DELETE"}, synchronize_session=False
    )
    db.commit()
    return {"message": f"{len(ids)}개의 모델이 삭제 대기 상태로 변경되었습니다."}

@router.get("/list/{mac_addr}")
async def get_models_by_sensor(mac_addr: str, db: Session = Depends(get_db)):
    """특정 센서에 등록된 모델 목록만 조회 (페이징 없음)"""
    models = db.query(ModelRegistry).filter(
        ModelRegistry.MAC_ADDR == mac_addr,
        ModelRegistry.STATUS != 'DELETE'
    ).order_by(ModelRegistry.VERSION.desc()).all()
    
    # 필요한 정보만 슬림하게 전달
    return [
        {
            "model_id": m.MODEL_ID,
            "version": m.VERSION,
            "model_type": m.MODEL_TYPE,
            "status": m.STATUS
        } for m in models
    ]