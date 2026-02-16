import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.post("/refresh-data")
async def refresh_data(
    sport: str = "NBA",
    db: AsyncSession = Depends(get_db),
):
    from app.services.data_fetcher import DataFetcher

    fetcher = DataFetcher(db)
    await fetcher.fetch_and_store_teams(sport)
    await fetcher.fetch_and_store_games(sport, seasons=[2024])
    return {"status": "ok", "message": "Data refreshed"}


@router.post("/run-predictions")
async def run_predictions(
    sport: str = "NBA",
    db: AsyncSession = Depends(get_db),
):
    from app.models import Game
    from app.services.prediction_engine import PredictionEngine
    from sqlalchemy import select

    engine = PredictionEngine()
    query = select(Game).where(Game.sport == sport, Game.status == "scheduled")
    result = await db.execute(query)
    games = result.scalars().all()

    await engine.predict_games_batch(games, db)
    return {"status": "ok", "predictions_generated": len(games)}


@router.post("/evaluate-accuracy")
async def evaluate_accuracy(
    sport: str = "NBA",
    db: AsyncSession = Depends(get_db),
):
    from app.services.accuracy_tracker import AccuracyTracker

    tracker = AccuracyTracker(db)
    count = await tracker.evaluate_completed_games(sport)
    return {"status": "ok", "evaluated": count}


@router.post("/train-model")
async def train_model(
    sport: str = "NBA",
    db: AsyncSession = Depends(get_db),
):
    from app.services.model_trainer import ModelTrainer

    trainer = ModelTrainer()
    metrics = await trainer.train(sport, db)
    return {"status": "ok", "metrics": metrics}


@router.post("/calculate-elos")
async def calculate_elos(
    sport: str = "NBA",
    db: AsyncSession = Depends(get_db),
):
    from app.services.elo_calculator import EloCalculator

    calculator = EloCalculator(db)
    await calculator.calculate_all_elos(sport)
    return {"status": "ok", "message": "ELO ratings calculated"}
