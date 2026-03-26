import json
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt

app = FastAPI()

# --- CORS 설정 (Next.js 프론트엔드에서 API를 호출할 수 있도록 허용) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영에서는 Next.js 주소(예: http://localhost:3000)만 허용하는 것이 좋습니다.
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 상태 관리 (가장 최근에 수신한 센서 데이터를 메모리에 저장) ---
latest_data = {
    "piezo": None,
    "adxl": None
}

# --- MQTT 설정 ---
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/data"

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ [Backend API] MQTT Broker 연결 성공! 데이터 수신 대기 중...")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ 연결 실패: {reason_code}")

def on_message(client, userdata, msg):
    try:
        raw_data = msg.payload.decode('utf-8')
        parsed_data = json.loads(raw_data)
        
        # 센서 타입(adxl 또는 piezo)을 확인하고 latest_data 딕셔너리 갱신
        sensor_type = parsed_data.get("sensor")
        if sensor_type in latest_data:
            latest_data[sensor_type] = parsed_data
            
    except Exception as e:
        print(f"데이터 파싱 에러: {e}")

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="Backend_API")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# --- FastAPI 수명주기 이벤트 (서버 시작/종료 시 MQTT 클라이언트 관리) ---
@app.on_event("startup")
async def startup_event():
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
    # loop_forever() 대신 loop_start()를 사용하여 백그라운드 스레드에서 MQTT 처리 (FastAPI를 막지 않음)
    mqtt_client.loop_start() 

@app.on_event("shutdown")
async def shutdown_event():
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

# --- 프론트엔드(Next.js)가 Polling으로 호출할 API 엔드포인트 ---
@app.get("/api/data/latest")
async def get_latest_data():
    return latest_data

@app.get("/")
async def root():
    return {"message": "Sensor Backend API is running! Go to /api/data/latest"}