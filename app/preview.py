from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.config import Settings, load_settings
from app.main import create_app as create_api


class ReaderBuild(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        if any(part.startswith(".") for part in path.replace("\\", "/").split("/") if part != "."):
            raise HTTPException(404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            accepts_html = "text/html" in Headers(scope=scope).get("accept", "")
            if error.status_code != 404 or not accepts_html or "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings | None = None) -> Starlette:
    config = settings or load_settings()
    if config.reader_dist is None or not (config.reader_dist / "index.html").is_file():
        raise ValueError("Set READER_DIST to the built Pathya reader directory.")
    if config.auth_mode != "session":
        raise ValueError("Use session authentication for the shared reader preview.")
    reader_dir = config.reader_dist.resolve()
    if any(
        private.resolve().is_relative_to(reader_dir)
        for private in (config.pathya_data_dir, config.pathya_db_path, config.backup_dir)
        if private is not None
    ):
        raise ValueError(
            "Keep the database, data files and backups outside the public reader build."
        )
    api = create_api(config)

    @asynccontextmanager
    async def lifespan(application: Starlette) -> AsyncIterator[None]:
        async with api.router.lifespan_context(api):
            yield

    return Starlette(
        lifespan=lifespan,
        routes=[
            Mount("/api", app=api),
            Mount("/", app=ReaderBuild(directory=reader_dir, html=True)),
        ],
    )
