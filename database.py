# sensor-backend/database.py

import influxdb_client
from influxdb_client.client.write_api import ASYNCHRONOUS
from config import settings # config.py에서 settings 객체 불러오기!
import datetime

# ==========================================
# 1. InfluxDB 클라이언트 전역 연결 (가장 먼저 실행되어야 함!)
# ==========================================
client = influxdb_client.InfluxDBClient(
    url=settings.influxdb_url,
    token=settings.influxdb_token,
    org=settings.influxdb_org
)

# ==========================================
# 2. 쓰기 및 읽기 API 객체 생성 (client 생성 이후에 위치!)
# ==========================================
write_api = client.write_api(write_options=ASYNCHRONOUS)
query_api = client.query_api()


# --- [2] 데이터 저장 함수들 ---
def save_piezo_data(voltage: float, timestamp: float, label: str = "normal"):
    point = (
        influxdb_client.Point("piezo_sensor")
        .tag("label", label)
        .field("voltage", voltage)
        .time(int(timestamp * 1e9))
    )
    # 🌟 settings.influxdb_bucket 사용
    write_api.write(bucket=settings.influxdb_bucket, org=settings.influxdb_org, record=point)

def save_adxl_data(x: float, y: float, z: float, timestamp: float, label: str = "normal"):
    point = (
        influxdb_client.Point("adxl_sensor")
        .tag("label", label)
        .field("x", x)
        .field("y", y)
        .field("z", z)
        .time(int(timestamp * 1e9))
    )
    # settings.influxdb_bucket 사용
    write_api.write(bucket=settings.influxdb_bucket, org=settings.influxdb_org, record=point)

def get_historical_data(sensor_type: str, start_time: datetime.datetime, end_time: datetime.datetime, axis: str = "x"):
    """사용자가 지정한 절대 시간 범위 내의 센서 데이터를 InfluxDB에서 조회합니다."""
    
    measurement = "piezo_sensor" if sensor_type == "piezo" else "adxl_sensor"
    
    # 파이썬의 타임존을 강제로 UTC로 맞추고, InfluxDB가 좋아하는 깔끔한 Z 포맷으로 직접 치환합니다.
    start_str = start_time.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    end_str = end_time.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    # Flux 쿼리 작성 (range가 절대 시간 범위로 바뀝니다)
    query = f'''
        from(bucket: "{settings.influxdb_bucket}")
        |> range(start: {start_str}, stop: {end_str})
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
    '''
    
    # ADXL의 경우, 특정 축(x, y, z)만 필터링해서 연산 속도를 높일 수도 있습니다. (필수 아님)
    if sensor_type == "adxl":
        query += f'|> filter(fn: (r) => r["_field"] == "{axis}")'

    # DB에 쿼리 전송
    tables = query_api.query(query, org=settings.influxdb_org)
    
    # 프론트엔드가 그리기 편하게 [{time:..., [axis/value]: ...}] 형태로 변환
    # (Piezo는 'value', ADXL은 'x','y','z' 필드명을 키로 사용)
    results = []
    
    # InfluxDB 결과를 Python 객체로 파싱하는 중복 로직을 별도 함수로 빼면 더 좋습니다.
    # (여기서는 일단 가독성을 위해 바로 작성합니다.)
    if sensor_type == "piezo":
        for table in tables:
            for record in table.records:
                results.append({
                    "time": record.get_time().isoformat(),
                    "value": record.get_value()
                })
    else: # adxl
        # ADXL은 x,y,z 필드가 각각 들어오므로, 같은 시간대의 데이터를 묶어주는 로직이 필요합니다.
        # (간단하게 구현하기 위해 브라우저 주소창 조회용과 동일하게 처리합니다.)
        for table in tables:
            for record in table.records:
                results.append({
                    "time": record.get_time().isoformat(),
                    "field": record.get_field(), # 'x', 'y', 또는 'z'
                    "value": record.get_value()
                })
                
    return results
def close_db():
    write_api.close()
    client.close()