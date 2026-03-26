import json
import asyncio
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
from collections import deque # 데이터 히스토리 관리를 위해 사용
import numpy as np
from scipy.signal.windows import flattop
from database import save_piezo_data, save_adxl_data, close_db
from config import settings

app = FastAPI()

# --- CORS 설정 (Next.js 프론트엔드에서 API를 호출할 수 있도록 허용) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 운영에서는 Next.js 주소(예: http://localhost:3000)만 허용하는 것이 좋습니다.
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 상태 관리 (메모리 내 저장소) ---
# 프론트엔드 그래프를 위해 최근 100개의 데이터를 보관합니다.
MAX_HISTORY = 100

db = {
    "piezo": {
        "history": deque(maxlen=MAX_HISTORY),
        "config": {
            "piezoSampleRate": 1000,
            "piezoSampleCount": 1024,
            "piezoFmax": 500
        }
    },
    "adxl": {
        "history": deque(maxlen=MAX_HISTORY),
        "config": {
            "memsSampleRate": 1000,
            "memsSampleCount": 1024,
            "gRange": "2g"
        }
    }
}

# --- MQTT 설정 ---
MQTT_TOPIC = "sensor/data"

# --- [추가] Window Function 로직 ---
def get_window(window_type: str, size: int):
    window_type = window_type.lower()
    if window_type == "hann": return np.hanning(size)
    elif window_type == "hamming": return np.hamming(size)
    elif window_type == "blackman": return np.blackman(size)
    elif window_type == "flattop": return flattop(size)
    elif window_type == "none": return np.ones(size)
    else: return np.hanning(size) # 기본값

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ [Backend API] MQTT Broker 연결 성공! 데이터 수신 대기 중...")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ 연결 실패: {reason_code}")

def parse_samples(hex_str: str):
    samples = []
    for i in range(0, len(hex_str), 4):
        chunk = hex_str[i:i+4]
        if len(chunk) != 4:
            continue
        value = int(chunk, 16)
        # signed int16 변환
        if value >= 0x8000:
            value -= 0x10000
        samples.append(value)
    return samples


def on_message(client, userdata, msg):
    try:
        raw_payload = json.loads(msg.payload.decode('utf-8'))
        sensor_type = raw_payload.get("sensor")
        hex_data = raw_payload.get("hex_data")
        ts = raw_payload.get("timestamp", time.time())

        if not hex_data: return
        samples = parse_samples(hex_data)

        if sensor_type == "piezo" and len(samples) >= 1:
            val = round(samples[0] / 1000.0, 4)
            # 프론트엔드 SensorDataPoint 형식에 맞춤
            data_point = {"value": val, "timestamp": ts}
            db["piezo"]["history"].append(data_point)

            # 메모리(프론트엔드용)에 넣은 직후 DB에도 영구 저장!
            save_piezo_data(val, ts)
            
        elif sensor_type == "adxl" and len(samples) >= 3:
            x_val, y_val, z_val = round(samples[0]/1000.0, 4), round(samples[1]/1000.0, 4), round(samples[2]/1000.0, 4)
            data_point = {"x": x_val, "y": y_val, "z": z_val, "timestamp": ts}
            db["adxl"]["history"].append(data_point)

            # DB 영구 저장!
            save_adxl_data(x_val, y_val, z_val, ts)


    except Exception as e:
        print(f"❌ 데이터 처리 에러: {e}")

# --- [추가] FFT 연산 핵심 로직 ---
def compute_fft_data(samples, sample_rate: int, window_type: str = "hann"):
    if len(samples) < 2: return []
    
    # 1. 평균(DC 성분) 제거
    x = np.array(samples, dtype=float)
    x -= np.mean(x)
    
    # 2. 해닝 창(Hanning Window) 적용하여 노이즈 감소
    window = np.hanning(len(x))
    xw = x * window
    
    # 3. Real FFT 연산
    rfft = np.fft.rfft(xw)
    freqs = np.fft.rfftfreq(len(xw), d=1/sample_rate)
    mags = np.abs(rfft) / len(xw) # 진폭 정규화
    
    # 프론트엔드가 그리기 편한 [{frequency: ..., magnitude: ...}] 형태로 변환
    fft_result = [{"frequency": round(float(f), 2), "magnitude": round(float(m), 4)} for f, m in zip(freqs, mags)]
    return fft_result

# --- MQTT 클라이언트 초기화 ---
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="Backend_API_v2")
mqtt_client.on_connect = lambda c, u, f, r, p: c.subscribe(MQTT_TOPIC) if r==0 else None
mqtt_client.on_message = on_message

@app.on_event("startup")
async def startup_event():
    mqtt_client.connect(settings.mqtt_broker, settings.mqtt_port)
    mqtt_client.loop_start()

@app.on_event("shutdown")
async def shutdown_event():
    mqtt_client.loop_stop()
    # 서버가 꺼질 때 InfluxDB 연결도 깔끔하게 닫기
    close_db()

# --- API 엔드포인트 ---

# 1. 최신 데이터 및 히스토리 조회 (Polling용) - 요청한 센서 데이터만 반환하도록 수정!
@app.get("/api/data/latest/{sensor_type}")
async def get_latest_data(sensor_type: str):
    if sensor_type not in db:
        return {"error": "Invalid sensor type"}
    
    history_data = list(db[sensor_type]["history"])
    latest_data = history_data[-1] if history_data else None

    return {
        "latest": latest_data,
        "history": history_data
    }

# --- [추가] FFT 전용 API 엔드포인트 ---
@app.get("/api/data/fft/{sensor_type}")
async def get_fft_data(sensor_type: str, sample_rate: int = 1000, axis: str = "x", window: str = "hann"):
    if sensor_type not in db or not db[sensor_type]["history"]:
        return []

    history_data = list(db[sensor_type]["history"])
    
    # 센서 타입에 따라 데이터 추출
    if sensor_type == "piezo":
        samples = [item["value"] for item in history_data]
    else: # adxl
        samples = [item.get(axis, 0.0) for item in history_data]

    # FFT 연산 후 반환
    fft_result = compute_fft_data(samples, sample_rate)
    return fft_result


@app.get("/")
async def root():
    return {"message": "Advanced Sensor Backend is running"}