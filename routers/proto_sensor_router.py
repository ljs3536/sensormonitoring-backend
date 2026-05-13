# sensor-backend/proto_sensor_router.py
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
    prefix="/api/proto/sensor",  # 이 라우터의 모든 API는 이 주소로 시작함
    tags=["ProtoSensor"]        # Swagger(Docs)에서 묶어주는 그룹 이름
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
        #orm_mode = True       # Pydantic v1 (버전에 맞게 사용)
        populate_by_name = True # alias로 데이터를 채울 수 있게 허용 (중요!)


class SensorPaginatedResponse(BaseModel):
    items: List[SensorResponse]
    total: int
    page: int
    size: int
    
# --- API 엔드포인트 ---


@router.get("/data/list", response_model=SensorPaginatedResponse)
async def get_proto_list(
    mac_addr: Optional[str] = Query(None),
    leak_yn: Optional[str] = Query(None),
    start_dt: Optional[datetime] = Query(None),
    end_dt: Optional[datetime] = Query(None),
    prob_min: Optional[float] = Query(None),
    prob_max: Optional[float] = Query(None),
    page: int = 1,
    size: int = 50,
    db: Session = Depends(get_db)
):
    """
    ProtoFilterBar의 검색 조건에 따라 센서 데이터 이력을 조회합니다.
    """

    offset = (page - 1) * size
    query = db.query(SensorModel)

    # 1. 맥주소 필터
    if mac_addr and mac_addr != "전체":
        query = query.filter(SensorModel.MAC_ADDR == mac_addr)
    
    # # 2. 누출 여부 필터
    # if leak_yn and leak_yn != "전체":
    #     query = query.filter(SensorModel.LEAK_YN == leak_yn)
    
    # # 3. 기간 필터
    if start_dt and end_dt:
        query = query.filter(
            SensorModel.REG_DT >= start_dt,
            SensorModel.REG_DT <= end_dt
        )

    # 4. 누출 확률 필터 (문자열로 저장되어 있으므로 캐스팅 연산이 필요할 수 있음)
    
    # 최신순 정렬
    query = query.order_by(SensorModel.REG_DT.desc())

    total_count = query.count()
    items = query.offset(offset).limit(size).all()

    return {
        "items": items,
        "total": total_count,
        "page": page,
        "size": size
    }

@router.get("/{seq}", response_model=SensorResponse)
async def get_proto_detail(seq: int, mac_addr: str, db: Session = Depends(get_db)):
    """
    특정 레코드를 클릭했을 때, 그래프를 그리기 위한 SENSOR_DATA(통문자열)를 포함한 상세 정보를 가져옵니다.
    """
    sensor_detail = db.query(SensorModel).filter(
        and_(SensorModel.SEQ == seq, SensorModel.MAC_ADDR == mac_addr)
    ).first()
    
    if not sensor_detail:
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
    
    return sensor_detail
