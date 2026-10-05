FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 atlas

COPY services/common /app/services/common
RUN pip install --no-cache-dir -e /app/services/common

COPY mcp-server /app/mcp-server
WORKDIR /app/mcp-server
RUN pip install --no-cache-dir -e . \
    && chown -R atlas:atlas /app

USER atlas

EXPOSE 8003

CMD ["uvicorn", "atlas_mcp_server.server:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "4"]
