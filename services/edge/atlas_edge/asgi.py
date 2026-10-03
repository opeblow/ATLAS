"""Single-process ATLAS edge.

The four services are separate ASGI apps (that is the architecture, and
docker-compose still runs them as four containers). For a keyless demo deploy we
also need one public origin, so this module mounts all four under path prefixes
behind a single uvicorn:

    /finance/*   -> finance-service
    /schedule/*  -> scheduling-service
    /risk/*      -> risk-model
    /mcp/*       -> MCP server (Streamable HTTP)

Sub-services talk to each other over real HTTP, exactly as in the four-container
setup, so nothing about the request path is faked. MCP tools use async HTTP
clients, since these services share the event loop with the MCP server in this
process.

Run:  python -m atlas_edge.asgi        (or: uvicorn atlas_edge.asgi:app)

Env:
  PORT                     public port (Render sets this)
  ATLAS_SELF_URL           base URL sub-services call each other on
                           (default http://127.0.0.1:$PORT)
  ATLAS_DATABASE_URL       SQLite by default; set for Postgres
  ATLAS_SEED_ON_START=1    seed the u_demo dataset on a cold database
  ATLAS_SEED_RISK_PORT     loopback port for the pre-boot risk model (default 8900)
  ATLAS_MOCK_BEDROCK=1     route /api/ask through the local rule-based router
  ATLAS_REQUIRE_AUTH=0     disable bearer auth (demo only)
  ATLAS_CORS_ORIGINS       comma-separated frontend origins
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import time

from pydantic import BaseModel, ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Mount, Route

log = logging.getLogger("atlas.edge")

# The three service packages are all named `app`, so they cannot be imported into
# one interpreter by plain name. Each is loaded from its own directory under a
# distinct module name; `app.*` imports inside them still resolve because the
# service directory is on sys.path while that service is loaded.
_SERVICE_DIRS = {
    "finance": "services/finance-service",
    "scheduling": "services/scheduling-service",
    "risk": "services/risk-model",
}


def _repo_root() -> str:
    """Repo root, i.e. the directory holding services/ and mcp-server/.

    Resolved from this file (services/edge/atlas_edge/asgi.py) so it holds no
    matter which working directory the process was launched from.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


ROOT = _repo_root()


def _bootstrap() -> None:
    """Put every ATLAS package on sys.path before any imports happen."""
    for rel in (
        "services/common",
        "mcp-server/src",
        "reasoning/bedrock-orchestrator",
        *_SERVICE_DIRS.values(),
    ):
        path = os.path.join(ROOT, rel)
        if path not in sys.path:
            sys.path.insert(0, path)


_bootstrap()

os.environ.setdefault("ATLAS_DATABASE_URL", f"sqlite:///{ROOT.replace(os.sep, '/')}/atlas.db")

from atlas_common.config import settings  # noqa: E402
from atlas_common.db import init_db  # noqa: E402
from atlas_mcp_server.config import mcp_settings  # noqa: E402

init_db()


def _load_service(alias: str):
    """Import `services/<dir>` under a unique module name to dodge the `app` clash."""
    import importlib.util

    path = os.path.join(ROOT, _SERVICE_DIRS[alias])
    if path not in sys.path:
        sys.path.insert(0, path)

    # Give this service a uniquely named package alias, then import its main
    # module through that alias so three `app` packages can coexist.
    pkg_name = f"atlas_svc_{alias}"
    spec = importlib.util.spec_from_file_location(
        pkg_name, os.path.join(path, "app", "__init__.py"), submodule_search_locations=[os.path.join(path, "app")]
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load service package for {alias} at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = module
    spec.loader.exec_module(module)

    main = importlib.util.spec_from_file_location(
        f"{pkg_name}.main", os.path.join(path, "app", "main.py")
    )
    if main is None or main.loader is None:
        raise RuntimeError(f"cannot load app.main for {alias}")
    main_module = importlib.util.module_from_spec(main)
    sys.modules[f"{pkg_name}.main"] = main_module
    main.loader.exec_module(main_module)
    return main_module.app


class _StripPrefix:
    """ASGI shim that removes a mount prefix from scope["path"].

    Starlette's Mount leaves the full path in scope, but the MCP transport and
    its bearer gate both match on exact paths ("/mcp", "/health"). Stripping the
    prefix lets the mounted app behave exactly as it does standalone.
    """

    def __init__(self, app, prefix: str) -> None:
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and scope.get("path", "").startswith(self.prefix):
            rest = scope["path"][len(self.prefix):] or "/"
            scope = {**scope, "path": rest, "root_path": scope.get("root_path", "") + self.prefix}
        await self.app(scope, receive, send)


def _load_mcp() -> tuple[object, object]:
    """Return (wrapped ASGI app, underlying Starlette app for lifespan)."""
    from atlas_mcp_server.auth.bearer import BearerAuthMiddleware
    from atlas_mcp_server.server import mcp
    from atlas_mcp_server.transport.streamable_http import build_app

    inner = mcp.http_app(
        path=mcp_settings.streamable_http_path,
        transport="streamable-http",
    )
    return BearerAuthMiddleware(inner), inner


def _start_loopback(app, port: int) -> "threading.Thread":
    """Serve one sub-app on a real loopback port in a background thread.

    Needed because seeding runs before uvicorn binds, and the finance seeder
    ends with a risk computation that calls the risk model over real HTTP. A
    TestClient can't satisfy that call, so the risk model gets a genuine socket.
    """
    import threading

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name=f"atlas-loopback-{port}", daemon=True)
    thread.start()
    for _ in range(100):
        if getattr(server, "started", False):
            break
        time.sleep(0.1)
    return thread


def _seed(risk_app, risk_port: int) -> None:
    """Populate u_demo so a cold deploy never renders an empty dashboard."""
    from fastapi.testclient import TestClient

    from atlas_common.db import SessionLocal
    from atlas_common.models import Transaction

    db = SessionLocal()
    try:
        already = db.query(Transaction).count() > 0
    finally:
        db.close()
    if already:
        log.info("seed skipped: ledger already has rows")
        return

    from atlas_svc_finance.main import app as finance_app
    from atlas_svc_scheduling.main import app as scheduling_app

    risk = _start_loopback(risk_app, risk_port)

    # Point the risk pipeline at the loopback server for the duration of the
    # seed, then restore the single-origin URL used once uvicorn is up.
    previous = settings.risk_model_url
    settings.risk_model_url = f"http://127.0.0.1:{risk_port}"
    try:
        with TestClient(finance_app) as c:
            fin = c.post("/demo/seed")
        with TestClient(scheduling_app) as c:
            sch = c.post("/demo/seed")
        if fin.status_code != 200 or sch.status_code != 200:
            raise RuntimeError(f"seed returned {fin.status_code}/{sch.status_code}")
    finally:
        settings.risk_model_url = previous
        risk.join(timeout=2.0)

    log.info("seeded u_demo demo data (balance + deadlines + committed blocks)")


def _capability_report() -> dict:
    """What is live vs simulated, surfaced on /api/capabilities for the demo."""
    return {
        "bedrock": {
            "mode": "simulated" if settings.mock_bedrock else "live",
            "reason": "rule-based router (no AWS credentials configured)"
            if settings.mock_bedrock
            else "amazon bedrock converse",
        },
        "risk_model": {
            "mode": "trained",
            "note": "PyTorch MLP over 12 engineered features, committed artifact",
        },
        "database": {"mode": "sqlite" if settings.is_sqlite else "postgres", "url_scheme": settings.db_url.split(":")[0]},
        "cache": {"mode": "redis" if settings.redis_url else "in-process L1", "ttl_ms": 1500},
        "mcp_auth": {"mode": "bearer" if settings.require_auth else "disabled (demo)"},
    }


def create_app() -> Starlette:
    finance = _load_service("finance")
    scheduling = _load_service("scheduling")
    risk = _load_service("risk")
    mcp, mcp_inner = _load_mcp()

    port = os.getenv("PORT", "8000")
    base = os.getenv("ATLAS_SELF_URL", f"http://127.0.0.1:{port}").rstrip("/")

    if settings.seed_on_start:
        try:
            _seed(risk, int(os.getenv("ATLAS_SEED_RISK_PORT", "8900")))
        except Exception as exc:  # seeding must never block the boot
            log.warning("seed failed (continuing): %s", exc)

    # Self-referential service URLs so intra-stack HTTP calls resolve through
    # this same process instead of assuming four separate hosts.
    port = os.getenv("PORT", "8000")
    base = os.getenv("ATLAS_SELF_URL", f"http://127.0.0.1:{port}").rstrip("/")

    # Both the finance/scheduling services and the MCP tools resolve their peers
    # at import time from these settings objects, so all four URLs are rewritten
    # here (not only on `settings`) or intra-stack calls would keep pointing at
    # 127.0.0.1:8001 and fail on a single-origin deploy.
    port = os.getenv("PORT", "8000")
    base = os.getenv("ATLAS_SELF_URL", f"http://127.0.0.1:{port}").rstrip("/")
    for target in (settings, mcp_settings):
        target.finance_url = f"{base}/finance"
        target.scheduling_url = f"{base}/schedule"
    settings.risk_model_url = f"{base}/risk"

    async def root(_request):
        return RedirectResponse("/dashboard")

    # FastMCP's Streamable HTTP transport starts its session manager in an ASGI
    # lifespan handler. Starlette only runs the *outer* app's lifespan, so a
    # mounted MCP app would never initialise and every request would fail with
    # "Task group is not initialized". Forward lifespan events into it.
    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with mcp_inner.router.lifespan_context(mcp_inner):
            yield

    async def capabilities(_request):
        return JSONResponse(_capability_report())

    async def edge_health(_request):
        return JSONResponse({"status": "ok", "service": "atlas-edge"})

    class AskIn(BaseModel):
        utterance: str
        user_id: str = "u_demo"

    async def ask(request):
        """Drive one natural-language turn through the orchestrator.

        This is the HTTP front door for the same code the Alexa+ MCP surface uses.
        Without Bedrock credentials the orchestrator transparently routes via its
        local rule-based router and labels the reply as simulated, so the demo
        never implies a live AWS call.
        """
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse({"error": "expected a JSON body"}, status_code=400)

        try:
            body = AskIn(**payload)
        except ValidationError as exc:
            return JSONResponse({"error": exc.errors()}, status_code=422)

        if not body.utterance.strip():
            return JSONResponse({"error": "utterance must not be empty"}, status_code=422)

        def _run() -> dict:
            from orchestrator import bedrock, fallback

            try:
                return bedrock.think(body.utterance, user_id=body.user_id)
            except bedrock.BedrockUnavailable:
                return fallback.think(body.utterance, user_id=body.user_id)

        try:
            # Tool execution is blocking httpx work, so keep it off the loop.
            result = await run_in_threadpool(_run)
        except Exception as exc:
            log.exception("orchestrator turn failed")
            return JSONResponse({"error": str(exc)}, status_code=502)

        result.setdefault("simulated", bool(settings.mock_bedrock))
        return JSONResponse(result)

    return Starlette(
        routes=[
            Route("/", root),
            Route("/api/capabilities", capabilities),
            Route("/api/ask", ask, methods=["POST"]),
            Route("/edge/health", edge_health),
            Mount("/finance", app=finance),
            Mount("/schedule", app=scheduling),
            Mount("/risk", app=risk),
            Mount("/mcp", app=_StripPrefix(mcp, "/mcp")),
        ],
        lifespan=lifespan,
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=settings.cors_origins,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ],
    )


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "atlas_edge.asgi:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("ATLAS_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()