import httpx
from fastapi import FastAPI

from app import main


async def get(application, path):
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path)


def test_not_mounted_without_a_build(tmp_path):
    assert main.mount_frontend(FastAPI(), tmp_path) is False


async def test_serves_index_and_assets_without_shadowing_the_api(tmp_path):
    (tmp_path / "index.html").write_text("<h1>studio</h1>")
    (tmp_path / "app.js").write_text("console.log(1)")
    application = FastAPI()

    @application.get("/health")
    async def health():
        return {"status": "ok"}

    assert main.mount_frontend(application, tmp_path) is True

    assert "studio" in (await get(application, "/")).text
    assert (await get(application, "/app.js")).status_code == 200
    assert (await get(application, "/health")).json() == {"status": "ok"}
    assert (await get(application, "/missing")).status_code == 404


async def test_real_app_still_serves_docs_and_health():
    assert (await get(main.app, "/health")).status_code == 200
    assert (await get(main.app, "/openapi.json")).status_code == 200
