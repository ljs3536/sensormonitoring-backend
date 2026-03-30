import paho.mqtt.client as mqtt
import json

MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/data"

def parse_hex_to_int16(hex_str):
    """긴 Hex 문자열을 4자리씩 끊어서 signed int16으로 변환"""
    samples = []
    for i in range(0, len(hex_str), 4):
        chunk = hex_str[i:i+4]
        if len(chunk) == 4:
            val = int(chunk, 16)
            if val >= 0x8000: # 음수 처리
                val -= 0x10000
            samples.append(val)
    return samples

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ [Backend] MQTT Broker 연결 성공! 데이터 수신 대기 중...")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ 연결 실패: {reason_code}")

def on_message(client, userdata, msg):
    try:
        raw_data = msg.payload.decode('utf-8')
        parsed_data = json.loads(raw_data)
        
        sensor_type = parsed_data.get("sensor")
        hex_data = parsed_data.get("hex_data", "")
        seq = parsed_data.get("seq", 0)
        
        # Hex 데이터를 실제 숫자로 복원
        real_values = parse_hex_to_int16(hex_data)
        
        print(f"\n📥 [데이터 수신] Seq: {seq} | Sensor: {sensor_type}")
        if real_values:
            print(f"  - 복원된 샘플 개수: {len(real_values)}개")
            print(f"  - 데이터 미리보기: {real_values[:5]} ...")
            print(f"  - 범위(Min/Max): {min(real_values)} / {max(real_values)}")
        else:
            print("  - 데이터 없음")
            
    except Exception as e:
        print(f"데이터 파싱 에러: {e}")

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="Backend_Subscriber")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
mqtt_client.loop_forever()