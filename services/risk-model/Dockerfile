FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY services/common /app/services/common
RUN pip install --no-cache-dir -e /app/services/common

COPY services/risk-model /app/services/risk-model
WORKDIR /app/services/risk-model
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
