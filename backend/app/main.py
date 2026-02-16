import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.jobs.scheduler import scheduler, setup_scheduler
from app.routers import accuracy, admin, games, teams

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_scheduler()
    scheduler.start()
    logging.getLogger(__name__).info("Scheduler started")
    yield
    scheduler.shutdown()
    logging.getLogger(__name__).info("Scheduler shut down")


app = FastAPI(
    title="SportsSignal API",
    version="0.1.0",
    description="Sports prediction analytics",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games.router)
app.include_router(teams.router)
app.include_router(accuracy.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
