import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Game, Prediction, PredictionAccuracy, Team
from app.schemas.accuracy import (
    AccuracyBySportItem,
    AccuracyBySportResponse,
    AccuracyByTypeItem,
    AccuracyByTypeResponse,
    AccuracyOverviewResponse,
    AccuracyTrendPoint,
    AccuracyTrendResponse,
    CalibrationBucket,
    CalibrationResponse,
    CalibrationSportData,
    RecentPredictionResult,
)

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
ALL_SPORTS = ["NBA", "NHL", "MLB", "NCAAB", "NCAAF", "NFL"]


def _get_model_accuracy(sport: str | None = None) -> float | None:
    """Read cross-validation accuracy from training metrics JSON files.

    If sport is None, returns the weighted average across all sports.
    """
    if sport:
        path = MODELS_DIR / f"{sport}_training_metrics.json"
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
        return round(data.get("accuracy", 0) * 100, 1)

    # Weighted average across all sports
    total_samples = 0
    weighted_sum = 0.0
    for s in ALL_SPORTS:
        path = MODELS_DIR / f"{s}_training_metrics.json"
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        samples = data.get("training_samples", 0)
        acc = data.get("accuracy", 0)
        total_samples += samples
        weighted_sum += samples * acc

    if total_samples == 0:
        return None
    return round(weighted_sum / total_samples * 100, 1)

router = APIRouter(prefix="/api/v1/accuracy", tags=["accuracy"])


@router.get("", response_model=AccuracyOverviewResponse)
async def get_accuracy_overview(
    sport: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(
        func.count(PredictionAccuracy.id).label("total"),
        func.sum(case((PredictionAccuracy.was_correct, 1), else_=0)).label("correct"),
        func.avg(func.abs(PredictionAccuracy.total_score_error)).label("avg_score_error"),
        func.avg(func.abs(PredictionAccuracy.spread_error)).label("avg_spread_error"),
        func.count(func.distinct(PredictionAccuracy.game_id)).label("games_predicted"),
    )

    if sport:
        query = query.where(PredictionAccuracy.sport == sport)

    result = await db.execute(query)
    row = result.one()

    total = row.total or 0
    correct = row.correct or 0

    return AccuracyOverviewResponse(
        total_predictions=total,
        correct_predictions=correct,
        accuracy_pct=round(correct / total * 100, 1) if total > 0 else 0.0,
        avg_score_error=round(float(row.avg_score_error or 0), 1),
        avg_spread_error=round(float(row.avg_spread_error or 0), 1),
        games_predicted=row.games_predicted or 0,
        model_accuracy=_get_model_accuracy(sport),
    )


@router.get("/by-sport", response_model=AccuracyBySportResponse)
async def get_accuracy_by_sport(db: AsyncSession = Depends(get_db)):
    query = select(
        PredictionAccuracy.sport,
        func.count(PredictionAccuracy.id).label("total"),
        func.sum(case((PredictionAccuracy.was_correct, 1), else_=0)).label("correct"),
    ).group_by(PredictionAccuracy.sport)

    result = await db.execute(query)
    rows = result.all()

    items = []
    for row in rows:
        total = row.total or 0
        correct = row.correct or 0
        items.append(
            AccuracyBySportItem(
                sport=row.sport,
                total=total,
                correct=correct,
                accuracy_pct=round(correct / total * 100, 1) if total > 0 else 0.0,
                model_accuracy=_get_model_accuracy(row.sport),
            )
        )

    # Include sports that have model accuracy but no live predictions yet
    existing_sports = {item.sport for item in items}
    for s in ALL_SPORTS:
        if s not in existing_sports:
            model_acc = _get_model_accuracy(s)
            if model_acc is not None:
                items.append(
                    AccuracyBySportItem(
                        sport=s,
                        total=0,
                        correct=0,
                        accuracy_pct=0.0,
                        model_accuracy=model_acc,
                    )
                )

    return AccuracyBySportResponse(by_sport=items)


@router.get("/by-type", response_model=AccuracyByTypeResponse)
async def get_accuracy_by_type(
    sport: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if sport:
        filters.append(PredictionAccuracy.sport == sport)

    base = select(PredictionAccuracy)
    if filters:
        base = base.where(and_(*filters))

    # Win/Loss accuracy
    wl_query = select(
        func.count(PredictionAccuracy.id).label("total"),
        func.sum(case((PredictionAccuracy.was_correct, 1), else_=0)).label("correct"),
    )
    if filters:
        wl_query = wl_query.where(and_(*filters))
    wl_result = await db.execute(wl_query)
    wl_row = wl_result.one()
    wl_total = wl_row.total or 0
    wl_correct = wl_row.correct or 0

    # Score accuracy (MAE)
    score_query = select(
        func.avg(func.abs(PredictionAccuracy.total_score_error)).label("avg_error"),
    )
    if filters:
        score_query = score_query.where(and_(*filters))
    score_result = await db.execute(score_query)
    score_row = score_result.one()

    # Spread accuracy
    spread_query = select(
        func.avg(func.abs(PredictionAccuracy.spread_error)).label("avg_error"),
    )
    if filters:
        spread_query = spread_query.where(and_(*filters))
    spread_result = await db.execute(spread_query)
    spread_row = spread_result.one()

    return AccuracyByTypeResponse(
        by_type=[
            AccuracyByTypeItem(
                prediction_type="Win/Loss",
                accuracy_pct=round(wl_correct / wl_total * 100, 1) if wl_total > 0 else 0.0,
                avg_error=0.0,
            ),
            AccuracyByTypeItem(
                prediction_type="Score",
                accuracy_pct=0.0,
                avg_error=round(float(score_row.avg_error or 0), 1),
            ),
            AccuracyByTypeItem(
                prediction_type="Spread",
                accuracy_pct=0.0,
                avg_error=round(float(spread_row.avg_error or 0), 1),
            ),
        ]
    )


@router.get("/trend", response_model=AccuracyTrendResponse)
async def get_accuracy_trend(
    sport: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    game_date = func.date(Game.game_date).label("game_date")
    query = (
        select(
            game_date,
            func.count(PredictionAccuracy.id).label("total"),
            func.sum(case((PredictionAccuracy.was_correct, 1), else_=0)).label("correct"),
        )
        .join(Game, PredictionAccuracy.game_id == Game.id)
        .group_by(game_date)
        .order_by(game_date)
    )

    if sport:
        query = query.where(PredictionAccuracy.sport == sport)

    result = await db.execute(query)
    rows = result.all()

    trend = []
    for row in rows:
        total = row.total or 0
        correct = row.correct or 0
        trend.append(
            AccuracyTrendPoint(
                date=str(row.game_date),
                accuracy_pct=round(correct / total * 100, 1) if total > 0 else 0.0,
                total=total,
            )
        )

    return AccuracyTrendResponse(trend=trend)


@router.get("/recent", response_model=list[RecentPredictionResult])
async def get_recent_predictions(
    sport: str | None = Query(None),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(PredictionAccuracy, Prediction, Game)
        .join(Prediction, PredictionAccuracy.prediction_id == Prediction.id)
        .join(Game, PredictionAccuracy.game_id == Game.id)
        .order_by(Game.game_date.desc())
        .limit(limit)
    )

    if sport:
        query = query.where(PredictionAccuracy.sport == sport)

    result = await db.execute(query)
    rows = result.all()

    results = []
    for acc, pred, game in rows:
        home_team = await db.get(Team, game.home_team_id)
        away_team = await db.get(Team, game.away_team_id)
        predicted_winner = await db.get(Team, pred.predicted_winner_id)

        actual_winner = home_team if (game.home_score or 0) > (game.away_score or 0) else away_team

        results.append(
            RecentPredictionResult(
                game_id=game.id,
                game_date=game.game_date.strftime("%Y-%m-%d"),
                home_team=home_team.abbreviation if home_team else "???",
                away_team=away_team.abbreviation if away_team else "???",
                predicted_winner=predicted_winner.abbreviation if predicted_winner else "???",
                actual_winner=actual_winner.abbreviation if actual_winner else "???",
                was_correct=acc.was_correct,
                predicted_score=f"{pred.predicted_home_score:.0f}-{pred.predicted_away_score:.0f}",
                actual_score=f"{game.home_score or 0}-{game.away_score or 0}",
                score_error=abs(acc.total_score_error),
            )
        )

    return results


@router.get("/calibration", response_model=CalibrationResponse)
async def get_calibration(db: AsyncSession = Depends(get_db)):
    """Return prediction accuracy bucketed by confidence level for each sport."""
    # Join PredictionAccuracy with Prediction to get win_probability
    query = select(
        PredictionAccuracy.sport,
        PredictionAccuracy.was_correct,
        Prediction.win_probability,
    ).join(Prediction, PredictionAccuracy.prediction_id == Prediction.id)

    result = await db.execute(query)
    rows = result.all()

    # Group by sport, then bucket by confidence
    from collections import defaultdict

    sport_buckets: dict[str, dict[int, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"correct": 0, "total": 0})
    )

    for sport, was_correct, win_prob in rows:
        # Convert to favored-team confidence (always >= 0.5)
        confidence = max(win_prob, 1.0 - win_prob)
        # Bucket into 5% ranges: 50-54% -> 50, 55-59% -> 55, etc.
        bucket = min(int(confidence * 100) // 5 * 5, 95)
        sport_buckets[sport][bucket]["total"] += 1
        if was_correct:
            sport_buckets[sport][bucket]["correct"] += 1

    sports_data = []
    for sport in ALL_SPORTS:
        if sport not in sport_buckets:
            continue

        buckets_dict = sport_buckets[sport]
        overall_correct = 0
        overall_total = 0
        buckets = []

        for bucket_start in range(50, 100, 5):
            data = buckets_dict.get(bucket_start, {"correct": 0, "total": 0})
            correct = data["correct"]
            total = data["total"]
            overall_correct += correct
            overall_total += total

            if total > 0:
                buckets.append(
                    CalibrationBucket(
                        bucket_label=f"{bucket_start}-{bucket_start + 4}%",
                        bucket_midpoint=bucket_start + 2.5,
                        correct=correct,
                        total=total,
                        accuracy_pct=round(correct / total * 100, 1),
                    )
                )

        if overall_total > 0:
            sports_data.append(
                CalibrationSportData(
                    sport=sport,
                    overall_correct=overall_correct,
                    overall_total=overall_total,
                    overall_accuracy_pct=round(
                        overall_correct / overall_total * 100, 1
                    ),
                    buckets=buckets,
                )
            )

    return CalibrationResponse(sports=sports_data)
