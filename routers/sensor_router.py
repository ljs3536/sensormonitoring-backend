# sensor-backend/routers/sensor_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from database_rdb import get_db # DB 세션 가져오는 함수 (구현되어 있다고 가정)
from sensors import Sensor       # 방금 만든 SQLAlchemy 모델

router = APIRouter(
    prefix="/api/sensors",
    tags=["Sensors"]
)

# --- Pydantic 스키마 (데이터 유효성 검사 및 API 문서화용) ---
class SensorBase(BaseModel):
    name: str
    type: str
    sampling_rate: int
    threshold_min: Optional[float] = None
    threshold_max: Optional[float] = None
    location: Optional[str] = None
    is_active: bool = True

class SensorCreate(SensorBase):
    id: str  # 생성할 때는 ID를 직접 입력받음 (예: piezo_01)

class SensorResponse(SensorCreate):
    class Config:
        orm_mode = True # SQLAlchemy 객체를 Pydantic 모델로 자동 변환

# --- API 엔드포인트 ---

@router.get("/", response_model=List[SensorResponse])
async def get_all_sensors(db: Session = Depends(get_db)):
    """모든 센서 목록을 조회합니다."""
    sensors = db.query(Sensor).all()
    return sensors

@router.post("/", response_model=SensorResponse)
async def create_sensor(sensor: SensorCreate, db: Session = Depends(get_db)):
    """새로운 센서를 등록합니다."""
    db_sensor = db.query(Sensor).filter(Sensor.id == sensor.id).first()
    if db_sensor:
        raise HTTPException(status_code=400, detail="이미 존재하는 센서 ID입니다.")
    
    new_sensor = Sensor(**sensor.dict())
    db.add(new_sensor)
    db.commit()
    db.refresh(new_sensor)
    return new_sensor

@router.put("/{sensor_id}", response_model=SensorResponse)
async def update_sensor(sensor_id: str, sensor_update: SensorBase, db: Session = Depends(get_db)):
    """기존 센서의 정보를 수정합니다."""
    db_sensor = db.query(Sensor).filter(Sensor.id == sensor_id).first()
    if not db_sensor:
        raise HTTPException(status_code=404, detail="센서를 찾을 수 없습니다.")
    
    for key, value in sensor_update.dict().items():
        setattr(db_sensor, key, value)
        
    db.commit()
    db.refresh(db_sensor)
    return db_sensor

@router.delete("/{sensor_id}")
async def delete_sensor(sensor_id: str, db: Session = Depends(get_db)):
    """센서를 삭제합니다."""
    db_sensor = db.query(Sensor).filter(Sensor.id == sensor_id).first()
    if not db_sensor:
        raise HTTPException(status_code=404, detail="센서를 찾을 수 없습니다.")
    
    db.delete(db_sensor)
    db.commit()
    return {"message": f"{sensor_id} 센서가 삭제되었습니다."}