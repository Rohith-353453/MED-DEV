import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager

from sqlalchemy import select, update

from app.config import get_settings
from app.telemetry import configure_telemetry

settings = get_settings()
configure_telemetry()

from fastapi import FastAPI  # noqa: E402 - telemetry configured before framework import
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.db import Base, SessionLocal, engine
from app import models  # noqa: F401 - register SQLAlchemy models before metadata setup
from app.models import Document
from app.routers import documents, fhir, profiles, timeline
from app.services.pipeline import process_document
from app.services.queue import close_document_queue
from app.services.storage import close_storage


_processing_tasks: set[asyncio.Task[None]] = set()


def _track_processing_task(document_id: str) -> None:
    task = asyncio.create_task(process_document(document_id))
    _processing_tasks.add(task)
    task.add_done_callback(_processing_tasks.discard)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_deployment_security()
    if settings.auto_create_schema and settings.app_env.lower() in {"local", "development", "test"}:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    if settings.queue_provider == "local":
        # Local background tasks can be interrupted by a process restart. Requeue their
        # durable records so they resume when the development server comes back up.
        async with SessionLocal() as session:
            await session.execute(
                update(Document)
                .where(Document.status == "processing")
                .values(status="queued", processing_error=None)
            )
            await session.commit()
            pending = await session.scalars(
                select(Document.id).where(Document.status == "queued")
            )
            for document_id in pending:
                _track_processing_task(document_id)
    yield
    tasks = tuple(_processing_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks)
    await close_document_queue()
    await close_storage()
    await engine.dispose()


app = FastAPI(
    title="Carefolio Health Copilot API",
    description="Private document organization and cautious health information summaries.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(profiles.router, prefix=settings.api_prefix)
app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(timeline.router, prefix=settings.api_prefix)
app.include_router(fhir.router, prefix=settings.api_prefix)


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def ready() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.exec_driver_sql("SELECT 1")
    return {"status": "ready"}
