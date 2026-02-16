from pydantic import BaseModel, ConfigDict

from app.schemas.teams import TeamResponse


class GameTeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    abbreviation: str
    logo_url: str
    current_elo: float


class PredictionSummary(BaseModel):
    win_probability: float
    predicted_winner_id: int
    predicted_home_score: float
    predicted_away_score: float
    confidence: float


class GameListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    sport: str
    season: int
    game_date: str
    status: str
    is_postseason: bool
    home_team: GameTeamResponse
    away_team: GameTeamResponse
    home_score: int | None = None
    away_score: int | None = None
    prediction: PredictionSummary | None = None


class GameListResponse(BaseModel):
    games: list[GameListItem]
    total: int


class FactorResponse(BaseModel):
    factor: str
    impact: float
    direction: str
    detail: str


class QuarterPredictions(BaseModel):
    home: list[float]
    away: list[float]


class PredictionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    win_probability: float
    confidence: float
    predicted_winner_id: int
    predicted_home_score: float
    predicted_away_score: float
    predicted_spread: float
    predicted_total: float
    quarter_predictions: QuarterPredictions | None = None
    key_factors: list[FactorResponse] = []


class HeadToHeadGame(BaseModel):
    game_date: str
    home_team_abbreviation: str
    away_team_abbreviation: str
    home_score: int
    away_score: int
    winner_abbreviation: str


class TeamComparisonStat(BaseModel):
    stat_name: str
    home_value: float
    away_value: float


class GameDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    sport: str
    season: int
    game_date: str
    status: str
    is_postseason: bool
    home_team: TeamResponse
    away_team: TeamResponse
    home_score: int | None = None
    away_score: int | None = None
    home_period_scores: list[int] | None = None
    away_period_scores: list[int] | None = None
    predictions: list[PredictionDetailResponse] = []
    head_to_head: list[HeadToHeadGame] = []
    team_comparison: list[TeamComparisonStat] = []
