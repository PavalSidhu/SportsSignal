from dataclasses import dataclass, field


@dataclass(frozen=True)
class SportConfig:
    name: str
    api_source: str  # "balldontlie", "nhl_api", "mlb_api", "espn"
    elo_k_base: float
    elo_home_advantage: float
    elo_season_regression: float  # Weight toward mean (0.75 = 75% old ELO + 25% mean)
    default_ppg: float
    period_type: str  # "quarter", "period", "inning", "half"
    num_periods: int
    # Maps win probability log-odds to expected point spread.
    # spread = spread_calibration * ln(p / (1-p))
    # Calibrated from historical average spreads per sport.
    spread_calibration: float = 10.0
    seasons: list[int] = field(default_factory=list)
    season_label_format: str = "single"  # "single" (2024) or "range" (2024-25)
    espn_groups: str | None = None  # ESPN API group filter (e.g. "50" for D1)


SPORT_CONFIGS: dict[str, SportConfig] = {
    "NBA": SportConfig(
        name="NBA",
        api_source="balldontlie",
        elo_k_base=20,
        elo_home_advantage=75,
        elo_season_regression=0.75,
        default_ppg=100.0,
        period_type="quarter",
        num_periods=4,
        spread_calibration=12.0,
        seasons=[2022, 2023, 2024, 2025],
        season_label_format="range",
    ),
    "NHL": SportConfig(
        name="NHL",
        api_source="nhl_api",
        elo_k_base=16,
        elo_home_advantage=30,
        elo_season_regression=0.75,
        default_ppg=3.0,
        period_type="period",
        num_periods=3,
        spread_calibration=2.5,
        seasons=[2022, 2023, 2024, 2025],
        season_label_format="range",
    ),
    "MLB": SportConfig(
        name="MLB",
        api_source="mlb_api",
        elo_k_base=10,
        elo_home_advantage=24,
        elo_season_regression=0.75,
        default_ppg=4.5,
        period_type="inning",
        num_periods=9,
        spread_calibration=5.0,
        seasons=[2022, 2023, 2024, 2025],
        season_label_format="single",
    ),
    "NCAAB": SportConfig(
        name="NCAAB",
        api_source="espn",
        elo_k_base=20,
        elo_home_advantage=125,
        elo_season_regression=0.75,
        default_ppg=70.0,
        period_type="half",
        num_periods=2,
        spread_calibration=10.0,
        seasons=[2022, 2023, 2024, 2025],
        season_label_format="range",
        espn_groups="50",
    ),
    "NFL": SportConfig(
        name="NFL",
        api_source="espn",
        elo_k_base=20,
        elo_home_advantage=48,
        elo_season_regression=0.75,
        default_ppg=22.0,
        period_type="quarter",
        num_periods=4,
        spread_calibration=10.0,
        seasons=[2022, 2023, 2024, 2025],
        season_label_format="single",
    ),
    "NCAAF": SportConfig(
        name="NCAAF",
        api_source="espn",
        elo_k_base=20,
        elo_home_advantage=75,
        elo_season_regression=0.75,
        default_ppg=28.0,
        period_type="quarter",
        num_periods=4,
        spread_calibration=10.0,
        seasons=[2022, 2023, 2024, 2025],
        season_label_format="single",
        espn_groups="80",
    ),
}


def get_sport_config(sport: str) -> SportConfig:
    """Get configuration for a sport. Raises KeyError if sport is not configured."""
    config = SPORT_CONFIGS.get(sport.upper())
    if config is None:
        raise KeyError(f"No configuration found for sport: {sport}")
    return config


def get_all_sports() -> list[str]:
    """Return list of all configured sport names."""
    return list(SPORT_CONFIGS.keys())
