# sensor-backend/leak_router.py
from fastapi import APIRouter, Depends, Body, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from database_rdb import get_db, SensorData as SensorModel # SQLAlchemy 모델
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import httpx
from config import settings

# ai 호출
import httpx
from config import settings

router = APIRouter(
    prefix="/api/leak",  # 이 라우터의 모든 API는 이 주소로 시작함
    tags=["Leak"]        # Swagger(Docs)에서 묶어주는 그룹 이름
)
# --- Pydantic 모델 정의 ---

class SensorResponse(BaseModel):
    seq: int = Field(alias="SEQ")
    mac_addr: str = Field(alias="MAC_ADDR")
    battery_rmin: str = Field(alias="BATTERY_RMIN")
    sensor_data: Optional[str] = Field(default=None, alias="SENSOR_DATA")
    leak_prbblt: Optional[str] = Field(default=None, alias="LEAK_PRBBLT")
    reg_dt: datetime = Field(alias="REG_DT")
    leak_yn: Optional[str] = Field(default=None, alias="LEAK_YN")

    class Config:
        from_attributes = True  # Pydantic v2
        # orm_mode = True       # Pydantic v1 (버전에 맞게 사용)
        populate_by_name = True # alias로 데이터를 채울 수 있게 허용 (중요!)


# --- API 엔드포인트 ---

@router.get("/list", response_model=List[SensorResponse])
async def get_leak_list(
    mac_addr: Optional[str] = Query(None),
    leak_yn: Optional[str] = Query(None),
    start_dt: Optional[datetime] = Query(None),
    end_dt: Optional[datetime] = Query(None),
    prob_min: Optional[float] = Query(None),
    prob_max: Optional[float] = Query(None),
    db: Session = Depends(get_db)
):
    """
    LeakFilterBar의 검색 조건에 따라 센서 데이터 이력을 조회합니다.
    """
    query = db.query(SensorModel)

    # 1. 맥주소 필터
    if mac_addr and mac_addr != "전체":
        query = query.filter(SensorModel.MAC_ADDR == mac_addr)
    
    # # 2. 누출 여부 필터
    # if leak_yn and leak_yn != "전체":
    #     query = query.filter(SensorModel.LEAK_YN == leak_yn)
    
    # # 3. 기간 필터
    # if start_dt and end_dt:
    #     query = query.filter(SensorModel.REG_DT.between(start_dt, end_dt))
    
    # 4. 누출 확률 필터 (문자열로 저장되어 있으므로 캐스팅 연산이 필요할 수 있음)
    # 여기서는 간단하게 필터링 로직만 추가합니다.
    # 최신순 정렬
    results = query.order_by(SensorModel.REG_DT.desc()).limit(500).all()
    return results

@router.get("/{seq}", response_model=SensorResponse)
async def get_leak_detail(seq: int, mac_addr: str, db: Session = Depends(get_db)):
    """
    특정 레코드를 클릭했을 때, 그래프를 그리기 위한 SENSOR_DATA(통문자열)를 포함한 상세 정보를 가져옵니다.
    """
    sensor_detail = db.query(SensorModel).filter(
        and_(SensorModel.SEQ == seq, SensorModel.MAC_ADDR == mac_addr)
    ).first()
    
    if not sensor_detail:
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
    
    return sensor_detail

# --- AI 서버 중계 API (기존 유지 및 보완) ---

@router.post("/train/{sensor_type}")
async def request_train(sensor_type: str, model_type: str = "Prototypical", sensor_id: str=None, days: int = 7):
    """AI 서버에 모델 학습(갱신)을 요청합니다."""
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f"{settings.ai_url}/train", 
            params={"sensor_type": sensor_type, "model_type": model_type, "sensor_id": sensor_id, "days": days}
        )
        return response.json()

@router.post("/train/{sensor_type}")
async def request_train(sensor_type: str, model_type: str = "AutoEncoder", sensor_id: str=None, days: int = 7):
    async with httpx.AsyncClient() as client:
        # AI 서비스에 학습 명령 전달 (model_type 추가)
        response = await client.post(
            f"{settings.ai_url}/train", 
            params={"sensor_type": sensor_type, "model_type": model_type, "sensor_id": sensor_id, "days": days}
        )
        return response.json()

@router.get("/models")
async def get_ai_models(sensor_type: str = None):
    """AI 서버에서 학습된 모델 목록을 가져옵니다."""
    async with httpx.AsyncClient() as client:
        params = {"sensor_type": sensor_type} if sensor_type else {}
        response = await client.get(f"{settings.ai_url}/models", params=params)
        return response.json()

@router.post("/predict/{sensor_type}")
async def request_analysis(sensor_type: str, model_id: int, sensor_id: str=None, data: list = Body(...)): 
    """프론트엔드에서 보낸 데이터를 특정 모델 ID로 예측합니다."""
    print("받은 데이터:",data)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ai_url}/predict", 
            json=data, # 프론트에서 보낸 배열 데이터
            params={"sensor_type": sensor_type,"model_id": model_id, "sensor_id": sensor_id} # 모델 ID 전달
        )
        return response.json()
    
@router.post("/{sensor_id}/auto_tune")
async def request_auto_tune(sensor_id: str, sensor_type: str, days: int = 7):
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f"{settings.ai_url}/auto_tune", 
            params={"sensor_id": sensor_id, "sensor_type": sensor_type, "days": days}
        )
        return response.json()
    
@router.delete("/models/{model_id}")
async def delete_ai_model(model_id: int):
    """AI 모델 삭제 중계"""
    async with httpx.AsyncClient() as client:
        response = await client.delete(f"{settings.ai_url}/models/{model_id}")
        # 성공/실패 여부를 그대로 프론트엔드에 전달
        return response.json()
    