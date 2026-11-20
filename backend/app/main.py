from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import router
from app.core.config import Settings
from app.core.database import create_engine, create_session_factory
from app.core.keitaro import KeitaroClient
from app.core.logging import setup_logging

settings = Settings()  # type: ignore[call-arg]
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = create_engine(database_url=settings.database_url)
    app.state.settings = settings
    app.state.session_factory = create_session_factory(engine=engine)
    app.state.keitaro = KeitaroClient(
        base_url=settings.keitaro_api_url,
        api_token=settings.keitaro_api_token,
        timeout=settings.keitaro_timeout,
    )
    yield
    await app.state.keitaro.aclose()
    await engine.dispose()


app = FastAPI(title="adrobot backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
register_exception_handlers(app)
