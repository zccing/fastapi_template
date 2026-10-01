import json
import os
import subprocess
import sys

import httpx
import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from src import database
from src.config import settings
from src.constants import Environment
from src.main import app


async def test_healthcheck_allows_configured_origin_only() -> None:
    assert app.title == "FastAPI Template API"
    assert app.version == settings.APP_VERSION
    assert app.root_path == settings.ROOT_PATH

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/healthcheck",
            headers={"Origin": "http://localhost:3000"},
        )
        denied = await client.get(
            "/healthcheck",
            headers={"Origin": "https://evil.example"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


async def test_cors_allows_head_preflight() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/healthcheck",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "HEAD",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "HEAD" in response.headers["access-control-allow-methods"]


@pytest.mark.parametrize("fail", (False, True))
async def test_lifespan_disposes_engine_even_on_failure(fail: bool) -> None:
    disposed: list[Engine] = []
    record_disposal = disposed.append
    event.listen(database.engine.sync_engine, "engine_disposed", record_disposal)
    try:
        if fail:
            with pytest.raises(RuntimeError, match="application failure"):
                async with app.router.lifespan_context(app):
                    raise RuntimeError("application failure")
        else:
            async with app.router.lifespan_context(app):
                pass
    finally:
        event.remove(database.engine.sync_engine, "engine_disposed", record_disposal)

    assert disposed == [database.engine.sync_engine]


@pytest.mark.parametrize("environment", tuple(Environment))
def test_documentation_follows_environment(environment: Environment) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio
import json
import httpx
from src.main import app

async def check():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        paths = ('/docs', '/redoc', '/openapi.json')
        statuses = [(await client.get(path)).status_code for path in paths]
    print(json.dumps({'statuses': statuses, 'root_path': app.root_path, 'debug': app.debug}))

asyncio.run(check())
""",
        ],
        env={**os.environ, "ENVIRONMENT": environment.value, "ROOT_PATH": "/gateway"},
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )

    expected_status = 404 if environment is Environment.PRODUCTION else 200
    assert json.loads(result.stdout) == {
        "statuses": [expected_status] * 3,
        "root_path": "/gateway",
        "debug": False,
    }
