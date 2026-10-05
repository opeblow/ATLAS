FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 atlas

# Shared library first: it changes least often, so this layer stays cached across
# service-image rebuilds.
COPY services/common /app/services/common
RUN pip install --no-cache-dir -e /app/services/common

# Redis powers the shared rate-limit counter. Without it the in-process fallback
# is per-worker, which silently multiplies the configured limit by the worker
# count -- and the image runs multiple workers.
RUN pip install --no-cache-dir "redis>=5.0,<7"

COPY services/edge /app/services/edge
WORKDIR /app/services/edge
RUN pip install --no-cache-dir -e . \
    && chown -R atlas:atlas /app

USER atlas

EXPOSE 8000

# Single worker by design: the edge is I/O-bound proxying and a shared Redis
# counter already bounds the fleet. Override with PORT at runtime.
CMD ["uvicorn", "atlas_edge.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
