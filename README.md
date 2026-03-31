# Sensor Backend
Emulator의 데이터를 가공하여 저장하고, AI 분석 및 실시간 스트리밍을 중계하는 프로젝트의 백엔드

이 모듈은 MQTT로 수신된 센서 RAW 데이터를 역직렬화하여 시계열 DB(InfluxDB)에 저장하고, 정밀 분석(FFT) 및 AI 학습/추론 요청을 관리합니다. 
실시간성을 위해 WebSocket 브로드캐스트 기능을 포함하고 있습니다.

## 🛠 Tech Stack
Framework: FastAPI

Database: InfluxDB 2.7 (Time-series)

Communication: MQTT (Paho-MQTT), WebSocket, HTTP (Httpx)

Library: SQLAlchemy (ORM), NumPy (FFT), APScheduler (Cleanup)

## 🚀 Getting Started
### 1. Infrastructure (Database Setup)
#### A. InfluxDB (Docker)
시계열 데이터 저장을 위해 InfluxDB 2.7 버전을 사용합니다. 데이터 영속성을 위해 볼륨 매핑을 적용합니다.
```
docker run -d \
  --name influxdb \
  -p 8086:8086 \
  -v influxdb2_data:/var/lib/influxdb2 \
  influxdb:2.7
```
- Web UI: http://localhost:8086 (admin / admin1234)

- Organization: sensor_hq

- Bucket: sensor_data
### 2. Environment Setup (.env)
.env.example 파일을 복사하여 .env 파일을 생성하고, 발급받은 InfluxDB 토큰을 입력합니다.
```
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=m7B0P2yETOdQ3M7...AD0g==
INFLUX_ORG=sensor_hq
INFLUX_BUCKET=sensor_data
MARIADB_URL=mysql+pymysql://root:password@localhost:3306/ai_db
MQTT_BROKER=127.0.0.1
AI_URL=http://localhost:8002
```
### 3. Installation & Running
```
# 가상환경 설정
python -m venv venv
.\venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 서버 실행 (start.txt 참고)
uvicorn backend_api:app --reload --port 8001
```
## 📂 Project Structure & Roles
backend_api.py: 메인 라우터. Polling API 및 WebSocket 엔드포인트 관리.

mqtt_handler.py: MQTT 메시지 수신 및 실시간 가공(WebSocket 브로드캐스트 연동).

database.py: InfluxDB 연결 및 Flux 쿼리 수행.

fft_processor.py: 수집된 RAW 데이터의 주파수 도메인 변환 연산.

config.py: Pydantic Settings를 이용한 환경 변수 로드.

## 📡 Core Features
Hybrid Communication: 정밀 분석을 위한 HTTP Polling과 실시간 모니터링을 위한 WebSocket(Push) 방식 동시 지원.

Data Pipeline: 16진수 Hex 데이터를 파싱하여 물리 단위(V, g)로 변환 후 DB 적재.

AI Orchestration: AI 서비스와의 통신을 중계하여 모델 학습(Train) 및 추론(Predict) 인터페이스 제공.

Auto Cleanup: APScheduler를 통해 삭제한 지 7일이 지난 Soft-Delete 모델 자동 삭제.
