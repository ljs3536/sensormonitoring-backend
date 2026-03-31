# sensor-backend/mqtt_handler.py
import json
import time
import paho.mqtt.client as mqtt
import asyncio
from config import settings
from database import save_piezo_data, save_adxl_data
import numpy as np
from fft_processor import compute_fft_data

MQTT_TOPIC = "sensor/data"

def parse_samples(hex_str: str):
    samples = []
    for i in range(0, len(hex_str), 4):
        chunk = hex_str[i:i+4]
        if len(chunk) != 4: continue
        value = int(chunk, 16)
        if value >= 0x8000: value -= 0x10000
        samples.append(value)
    return samples

def setup_mqtt(memory_db, ws_manager):
    # FastAPI가 실행 중인 메인 이벤트 루프를 미리 가져옵니다.
    main_loop = asyncio.get_event_loop()

    def on_message(client, userdata, msg):
        try:
            raw_payload = json.loads(msg.payload.decode('utf-8'))
            sensor_type = raw_payload.get("sensor")
            hex_data = raw_payload.get("hex_data")
            ts = raw_payload.get("timestamp", time.time())
            
            # 에뮬레이터에서 보낸 라벨 정보 받기 (없으면 "normal" 처리)
            label = raw_payload.get("label", "normal") 

            if not hex_data: return
            samples = parse_samples(hex_data)

            # 1초에 128개가 들어왔다면, 각 데이터의 시간차를 계산해줍니다.
            if sensor_type == "piezo":
                time_step = 1.0 / len(samples) if len(samples) > 0 else 0
                
                # 128개 데이터를 모두 돌면서 DB에 밀어 넣습니다!
                for i, val in enumerate(samples):
                    real_val = round(val / 1000.0, 4)
                    current_ts = ts + (i * time_step) # 타임스탬프 미세 분배
                    
                    memory_db["piezo"]["history"].append({"value": real_val, "timestamp": current_ts})
                    # DB 저장 함수에 label을 함께 넘겨줍니다.
                    save_piezo_data(real_val, current_ts, label) 
                    
            elif sensor_type == "adxl":
                # ADXL은 x,y,z 3개가 한 세트이므로 3개씩 묶어서 처리합니다.
                num_records = len(samples) // 3
                time_step = 1.0 / num_records if num_records > 0 else 0
                
                for i in range(0, len(samples), 3):
                    if i+2 >= len(samples): break
                    x_val, y_val, z_val = round(samples[i]/1000.0, 4), round(samples[i+1]/1000.0, 4), round(samples[i+2]/1000.0, 4)
                    current_ts = ts + ((i//3) * time_step)
                    
                    memory_db["adxl"]["history"].append({"x": x_val, "y": y_val, "z": z_val, "timestamp": current_ts})
                    # DB 저장 함수에 label을 함께 넘겨줍니다.
                    save_adxl_data(x_val, y_val, z_val, current_ts, label)

            # --- 웹소켓으로 실시간 브로드캐스트 ---
            # MQTT 스레드에서 FastAPI의 비동기 함수인 broadcast를 안전하게 호출합니다.

            # --- 웹소켓으로 실시간 브로드캐스트 ---
            ws_payload = {
                "sensor": sensor_type,
                "timestamp": ts,
                "label": label,
                "history": [],
                "fft": {}
            }
            # --- 1. Piezo 데이터 가공 ---
            if sensor_type == "piezo":
                # Piezo 가공
                vals = [round(v / 1000.0, 4) for v in samples]
                ws_payload["history"] = [{"value": v, "timestamp": ts} for v in vals]
                ws_payload["fft"] = compute_fft_data(vals, sample_rate=1000) # 단일 배열

            # --- 2. ADXL 데이터 가공 (X, Y, Z 분리) ---
            elif sensor_type == "adxl":
                # ADXL 가공 (X, Y, Z 분리)
                history = []
                for i in range(0, len(samples), 3):
                    if i + 2 < len(samples):
                        history.append({
                            "x": round(samples[i] / 1000.0, 4),
                            "y": round(samples[i+1] / 1000.0, 4),
                            "z": round(samples[i+2] / 1000.0, 4),
                            "timestamp": ts
                        })
                ws_payload["history"] = history
                
                # 🌟 중요: 모든 축의 FFT를 미리 계산해서 객체로 묶음
                ws_payload["fft"] = {
                    "x": compute_fft_data([d["x"] for d in history],sample_rate=1000),
                    "y": compute_fft_data([d["y"] for d in history],sample_rate=1000),
                    "z": compute_fft_data([d["z"] for d in history],sample_rate=1000)
                }
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(ws_payload),
                main_loop
            )

        except Exception as e:
            print(f"❌ 데이터 처리 에러: {e}")

    mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="Backend_API_v3")
    mqtt_client.on_connect = lambda c, u, f, r, p: c.subscribe(MQTT_TOPIC) if r==0 else None
    mqtt_client.on_message = on_message
    
    mqtt_client.connect(settings.mqtt_broker, settings.mqtt_port)
    mqtt_client.loop_start()
    return mqtt_client