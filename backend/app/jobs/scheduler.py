import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import async_session
from app.utils.sport_config import get_all_sports, get_sport_config

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _fetch_games_for_sport(sport: str) -> None:
    """Fetch latest games for a single sport."""
    async with async_session() as db:
        try:
            from app.services.data_fetcher import DataFetcher

            config = get_sport_config(sport)
            current_season = config.seasons[-1] if config.seasons else 2024
            fetcher = DataFetcher(db)
            await fetcher.fetch_and_store_games(sport, seasons=[current_season])
            await db.commit()
            logger.info("Fetch games completed for %s", sport)
        except Exception:
            logger.exception("Fetch games failed for %s", sport)
            await db.rollback()


async def fetch_games_job():
    """Fetch games for all configured sports with staggered timing."""
    logger.info("Running scheduled job: fetch_games (all sports)")
    for sport in get_all_sports():
        await _fetch_games_for_sport(sport)
        await asyncio.sleep(30)  # Stagger to respect rate limits


async def _seed_boxscores_for_sport(sport: str) -> None:
    """Fetch boxscores for completed games missing them."""
    async with async_session() as db:
        try:
            from app.services.data_fetcher import DataFetcher

            fetcher = DataFetcher(db)
            stored = await fetcher.fetch_and_store_boxscores(sport, season=None)
            logger.info("Seeded %d boxscore records for %s", stored, sport)
        except Exception:
            logger.exception("Seed boxscores failed for %s", sport)
            await db.rollback()


async def seed_boxscores_job():
    """Seed boxscores for all sports."""
    logger.info("Running scheduled job: seed_boxscores (all sports)")
    for sport in get_all_sports():
        await _seed_boxscores_for_sport(sport)
        await asyncio.sleep(5)


async def _compute_rolling_stats_for_sport(sport: str) -> None:
    """Recompute rolling stats for a single sport."""
    async with async_session() as db:
        try:
            from app.services.rolling_stats_computer import RollingStatsComputer

            computer = RollingStatsComputer(db)
            count = await computer.compute_all(sport)
            logger.info("Computed %d rolling stat records for %s", count, sport)
        except Exception:
            logger.exception("Compute rolling stats failed for %s", sport)
            await db.rollback()


async def compute_rolling_stats_job():
    """Compute rolling stats for all sports."""
    logger.info("Running scheduled job: compute_rolling_stats (all sports)")
    for sport in get_all_sports():
        await _compute_rolling_stats_for_sport(sport)


async def _update_elos_for_sport(sport: str) -> None:
    """Update ELO ratings for a single sport."""
    async with async_session() as db:
        try:
            from app.services.elo_calculator import EloCalculator

            calculator = EloCalculator(db, sport)
            await calculator.calculate_all_elos(sport)
            await db.commit()
            logger.info("ELO update completed for %s", sport)
        except Exception:
            logger.exception("ELO update failed for %s", sport)
            await db.rollback()


async def update_elos_job():
    """Update ELO ratings for all sports."""
    logger.info("Running scheduled job: update_elos (all sports)")
    for sport in get_all_sports():
        await _update_elos_for_sport(sport)


async def _generate_predictions_for_sport(sport: str) -> None:
    """Generate predictions for a single sport."""
    async with async_session() as db:
        try:
            from sqlalchemy import select

            from app.models import Game
            from app.services.prediction_engine import PredictionEngine

            engine = PredictionEngine()
            query = select(Game).where(
                Game.sport == sport, Game.status == "scheduled"
            )
            result = await db.execute(query)
            games = list(result.scalars().all())
            if games:
                await engine.predict_games_batch(games, db)
                await db.commit()
            logger.info("Generated predictions for %d %s games", len(games), sport)
        except Exception:
            logger.exception("Generate predictions failed for %s", sport)
            await db.rollback()


async def generate_predictions_job():
    """Generate predictions for all sports."""
    logger.info("Running scheduled job: generate_predictions (all sports)")
    for sport in get_all_sports():
        await _generate_predictions_for_sport(sport)


async def _evaluate_accuracy_for_sport(sport: str) -> None:
    """Evaluate prediction accuracy for a single sport."""
    async with async_session() as db:
        try:
            from app.services.accuracy_tracker import AccuracyTracker

            tracker = AccuracyTracker(db)
            await tracker.evaluate_completed_games(sport)
            await db.commit()
            logger.info("Evaluate accuracy completed for %s", sport)
        except Exception:
            logger.exception("Evaluate accuracy failed for %s", sport)
            await db.rollback()


async def evaluate_accuracy_job():
    """Evaluate accuracy for all sports."""
    logger.info("Running scheduled job: evaluate_accuracy (all sports)")
    for sport in get_all_sports():
        await _evaluate_accuracy_for_sport(sport)


def setup_scheduler():
    scheduler.add_job(fetch_games_job, "cron", hour=6, minute=0, id="fetch_games")
    scheduler.add_job(
        seed_boxscores_job, "cron", hour=6, minute=30, id="seed_boxscores"
    )
    scheduler.add_job(
        compute_rolling_stats_job, "cron", hour=6, minute=45, id="compute_rolling_stats"
    )
    scheduler.add_job(update_elos_job, "cron", hour=7, minute=0, id="update_elos")
    scheduler.add_job(
        generate_predictions_job, "cron", hour=8, minute=0, id="generate_predictions"
    )
    scheduler.add_job(
        evaluate_accuracy_job, "cron", hour=0, minute=0, id="evaluate_accuracy"
    )
