import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Prediction, PredictionAccuracy

logger = logging.getLogger(__name__)


class AccuracyTracker:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def evaluate_completed_games(self, sport: str) -> int:
        """Evaluate predictions for newly completed games. Returns count of evaluated."""
        # Auto-fix: mark games with real scores as Final if still scheduled
        fix_result = await self.db.execute(
            update(Game)
            .where(
                Game.sport == sport,
                Game.status != "Final",
                Game.home_score.isnot(None),
                Game.away_score.isnot(None),
                (Game.home_score + Game.away_score) > 0,
            )
            .returning(Game.id)
        )
        fixed = fix_result.all()
        if fixed:
            logger.info("Auto-fixed %d %s games to Final status", len(fixed), sport)

        # Find predictions for completed games that don't have an accuracy record yet
        existing_accuracy_ids = (
            select(PredictionAccuracy.prediction_id)
        ).scalar_subquery()

        result = await self.db.execute(
            select(Prediction, Game)
            .join(Game, Prediction.game_id == Game.id)
            .where(
                Game.status == "Final",
                Game.sport == sport,
                Prediction.id.notin_(existing_accuracy_ids),
                # Only evaluate predictions made BEFORE the game was played.
                # Predictions generated after a game completes are in-sample
                # and would artificially inflate accuracy.
                Prediction.prediction_date < Game.game_date,
            )
        )
        rows = result.all()

        if not rows:
            logger.info("No new completed games to evaluate for sport=%s", sport)
            return 0

        accuracy_records: list[PredictionAccuracy] = []

        for prediction, game in rows:
            if game.home_score is None or game.away_score is None:
                continue
            # Skip games where both scores are 0 (future games with default values)
            if game.home_score == 0 and game.away_score == 0:
                continue

            # Determine actual winner
            actual_winner_id = (
                game.home_team_id
                if game.home_score > game.away_score
                else game.away_team_id
            )

            was_correct = prediction.predicted_winner_id == actual_winner_id

            home_score_error = prediction.predicted_home_score - game.home_score
            away_score_error = prediction.predicted_away_score - game.away_score

            predicted_total = (
                prediction.predicted_home_score + prediction.predicted_away_score
            )
            actual_total = game.home_score + game.away_score
            total_score_error = predicted_total - actual_total

            actual_spread = game.home_score - game.away_score
            spread_error = prediction.predicted_spread - actual_spread

            accuracy_records.append(
                PredictionAccuracy(
                    prediction_id=prediction.id,
                    game_id=game.id,
                    sport=sport,
                    was_correct=was_correct,
                    home_score_error=home_score_error,
                    away_score_error=away_score_error,
                    total_score_error=total_score_error,
                    spread_error=spread_error,
                )
            )

        if accuracy_records:
            self.db.add_all(accuracy_records)
            await self.db.flush()

        logger.info(
            "Evaluated %d predictions for sport=%s", len(accuracy_records), sport
        )
        return len(accuracy_records)

    async def get_accuracy_overview(self, sport: str | None = None) -> dict:
        """Get an overview of prediction accuracy, optionally filtered by sport."""
        filters = []
        if sport is not None:
            filters.append(PredictionAccuracy.sport == sport)

        # Total predictions
        total_result = await self.db.execute(
            select(func.count(PredictionAccuracy.id)).where(*filters)
        )
        total_predictions = total_result.scalar() or 0

        # Correct predictions
        correct_result = await self.db.execute(
            select(func.count(PredictionAccuracy.id)).where(
                PredictionAccuracy.was_correct == True,  # noqa: E712
                *filters,
            )
        )
        correct_predictions = correct_result.scalar() or 0

        # Distinct games predicted
        games_result = await self.db.execute(
            select(func.count(func.distinct(PredictionAccuracy.game_id))).where(
                *filters
            )
        )
        games_predicted = games_result.scalar() or 0

        # Accuracy percentage
        accuracy_pct = (
            (correct_predictions / total_predictions * 100.0)
            if total_predictions > 0
            else 0.0
        )

        # Average score error (MAE of individual score predictions)
        score_error_result = await self.db.execute(
            select(
                func.avg(
                    (
                        func.abs(PredictionAccuracy.home_score_error)
                        + func.abs(PredictionAccuracy.away_score_error)
                    )
                    / 2.0
                )
            ).where(*filters)
        )
        avg_score_error = score_error_result.scalar() or 0.0

        # Average spread error
        spread_error_result = await self.db.execute(
            select(func.avg(func.abs(PredictionAccuracy.spread_error))).where(
                *filters
            )
        )
        avg_spread_error = spread_error_result.scalar() or 0.0

        return {
            "total_predictions": total_predictions,
            "correct_predictions": correct_predictions,
            "accuracy_pct": round(float(accuracy_pct), 2),
            "avg_score_error": round(float(avg_score_error), 2),
            "avg_spread_error": round(float(avg_spread_error), 2),
            "games_predicted": games_predicted,
        }
