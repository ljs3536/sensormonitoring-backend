# sensor-backend/ai_router.py
from fastapi import APIRouter
from fastapi import Body

# ai 호출
import httpx
from config import settings

router = APIRouter(
    prefix="/api/ai",  # 이 라우터의 모든 API는 이 주소로 시작함
    tags=["Ai"]        # Swagger(Docs)에서 묶어주는 그룹 이름
)


@router.post("/train/{sensor_type}")
async def request_train(sensor_type: str, model_type: str = "AutoEncoder", days: int = 7):
    async with httpx.AsyncClient() as client:
        # AI 서비스에 학습 명령 전달 (model_type 추가)
        response = await client.post(
            f"{settings.ai_url}/train", 
            params={"sensor_type": sensor_type, "model_type": model_type, "days": days}
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
async def request_analysis(sensor_type: str, model_id: int, data: list = Body(...)): 
    """프론트엔드에서 보낸 데이터를 특정 모델 ID로 예측합니다."""
    print("받은 데이터:",data)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ai_url}/predict", 
            json=data, # 프론트에서 보낸 배열 데이터
            params={"sensor_type": sensor_type,"model_id": model_id} # 모델 ID 전달
        )
        return response.json()

@router.delete("/models/{model_id}")
async def delete_ai_model(model_id: int):
    """AI 모델 삭제 중계"""
    async with httpx.AsyncClient() as client:
        response = await client.delete(f"{settings.ai_url}/models/{model_id}")
        # 성공/실패 여부를 그대로 프론트엔드에 전달
        return response.json()
    
@router.get("/status")
async def get_ai_status():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{settings.ai_url}/status")
        return response.json()