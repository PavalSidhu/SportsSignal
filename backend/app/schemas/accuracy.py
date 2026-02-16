from pydantic import BaseModel


class AccuracyOverviewResponse(BaseModel):
    total_predictions: int
    correct_predictions: int
    accuracy_pct: float
    avg_score_error: float
    avg_spread_error: float
    games_predicted: int
    model_accuracy: float | None = None  # CV accuracy from training metrics


class AccuracyBySportItem(BaseModel):
    sport: str
    total: int
    correct: int
    accuracy_pct: float
    model_accuracy: float | None = None  # CV accuracy from training metrics


class AccuracyBySportResponse(BaseModel):
    by_sport: list[AccuracyBySportItem]


class AccuracyByTypeItem(BaseModel):
    prediction_type: str
    accuracy_pct: float
    avg_error: float


class AccuracyByTypeResponse(BaseModel):
    by_type: list[AccuracyByTypeItem]


class AccuracyTrendPoint(BaseModel):
    date: str
    accuracy_pct: float
    total: int


class AccuracyTrendResponse(BaseModel):
    trend: list[AccuracyTrendPoint]


class RecentPredictionResult(BaseModel):
    game_id: int
    game_date: str
    home_team: str
    away_team: str
    predicted_winner: str
    actual_winner: str
    was_correct: bool
    predicted_score: str
    actual_score: str
    score_error: float


class CalibrationBucket(BaseModel):
    bucket_label: str
    bucket_midpoint: float
    correct: int
    total: int
    accuracy_pct: float


class CalibrationSportData(BaseModel):
    sport: str
    overall_correct: int
    overall_total: int
    overall_accuracy_pct: float
    buckets: list[CalibrationBucket]


class CalibrationResponse(BaseModel):
    sports: list[CalibrationSportData]
