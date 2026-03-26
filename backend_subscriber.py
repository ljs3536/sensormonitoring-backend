# 간단한 연결 테스트 페이지
import paho.mqtt.client as mqtt
import json

# --- 브로커 설정 ---
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
MQTT_TOPIC = "sensor/data"

# 1. 연결 성공 시 실행되는 함수
def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ [Backend] MQTT Broker 연결 성공! 데이터 수신 대기 중...")
        # 연결되자마자 "sensor/data" 토픽을 구독(Subscribe)합니다.
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ 연결 실패: {reason_code}")

# 2. 메시지가 도착했을 때 실행되는 함수 (역직렬화 처리)
def on_message(client, userdata, msg):
    try:
        # 수신된 바이트(Byte) 데이터를 문자열로 디코딩 후 JSON 역직렬화(Dictionary 변환)
        raw_data = msg.payload.decode('utf-8')
        parsed_data = json.loads(raw_data)
        
        print("\n📥 [데이터 수신]")
        print(f"  - 토픽: {msg.topic}")
        print(f"  - 내용: {parsed_data}")
        # 여기서 만약 parsed_data['sensor'] == 'piezo' 이면 특정 처리를 하는 등
        # 백엔드 로직을 추가할 수 있습니다.
        
    except Exception as e:
        print(f"데이터 파싱 에러: {e}")

# --- MQTT 클라이언트 설정 및 실행 ---
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="Backend_Subscriber")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

mqtt_client.connect(MQTT_BROKER, MQTT_PORT)

# 프로그램이 종료되지 않고 계속 메시지를 기다리도록 무한 루프 실행
mqtt_client.loop_forever()