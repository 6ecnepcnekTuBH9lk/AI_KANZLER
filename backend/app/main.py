import logging
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import ROOT, Settings
from app.core.database import make_database
from app.core.exceptions import BusinessError
from app.core.jobs import JobExecutor
from app.modules.merchandise.router import router as merchandise_router
from app.modules.merchandise.service import run as merchandise_run
from app.modules.tnved.router import router as tnved_router
from app.modules.tnved.service import run as tnved_run
from app.shared.api import router as shared_router
from app.shared.files import FileService


def create_app(settings=None, services=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(settings.data_dir / "platform.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.getLogger().addHandler(handler)
        engine, sessions = make_database(settings)
        # Programmatic migration uses this app's connection, including isolated test databases.
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "backend/migrations"))
        with engine.begin() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
        app.state.settings, app.state.sessions = settings, sessions
        app.state.files = FileService(settings, sessions)
        app.state.jobs = JobExecutor(
            settings, sessions, services or {"tnved": tnved_run, "merchandise": merchandise_run}
        )
        app.state.jobs.recover()
        yield
        app.state.jobs.close()
        engine.dispose()
        logging.getLogger().removeHandler(handler)
        handler.close()

    app = FastAPI(title="KANZLER Business Platform", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(BusinessError)
    async def business_error(request, exc):
        return JSONResponse(status_code=422, content={"message": exc.message, "details": exc.details})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            status_code=422, content={"message": "Проверьте формат и обязательные поля запроса."}
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logging.getLogger(__name__).exception("Request failed", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"message": "Внутренняя ошибка приложения. Подробности сохранены в журнале."},
        )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/settings")
    def app_settings(request: Request):
        return {
            "version": "0.1.0",
            "storage": "SQLite" if settings.database_url.startswith("sqlite") else "Внешняя БД",
            "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
            "workers": settings.workers,
            "modules": ["Коммерческая аналитика", "Коды ТН ВЭД"],
            "alta_source": "https://www.alta.ru/tnved/",
            "resources": [
                "Управление ассортиментом.docx",
                "ОЗ25 продажи по неделям (по группам-видам).xlsx",
                "ОЗ25 продажи по неделям (по-артикульно).xlsx",
                "Анализ продаж ОЗ 25 на  02.03.2026.xlsx",
            ],
        }

    app.include_router(shared_router)
    app.include_router(tnved_router)
    app.include_router(merchandise_router)
    dist = ROOT / "frontend/dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html")
        return JSONResponse(
            {"message": "Backend запущен. Соберите frontend или откройте Vite на порту 5173."}
        )

    return app


app = create_app()
