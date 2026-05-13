# sensor-backend/proto_router.py
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
    prefix="/api/proto",  # 이 라우터의 모든 API는 이 주소로 시작함
    tags=["Proto"]        # Swagger(Docs)에서 묶어주는 그룹 이름
)
# --- Pydantic 모델 정의 ---

# 프론트엔드에서 예측을 요청할 때 보낼 데이터 규격
class PredictRequest(BaseModel):
    seq_list: List[int]
    mac_addr: str

class TrainRequest(BaseModel):
    memo: str = ""

#  1. AI 모델 갱신 (학습 트리거)
@router.post("/train/{sensor_id}")
async def request_train(sensor_id: str, model_type: str, update_mode: str, auto_activate: bool, days: int = 7,request_data: TrainRequest = Body(...)):
    """
    AI 서버에 학습을 지시합니다. (중간 게이트웨이 역할)
    """
    # 전송할 JSON 바디 데이터 구성
    payload = {"memo": request_data.memo}
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f"{settings.ai_url}/ai/proto/train", 
            params={
                "sensor_id": sensor_id, 
                "model_type": model_type, 
                "days": days,
                "update_mode": update_mode, 
                "auto_activate": auto_activate
            },
            # 2. HTTP Body에 담길 JSON 데이터 
            json=payload
        )
        return response.json()


#  2. 누출 여부 예측 및 DB 업데이트
@router.post("/predict")
async def request_predict(req: PredictRequest, db: Session = Depends(get_db)):
    # 1. DB에서 해당 센서의 'ACTIVE' 모델 찾기
    active_model = db.query(ModelRegistry).filter(
        ModelRegistry.MAC_ADDR == req.mac_addr,
        ModelRegistry.STATUS == "ACTIVE"
    ).first()

    if not active_model:
        raise HTTPException(status_code=400, detail="이 센서에 활성화된(ACTIVE) 모델이 없습니다. 모델 관리 페이지에서 모델을 학습하고 적용해주세요.")

    # 2. 예측할 데이터 조회
    records = db.query(SensorModel).filter(
        SensorModel.SEQ.in_(req.seq_list), 
        SensorModel.MAC_ADDR == req.mac_addr
    ).all()

    if not records:
        raise HTTPException(status_code=404, detail="요청한 데이터를 DB에서 찾을 수 없습니다.")

    ai_input_data = [[float(val) for val in r.SENSOR_DATA.split('|')] for r in records]

    # 3. AI 서버에 정확한 파일 경로와 함께 예측 요청
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.ai_url}/ai/proto/predict", 
                json={
                    "features": ai_input_data,
                    "file_path": active_model.FILE_PATH,    #  DB에서 꺼낸 경로 전달
                    "model_type": active_model.MODEL_TYPE   #  DB에서 꺼낸 타입 전달
                } 
            )
            response.raise_for_status()
            ai_results = response.json().get("predictions", [])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 서버 통신 오류: {str(e)}")

    # 4. 결과 업데이트 및 로그(PredictionLog) 저장
    updated_results = []
    for record, ai_res in zip(records, ai_results):
        prob_percent = round(ai_res.get("prob", 0) * 100, 2) 
        is_leak = ai_res.get("is_leak", "N")
        
        # [기존] 센서 데이터 마스터 테이블 업데이트
        record.LEAK_PRBBLT = str(prob_percent)
        record.LEAK_YN = is_leak
        
        #  [NEW] 예측 로그 테이블에 INSERT!
        new_log = PredictionLog(
            MODEL_ID=active_model.MODEL_ID,
            MAC_ADDR=req.mac_addr,
            PROBABILITY=prob_percent,
            RESULT=is_leak
        )
        db.add(new_log) # 세션에 추가
        
        updated_results.append({
            "seq": record.SEQ,
            "leakProbability": record.LEAK_PRBBLT,
            "leakageFirst": record.LEAK_YN
        })

    db.commit() # 마스터 테이블 업데이트와 로그 INSERT를 한 번에 커밋!

    return {"status": "success", "updated_data": updated_results}
