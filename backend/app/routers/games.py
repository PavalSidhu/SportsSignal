from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, cast, func, or_, select, Time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Game, Prediction, Team
from app.schemas.games import (
    FactorResponse,
    GameDetailResponse,
    GameListItem,
    GameListResponse,
    GameTeamResponse,
    HeadToHeadGame,
    PredictionDetailResponse,
    PredictionSummary,
    QuarterPredictions,
    TeamComparisonStat,
)
from app.schemas.teams import TeamResponse

router = APIRouter(prefix="/api/v1/games", tags=["games"])


@router.get("", response_model=GameListResponse)
async def list_games(
    sport: str = Query("NBA"),
    date: str | None = Query(None),
    status: str | None = Query(None),
    team_id: int | None = Query(None),
    limit: int = Query(100, le=200),
    offset: int = Query(0),
    tz_offset: float = Query(-5, description="User's UTC offset in hours (e.g. -8 for Pacific)"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Game).options(
        selectinload(Game.home_team),
        selectinload(Game.away_team),
        selectinload(Game.predictions),
    )

    filters = [Game.sport == sport]
    if date:
        # Game dates are stored as approximate US Eastern (UTC-5h).
        # Shift the filter window so users in other timezones see games
        # that fall on the requested calendar date in *their* local time.
        game_date = datetime.strptime(date, "%Y-%m-%d")
        shift = timedelta(hours=(tz_offset - (-5)))  # e.g. Pacific: -8 - (-5) = -3h
        start = game_date - shift
        end = start + timedelta(days=1)
        filters.append(Game.game_date >= start)
        filters.append(Game.game_date < end)
    if status:
        filters.append(Game.status == status)
    if team_id:
        filters.append(
            or_(Game.home_team_id == team_id, Game.away_team_id == team_id)
        )

    query = query.where(and_(*filters))
    count_query = select(func.count()).select_from(
        query.subquery()
    )
    total = (await db.execute(count_query)).scalar() or 0

    # Sort games with known times first, then unknown-time games (midnight
    # hour) at the end.  Games stored between 00:00–00:59 have no real
    # start time from ESPN.
    from datetime import time as dt_time
    midnight_flag = case(
        (cast(Game.game_date, Time) < dt_time(1, 0), 1),
        else_=0,
    )
    query = query.order_by(midnight_flag, Game.game_date.asc()).offset(offset).limit(limit)
    result = await db.execute(query)
    games = result.scalars().unique().all()

    items = []
    for game in games:
        prediction = None
        if game.predictions:
            # Use the most recent prediction (highest id = latest)
            p = max(game.predictions, key=lambda pred: pred.id)
            prediction = PredictionSummary(
                win_probability=p.win_probability,
                predicted_winner_id=p.predicted_winner_id,
                predicted_home_score=p.predicted_home_score,
                predicted_away_score=p.predicted_away_score,
                confidence=p.confidence,
            )

        items.append(
            GameListItem(
                id=game.id,
                external_id=game.external_id,
                sport=game.sport,
                season=game.season,
                game_date=game.game_date.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
                status=game.status,
                is_postseason=game.is_postseason,
                home_team=GameTeamResponse.model_validate(game.home_team),
                away_team=GameTeamResponse.model_validate(game.away_team),
                home_score=game.home_score,
                away_score=game.away_score,
                prediction=prediction,
            )
        )

    return GameListResponse(games=items, total=total)


@router.get("/{game_id}", response_model=GameDetailResponse)
async def get_game(game_id: int, db: AsyncSession = Depends(get_db)):
    query = (
        select(Game)
        .where(Game.id == game_id)
        .options(
            selectinload(Game.home_team),
            selectinload(Game.away_team),
            selectinload(Game.predictions),
        )
    )
    result = await db.execute(query)
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    predictions = []
    for p in game.predictions:
        quarters = None
        if p.quarter_predictions:
            quarters = QuarterPredictions(**p.quarter_predictions)

        factors = []
        if p.key_factors:
            factors = [FactorResponse(**f) for f in p.key_factors]

        predictions.append(
            PredictionDetailResponse(
                id=p.id,
                win_probability=p.win_probability,
                confidence=p.confidence,
                predicted_winner_id=p.predicted_winner_id,
                predicted_home_score=p.predicted_home_score,
                predicted_away_score=p.predicted_away_score,
                predicted_spread=p.predicted_spread,
                predicted_total=p.predicted_total,
                quarter_predictions=quarters,
                key_factors=factors,
            )
        )

    # Head-to-head games
    h2h_query = (
        select(Game)
        .where(
            and_(
                Game.status == "Final",
                or_(
                    and_(
                        Game.home_team_id == game.home_team_id,
                        Game.away_team_id == game.away_team_id,
                    ),
                    and_(
                        Game.home_team_id == game.away_team_id,
                        Game.away_team_id == game.home_team_id,
                    ),
                ),
            )
        )
        .options(selectinload(Game.home_team), selectinload(Game.away_team))
        .order_by(Game.game_date.desc())
        .limit(5)
    )
    h2h_result = await db.execute(h2h_query)
    h2h_games = h2h_result.scalars().unique().all()

    head_to_head = []
    for h in h2h_games:
        winner = h.home_team if (h.home_score or 0) > (h.away_score or 0) else h.away_team
        head_to_head.append(
            HeadToHeadGame(
                game_date=h.game_date.strftime("%Y-%m-%d"),
                home_team_abbreviation=h.home_team.abbreviation,
                away_team_abbreviation=h.away_team.abbreviation,
                home_score=h.home_score or 0,
                away_score=h.away_score or 0,
                winner_abbreviation=winner.abbreviation,
            )
        )

    # Team comparison stats
    team_comparison = await _compute_team_comparison(
        game.home_team_id, game.away_team_id, game.sport, db
    )

    return GameDetailResponse(
        id=game.id,
        external_id=game.external_id,
        sport=game.sport,
        season=game.season,
        game_date=game.game_date.strftime("%Y-%m-%dT%H:%M:%S-05:00"),
        status=game.status,
        is_postseason=game.is_postseason,
        home_team=TeamResponse.model_validate(game.home_team),
        away_team=TeamResponse.model_validate(game.away_team),
        home_score=game.home_score,
        away_score=game.away_score,
        home_period_scores=game.home_period_scores,
        away_period_scores=game.away_period_scores,
        predictions=predictions,
        head_to_head=head_to_head,
        team_comparison=team_comparison,
    )


async def _compute_team_comparison(
    home_team_id: int, away_team_id: int, sport: str, db: AsyncSession
) -> list[TeamComparisonStat]:
    stats = []

    for label, team_id in [("home", home_team_id), ("away", away_team_id)]:
        # Get last 20 games
        games_query = (
            select(Game)
            .where(
                and_(
                    Game.sport == sport,
                    Game.status == "Final",
                    or_(
                        Game.home_team_id == team_id,
                        Game.away_team_id == team_id,
                    ),
                )
            )
            .order_by(Game.game_date.desc())
            .limit(20)
        )
        result = await db.execute(games_query)
        games = result.scalars().all()

        if not games:
            continue

        ppg = 0.0
        papg = 0.0
        wins = 0
        for g in games:
            if g.home_team_id == team_id:
                ppg += g.home_score or 0
                papg += g.away_score or 0
                if (g.home_score or 0) > (g.away_score or 0):
                    wins += 1
            else:
                ppg += g.away_score or 0
                papg += g.home_score or 0
                if (g.away_score or 0) > (g.home_score or 0):
                    wins += 1

        n = len(games)
        if label == "home":
            home_ppg = round(ppg / n, 1)
            home_papg = round(papg / n, 1)
            home_win_pct = round(wins / n * 100, 1)
        else:
            away_ppg = round(ppg / n, 1)
            away_papg = round(papg / n, 1)
            away_win_pct = round(wins / n * 100, 1)

    if "home_ppg" in dir() and "away_ppg" in dir():
        stats = [
            TeamComparisonStat(stat_name="Points Per Game", home_value=home_ppg, away_value=away_ppg),
            TeamComparisonStat(stat_name="Points Allowed", home_value=home_papg, away_value=away_papg),
            TeamComparisonStat(stat_name="Win %", home_value=home_win_pct, away_value=away_win_pct),
        ]

    return stats
