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
    prefix="/api/proto",  # 이 라우터의 모든 API는 이 주소로 시작함
    tags=["Proto"]        # Swagger(Docs)에서 묶어주는 그룹 이름
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


# --- API 엔드포인트 ---

@router.get("/list", response_model=List[SensorResponse])
async def get_proto_list(
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
    if start_dt and end_dt:
        query = query.filter(
            SensorModel.REG_DT >= start_dt,
            SensorModel.REG_DT <= end_dt
        )

    # 4. 누출 확률 필터 (문자열로 저장되어 있으므로 캐스팅 연산이 필요할 수 있음)
    # 여기서는 간단하게 필터링 로직만 추가합니다.
    # 최신순 정렬
    results = query.order_by(SensorModel.REG_DT.desc()).limit(500).all()
    return results

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

# 프론트엔드에서 예측을 요청할 때 보낼 데이터 규격
class PredictRequest(BaseModel):
    seq_list: List[int]
    mac_addr: str

# 🌟 1. AI 모델 갱신 (학습 트리거)
@router.post("/train/{sensor_id}")
async def request_train(sensor_id: str, model_type: str, days: int = 7):
    """
    AI 서버에 학습을 지시합니다. (데이터 전송 X, 명령만 전달)
    AI 서버는 이 요청을 받으면 스스로 RDB에 접속해 최근 {days}일치 데이터를 긁어가서 학습합니다.
    """
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f"{settings.ai_url}/ai/proto/train", 
            params={"sensor_id": sensor_id, "model_type": model_type, "days": days}
        )
        return response.json()


# 🌟 2. 누출 여부 예측 및 DB 업데이트
@router.post("/predict/{model_type}")
async def request_predict(model_type: str, req: PredictRequest, db: Session = Depends(get_db)):
    """
    프론트에서 선택한 seq 번호들의 데이터를 DB에서 꺼내 AI 서버에 예측을 맡깁니다.
    """
    # 1. DB에서 선택된 데이터들 조회
    records = db.query(SensorModel).filter(
        and_(SensorModel.SEQ.in_(req.seq_list), SensorModel.MAC_ADDR == req.mac_addr)
    ).all()

    if not records:
        raise HTTPException(status_code=404, detail="요청한 데이터를 DB에서 찾을 수 없습니다.")

    # 2. AI 서버에 보낼 2D Float 배열 생성
    # AI는 [ [0.1, 0.2, ...], [0.1, 0.3, ...] ] 형태의 Batch 처리를 좋아합니다.
    ai_input_data = []
    for record in records:
        fft_array = [float(val) for val in record.SENSOR_DATA.split('|')]
        ai_input_data.append(fft_array)

    # 3. AI 서버에 예측 요청
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 예시: AI 서버가 {"predictions": [{"prob": 0.95, "is_leak": "Y"}, ...]} 형태로 응답한다고 가정
            print(req.mac_addr)
            response = await client.post(
                f"{settings.ai_url}/ai/proto/predict", 
                params={"sensor_id": req.mac_addr, "model_type": model_type},
                json={"features": ai_input_data} 
            )
            if response.status_code != 200:
                error_msg = response.json().get("detail", "알 수 없는 에러")
                print(f"❌ [백엔드] AI 서버 통신 에러: {response.status_code} - {error_msg}")
                raise HTTPException(status_code=response.status_code, detail=f"AI 서버 측 에러: {error_msg}")

            ai_results = response.json().get("predictions", [])
            
    except httpx.RequestError as e:
        # AI 서버가 아예 꺼져있거나 주소가 틀렸을 때
        raise HTTPException(status_code=500, detail=f"AI 서버에 연결할 수 없습니다: {str(e)}")

    # 4. AI의 예측 결과를 받아 RDB 업데이트
    updated_results = []
    for record, ai_res in zip(records, ai_results):
        # AI 결과 적용 (소수점 2자리 %로 표현한다고 가정)
        prob_percent = round(ai_res.get("prob", 0) * 100, 2) 
        
        record.LEAK_PRBBLT = str(prob_percent)
        record.LEAK_YN = ai_res.get("is_leak", "N")
        
        updated_results.append({
            "seq": record.SEQ,
            "leakProbability": record.LEAK_PRBBLT,
            "leakageFirst": record.LEAK_YN
        })

    db.commit() # 변경사항 DB에 영구 저장

    # 5. 프론트엔드 화면 업데이트를 위해 결과 반환
    return {"status": "success", "updated_data": updated_results}