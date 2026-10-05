FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl libpq-dev gcc && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 atlas

COPY services/common /app/services/common
RUN pip install --no-cache-dir -e /app/services/common

COPY services/finance-service /app/services/finance-service
WORKDIR /app/services/finance-service
RUN pip install --no-cache-dir -e . psycopg2-binary \
    && chown -R atlas:atlas /app

# Drop to an unprivileged uid: the service binds a high port and never writes
# outside /app, so root buys nothing and a container escape would start from uid 0.
USER atlas

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
