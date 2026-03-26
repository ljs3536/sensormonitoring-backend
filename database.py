# sensor-backend/database.py

import influxdb_client
from influxdb_client.client.write_api import ASYNCHRONOUS
from config import settings # 🌟 config.py에서 settings 객체 불러오기!

# --- [1] InfluxDB 설정 (하드코딩 제거!) ---
client = influxdb_client.InfluxDBClient(
    url=settings.influxdb_url,
    token=settings.influxdb_token,
    org=settings.influxdb_org
)
write_api = client.write_api(write_options=ASYNCHRONOUS)

# --- [2] 데이터 저장 함수들 ---
def save_piezo_data(voltage: float, timestamp: float):
    point = (
        influxdb_client.Point("piezo_sensor")
        .field("voltage", voltage)
        .time(int(timestamp * 1e9))
    )
    # 🌟 settings.influxdb_bucket 사용
    write_api.write(bucket=settings.influxdb_bucket, org=settings.influxdb_org, record=point)

def save_adxl_data(x: float, y: float, z: float, timestamp: float):
    point = (
        influxdb_client.Point("adxl_sensor")
        .field("x", x)
        .field("y", y)
        .field("z", z)
        .time(int(timestamp * 1e9))
    )
    # 🌟 settings.influxdb_bucket 사용
    write_api.write(bucket=settings.influxdb_bucket, org=settings.influxdb_org, record=point)

def close_db():
    write_api.close()
    client.close()