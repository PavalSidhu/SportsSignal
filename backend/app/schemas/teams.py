from pydantic import BaseModel, ConfigDict


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    sport: str
    name: str
    abbreviation: str
    city: str
    conference: str
    division: str
    logo_url: str
    current_elo: float


class TeamDetailResponse(TeamResponse):
    wins: int = 0
    losses: int = 0
    win_pct: float = 0.0


class EloHistoryPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    game_date: str
    elo_before: float
    elo_after: float


class EloHistoryResponse(BaseModel):
    team: TeamResponse
    history: list[EloHistoryPoint]
