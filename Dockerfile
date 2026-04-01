# 1. 베이스 이미지 설정 (가벼운 slim 버전 추천)
FROM python:3.9-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 소스 코드 복사
COPY . .

# 5. 포트 설정
EXPOSE 8001

# 6. 실행 명령 (Uvicorn 등을 사용하여 실행)
CMD ["uvicorn", "backend_api:app"]