from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Team, TeamEloHistory
from app.schemas.teams import EloHistoryPoint, EloHistoryResponse, TeamResponse

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    sport: str = Query("NBA"),
    db: AsyncSession = Depends(get_db),
):
    query = select(Team).where(Team.sport == sport).order_by(Team.name)
    result = await db.execute(query)
    teams = result.scalars().all()
    return [TeamResponse.model_validate(t) for t in teams]


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(team_id: int, db: AsyncSession = Depends(get_db)):
    query = select(Team).where(Team.id == team_id)
    result = await db.execute(query)
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return TeamResponse.model_validate(team)


@router.get("/{team_id}/elo-history", response_model=EloHistoryResponse)
async def get_elo_history(team_id: int, db: AsyncSession = Depends(get_db)):
    team_query = select(Team).where(Team.id == team_id)
    result = await db.execute(team_query)
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    history_query = (
        select(TeamEloHistory)
        .where(TeamEloHistory.team_id == team_id)
        .order_by(TeamEloHistory.game_date.asc())
    )
    result = await db.execute(history_query)
    history = result.scalars().all()

    return EloHistoryResponse(
        team=TeamResponse.model_validate(team),
        history=[
            EloHistoryPoint(
                game_date=h.game_date.strftime("%Y-%m-%d"),
                elo_before=h.elo_before,
                elo_after=h.elo_after,
            )
            for h in history
        ],
    )
