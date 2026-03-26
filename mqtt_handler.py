# MQTT 통신
# sensor-backend/mqtt_handler.py
import json
import time
import paho.mqtt.client as mqtt
from config import settings
from database import save_piezo_data, save_adxl_data

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

# 메인 서버에서 메모리 DB(deque)를 넘겨받아 업데이트합니다.
def setup_mqtt(memory_db):
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
                memory_db["piezo"]["history"].append({"value": val, "timestamp": ts})
                save_piezo_data(val, ts) # DB 영구 저장
                
            elif sensor_type == "adxl" and len(samples) >= 3:
                x_val, y_val, z_val = round(samples[0]/1000.0, 4), round(samples[1]/1000.0, 4), round(samples[2]/1000.0, 4)
                memory_db["adxl"]["history"].append({"x": x_val, "y": y_val, "z": z_val, "timestamp": ts})
                save_adxl_data(x_val, y_val, z_val, ts) # DB 영구 저장
        except Exception as e:
            print(f"❌ 데이터 처리 에러: {e}")

    mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="Backend_API_v3")
    mqtt_client.on_connect = lambda c, u, f, r, p: c.subscribe(MQTT_TOPIC) if r==0 else None
    mqtt_client.on_message = on_message
    
    mqtt_client.connect(settings.mqtt_broker, settings.mqtt_port)
    mqtt_client.loop_start()
    return mqtt_client