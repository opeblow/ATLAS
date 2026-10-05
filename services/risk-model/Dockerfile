FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 atlas

COPY services/common /app/services/common
RUN pip install --no-cache-dir -e /app/services/common

COPY services/risk-model /app/services/risk-model
WORKDIR /app/services/risk-model
# The service writes its trained artifact into ./artifacts at runtime, so that
# tree has to belong to the unprivileged user before privileges are dropped.
# torch from the CPU-only index: the default wheel pulls ~2.5GB of CUDA libraries
# this model never uses, which is the difference between a fast build and a
# timing-out one. Matches render.yaml.
RUN pip install --no-cache-dir "torch>=2.2" --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -e . \
    && mkdir -p artifacts \
    && chown -R atlas:atlas /app

USER atlas

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
