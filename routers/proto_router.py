# sensor-backend/leak_router.py
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

@router.get("/sensor/list", response_model=List[SensorResponse])
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

@router.get("/sensor/{seq}", response_model=SensorResponse)
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


#  1. 전체 모델 목록 조회 API
@router.get("/models")
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
@router.post("/models/{model_id}/activate")
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
@router.get("/models/{model_id}")
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
@router.get("/models/{model_id}/stats")
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

@router.delete("/models")
async def bulk_delete_models(ids: List[int], db: Session = Depends(get_db)):
    db.query(ModelRegistry).filter(ModelRegistry.MODEL_ID.in_(ids)).update(
        {"STATUS": "DELETE"}, synchronize_session=False
    )
    db.commit()
    return {"message": f"{len(ids)}개의 모델이 삭제 대기 상태로 변경되었습니다."}