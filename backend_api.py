# 메인 API 라우터
# sensor-backend/backend_api.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from collections import deque
from fastapi import Body
from typing import List

# 분리한 모듈들 불러오기
from database import close_db, get_historical_data
from fft_processor import compute_fft_data
from mqtt_handler import setup_mqtt
from datetime import datetime

# ai 호출
import httpx
from config import settings

app = FastAPI()

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

MAX_HISTORY = 100
db = {
    "piezo": {"history": deque(maxlen=MAX_HISTORY)},
    "adxl": {"history": deque(maxlen=MAX_HISTORY)}
}

mqtt_client = None

class ConnectionManager:
    def __init__(self):
        # 연결된 웹소켓들을 관리하는 리스트
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # 연결된 모든 클라이언트에게 데이터 전송
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # 끊긴 연결은 자동으로 정리할 수도 있음
                pass

manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    global mqtt_client
    mqtt_client = setup_mqtt(db, manager) # 모듈화된 MQTT 시작, websocket 추가

@app.on_event("shutdown")
async def shutdown_event():
    if mqtt_client: mqtt_client.loop_stop()
    close_db()

@app.websocket("/ws/sensor/{sensor_type}")
async def websocket_endpoint(websocket: WebSocket, sensor_type: str):
    await manager.connect(websocket)
    try:
        while True:
            # 웹소켓 유지를 위한 루프 (클라이언트가 메시지를 보낼 일은 없으므로 대기)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 실시간 데이터 폴링 API
@app.get("/api/data/latest/{sensor_type}")
async def get_latest_data(sensor_type: str):
    if sensor_type not in db: return {"error": "Invalid sensor"}
    return {"history": list(db[sensor_type]["history"])}

# 실시간 FFT 연산 API
@app.get("/api/data/fft/{sensor_type}")
async def get_fft_data(sensor_type: str, sample_rate: int = 1000, axis: str = "x", window: str = "hann"):
    if sensor_type not in db or not db[sensor_type]["history"]: return []
    history_data = list(db[sensor_type]["history"])
    
    samples = [item["value"] for item in history_data] if sensor_type == "piezo" else [item.get(axis, 0.0) for item in history_data]
    return compute_fft_data(samples, sample_rate, window)

# InfluxDB 과거 기록 조회 전용 API (시작/끝 날짜를 받음)
@app.get("/api/db/history/{sensor_type}")
async def get_db_history_data(sensor_type: str, start_iso: str, end_iso: str, axis: str = "x"):
    """
    브라우저 조회 예시:
    http://localhost:8001/api/db/history/piezo?start_iso=2023-10-27T00:00:00&end_iso=2023-10-27T23:59:59
    """
    try:
        # 프론트엔드가 보낸 ISO 문자열을 Python datetime 객체로 변환
        start_time = datetime.fromisoformat(start_iso)
        end_time = datetime.fromisoformat(end_iso)
        
        data = get_historical_data(sensor_type, start_time, end_time, axis)
        return {
            "sensor": sensor_type,
            "count": len(data),
            "data": data
        }
    except ValueError:
        return {"error": "Invalid date format. Use ISO 8601 format."}
    

@app.post("/api/ai/train/{sensor_type}")
async def request_train(sensor_type: str, model_type: str = "AutoEncoder", days: int = 7):
    async with httpx.AsyncClient() as client:
        # AI 서비스에 학습 명령 전달 (model_type 추가)
        response = await client.post(
            f"{settings.ai_url}/train", 
            params={"sensor_type": sensor_type, "model_type": model_type, "days": days}
        )
        return response.json()

@app.get("/api/ai/models")
async def get_ai_models(sensor_type: str = None):
    """AI 서버에서 학습된 모델 목록을 가져옵니다."""
    async with httpx.AsyncClient() as client:
        params = {"sensor_type": sensor_type} if sensor_type else {}
        response = await client.get(f"{settings.ai_url}/models", params=params)
        return response.json()

@app.post("/api/ai/predict/{model_id}")
async def request_analysis(model_id: int, data: list = Body(...)): 
    """프론트엔드에서 보낸 데이터를 특정 모델 ID로 예측합니다."""
    print("받은 데이터:",data)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ai_url}/predict", 
            json=data, # 프론트에서 보낸 배열 데이터
            params={"model_id": model_id} # 모델 ID 전달
        )
        return response.json()

@app.delete("/api/ai/models/{model_id}")
async def delete_ai_model(model_id: int):
    """AI 모델 삭제 중계"""
    async with httpx.AsyncClient() as client:
        response = await client.delete(f"{settings.ai_url}/models/{model_id}")
        # 성공/실패 여부를 그대로 프론트엔드에 전달
        return response.json()
    
@app.get("/api/ai/status")
async def get_ai_status():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{settings.ai_url}/status")
        return response.json()
