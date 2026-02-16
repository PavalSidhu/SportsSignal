import logging
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Team
from app.models.team_rolling_stats import TeamRollingStats
from app.utils.sport_config import get_sport_config

logger = logging.getLogger(__name__)

# Sport-specific feature names (added on top of the base features)
SPORT_FEATURE_REGISTRY: dict[str, list[str]] = {
    "NBA": [
        "home_efg_pct_10", "away_efg_pct_10",
        "home_tov_pct_10", "away_tov_pct_10",
        "home_ftr_10", "away_ftr_10",
        "home_oreb_pct_10", "away_oreb_pct_10",
        "home_net_rating_10", "away_net_rating_10",
        "home_pace_10", "away_pace_10",
    ],
    "NHL": [
        "home_save_pct_10", "away_save_pct_10",
        "home_shot_diff_10", "away_shot_diff_10",
        "home_pp_pct_10", "away_pp_pct_10",
        "home_pk_pct_10", "away_pk_pct_10",
        "home_goals_per_game_10", "away_goals_per_game_10",
    ],
    "MLB": [
        "home_ops_10", "away_ops_10",
        "home_era_10", "away_era_10",
        "home_whip_10", "away_whip_10",
        "home_k_bb_ratio_10", "away_k_bb_ratio_10",
        "home_runs_per_game_10", "away_runs_per_game_10",
    ],
    "NCAAB": [
        "home_efg_pct_10", "away_efg_pct_10",
        "home_tov_pct_10", "away_tov_pct_10",
        "home_ftr_10", "away_ftr_10",
        "home_oreb_pct_10", "away_oreb_pct_10",
    ],
    "NCAAF": [
        "home_yards_per_play_10", "away_yards_per_play_10",
        "home_tov_margin_10", "away_tov_margin_10",
        "home_third_down_pct_10", "away_third_down_pct_10",
    ],
    "NFL": [
        "home_yards_per_play_10", "away_yards_per_play_10",
        "home_tov_margin_10", "away_tov_margin_10",
        "home_third_down_pct_10", "away_third_down_pct_10",
    ],
}

# Base feature names shared across all sports
# Removed: home_advantage (always 1.0, zero importance),
#          is_back_to_back_home/away (redundant with rest_days),
#          is_postseason (near-zero importance across all sports)
BASE_FEATURE_NAMES: list[str] = [
    "elo_diff",
    "home_win_pct_10",
    "away_win_pct_10",
    "home_ppg_20",
    "away_ppg_20",
    "home_papg_20",
    "away_papg_20",
    "rest_days_home",
    "rest_days_away",
    "h2h_home_wins_last5",
    "home_streak",
    "away_streak",
    "home_margin_avg_10",
    "away_margin_avg_10",
]


class FeatureEngineer:
    """Compute features for prediction models.

    When rolling stats are available (from the team_rolling_stats table),
    uses them directly — eliminating N+1 game queries.  Falls back to
    the legacy per-game query path when rolling stats are not found.
    """

    # Dynamic per-sport feature names
    FEATURE_NAMES: list[str]

    def __init__(self, db: AsyncSession, sport: str | None = None) -> None:
        self.db = db
        self.sport = sport
        if sport:
            sport_features = SPORT_FEATURE_REGISTRY.get(sport, [])
            self.FEATURE_NAMES = BASE_FEATURE_NAMES + sport_features
        else:
            # Legacy mode: original features for backward compatibility
            self.FEATURE_NAMES = [
                "elo_diff",
                "home_win_pct_last10",
                "away_win_pct_last10",
                "home_ppg",
                "away_ppg",
                "home_papg",
                "away_papg",
                "rest_days_home",
                "rest_days_away",
                "h2h_home_wins_last5",
            ]

    async def compute_features(self, game: Game) -> dict | None:
        """Compute feature dict for a game. Returns None if insufficient data.

        Tries rolling stats first; falls back to legacy queries.
        """
        if self.sport:
            result = await self._compute_features_from_rolling_stats(game)
            if result is not None:
                return result
            logger.debug(
                "Rolling stats not found for game %d, falling back to legacy",
                game.id,
            )

        return await self._compute_features_legacy(game)

    async def _compute_features_from_rolling_stats(self, game: Game) -> dict | None:
        """Compute features from pre-computed rolling stats."""
        home_stats = await self._get_rolling_stats(game.home_team_id, game.game_date, game.id)
        away_stats = await self._get_rolling_stats(game.away_team_id, game.game_date, game.id)

        if home_stats is None or away_stats is None:
            return None

        # Need enough games played for meaningful stats
        if home_stats.games_played < 3 or away_stats.games_played < 3:
            return None

        hs = home_stats.stats
        as_ = away_stats.stats

        # Rest days: compute from rolling stats as_of_date
        rest_days_home = self._calc_rest_days_from_dates(game.game_date, home_stats.as_of_date)
        rest_days_away = self._calc_rest_days_from_dates(game.game_date, away_stats.as_of_date)

        # H2H record — still need a query for this
        h2h_games = await self._get_h2h_games(
            game.home_team_id, game.away_team_id, 5, game.game_date
        )
        h2h_home_wins = 0
        for h2h in h2h_games:
            if h2h.home_team_id == game.home_team_id and (h2h.home_score or 0) > (h2h.away_score or 0):
                h2h_home_wins += 1
            elif h2h.away_team_id == game.home_team_id and (h2h.away_score or 0) > (h2h.home_score or 0):
                h2h_home_wins += 1
        h2h_home_wins_last5 = h2h_home_wins / max(len(h2h_games), 1) if h2h_games else 0.5

        features = {
            "elo_diff": hs.get("elo", 1500) - as_.get("elo", 1500),
            "home_win_pct_10": hs.get("win_pct_10", 0.5),
            "away_win_pct_10": as_.get("win_pct_10", 0.5),
            "home_ppg_20": hs.get("ppg_20", 0.0),
            "away_ppg_20": as_.get("ppg_20", 0.0),
            "home_papg_20": hs.get("papg_20", 0.0),
            "away_papg_20": as_.get("papg_20", 0.0),
            "rest_days_home": rest_days_home,
            "rest_days_away": rest_days_away,
            "h2h_home_wins_last5": h2h_home_wins_last5,
            "home_streak": float(hs.get("streak", 0)),
            "away_streak": float(as_.get("streak", 0)),
            "home_margin_avg_10": hs.get("margin_avg_10", 0.0),
            "away_margin_avg_10": as_.get("margin_avg_10", 0.0),
        }

        # Add sport-specific features from rolling stats
        sport = self.sport or game.sport
        for feat in SPORT_FEATURE_REGISTRY.get(sport, []):
            if feat.startswith("home_"):
                stat_key = feat[5:]  # remove "home_"
                features[feat] = float(hs.get(stat_key, 0.0))
            elif feat.startswith("away_"):
                stat_key = feat[5:]  # remove "away_"
                features[feat] = float(as_.get(stat_key, 0.0))

        return features

    async def _get_rolling_stats(
        self, team_id: int, before_date, game_id: int | None = None
    ) -> TeamRollingStats | None:
        """Get the most recent rolling stats for a team before a given date.

        If game_id is provided, first try a direct lookup (the row stored for
        that game contains stats computed *before* the game was played).
        Falls back to the most recent row before ``before_date`` for upcoming
        games that don't have a rolling stats row yet.
        """
        if game_id is not None:
            result = await self.db.execute(
                select(TeamRollingStats)
                .where(
                    TeamRollingStats.team_id == team_id,
                    TeamRollingStats.game_id == game_id,
                )
                .limit(1)
            )
            row = result.scalars().first()
            if row is not None:
                return row

        # Fallback: most recent stats before game date (for upcoming games)
        result = await self.db.execute(
            select(TeamRollingStats)
            .where(
                TeamRollingStats.team_id == team_id,
                TeamRollingStats.as_of_date < before_date,
            )
            .order_by(TeamRollingStats.as_of_date.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    def _calc_rest_days_from_dates(game_date, last_game_date) -> float:
        """Calculate rest days between two dates. Capped at 7."""
        if last_game_date is None:
            return 3.0
        delta = game_date - last_game_date
        rest = delta.days if isinstance(delta, timedelta) else delta.total_seconds() / 86400
        return min(rest, 7.0)

    # --- Legacy feature computation (fallback) ---

    async def _compute_features_legacy(self, game: Game) -> dict | None:
        """Original 14-feature computation via per-game queries."""
        home_team = await self.db.get(Team, game.home_team_id)
        away_team = await self.db.get(Team, game.away_team_id)

        if home_team is None or away_team is None:
            logger.warning("Could not find teams for game %d", game.id)
            return None

        home_last_10 = await self._get_team_last_n_games(
            game.home_team_id, 10, game.game_date
        )
        away_last_10 = await self._get_team_last_n_games(
            game.away_team_id, 10, game.game_date
        )

        if len(home_last_10) < 3 or len(away_last_10) < 3:
            return None

        home_last_20 = await self._get_team_last_n_games(
            game.home_team_id, 20, game.game_date
        )
        away_last_20 = await self._get_team_last_n_games(
            game.away_team_id, 20, game.game_date
        )

        config = get_sport_config(game.sport)
        default_ppg = config.default_ppg

        elo_diff = home_team.current_elo - away_team.current_elo
        home_win_pct_last10 = self._calc_win_pct(game.home_team_id, home_last_10)
        away_win_pct_last10 = self._calc_win_pct(game.away_team_id, away_last_10)
        home_ppg = self._calc_ppg(game.home_team_id, home_last_20, default_ppg)
        away_ppg = self._calc_ppg(game.away_team_id, away_last_20, default_ppg)
        home_papg = self._calc_papg(game.home_team_id, home_last_20, default_ppg)
        away_papg = self._calc_papg(game.away_team_id, away_last_20, default_ppg)
        rest_days_home = self._calc_rest_days(game.game_date, home_last_10)
        rest_days_away = self._calc_rest_days(game.game_date, away_last_10)

        h2h_games = await self._get_h2h_games(
            game.home_team_id, game.away_team_id, 5, game.game_date
        )
        h2h_home_wins = 0
        for h2h in h2h_games:
            if h2h.home_team_id == game.home_team_id and (h2h.home_score or 0) > (h2h.away_score or 0):
                h2h_home_wins += 1
            elif h2h.away_team_id == game.home_team_id and (h2h.away_score or 0) > (h2h.home_score or 0):
                h2h_home_wins += 1
        h2h_home_wins_last5 = h2h_home_wins / max(len(h2h_games), 1) if h2h_games else 0.5

        # When sport is set, use the new feature names
        if self.sport:
            return {
                "elo_diff": elo_diff,
                "home_win_pct_10": home_win_pct_last10,
                "away_win_pct_10": away_win_pct_last10,
                "home_ppg_20": home_ppg,
                "away_ppg_20": away_ppg,
                "home_papg_20": home_papg,
                "away_papg_20": away_papg,
                "rest_days_home": rest_days_home,
                "rest_days_away": rest_days_away,
                "h2h_home_wins_last5": h2h_home_wins_last5,
                "home_streak": 0.0,
                "away_streak": 0.0,
                "home_margin_avg_10": 0.0,
                "away_margin_avg_10": 0.0,
                # Zero out sport-specific features in legacy mode
                **{feat: 0.0 for feat in SPORT_FEATURE_REGISTRY.get(self.sport, [])},
            }

        # Legacy feature dict (no sport set)
        return {
            "elo_diff": elo_diff,
            "home_win_pct_last10": home_win_pct_last10,
            "away_win_pct_last10": away_win_pct_last10,
            "home_ppg": home_ppg,
            "away_ppg": away_ppg,
            "home_papg": home_papg,
            "away_papg": away_papg,
            "rest_days_home": rest_days_home,
            "rest_days_away": rest_days_away,
            "h2h_home_wins_last5": h2h_home_wins_last5,
        }

    def to_array(self, features: dict) -> list[float]:
        """Convert a features dict to a list in consistent order matching FEATURE_NAMES."""
        return [float(features[name]) for name in self.FEATURE_NAMES]

    async def _get_team_last_n_games(
        self, team_id: int, n: int, before_date
    ) -> list[Game]:
        """Query last N completed games for a team before the given date."""
        result = await self.db.execute(
            select(Game)
            .where(
                or_(
                    Game.home_team_id == team_id,
                    Game.away_team_id == team_id,
                ),
                Game.status == "Final",
                Game.game_date < before_date,
            )
            .order_by(Game.game_date.desc())
            .limit(n)
        )
        return list(result.scalars().all())

    async def _get_h2h_games(
        self, team_a_id: int, team_b_id: int, n: int, before_date
    ) -> list[Game]:
        """Query last N head-to-head games between two teams."""
        result = await self.db.execute(
            select(Game)
            .where(
                or_(
                    (Game.home_team_id == team_a_id) & (Game.away_team_id == team_b_id),
                    (Game.home_team_id == team_b_id) & (Game.away_team_id == team_a_id),
                ),
                Game.status == "Final",
                Game.game_date < before_date,
            )
            .order_by(Game.game_date.desc())
            .limit(n)
        )
        return list(result.scalars().all())

    @staticmethod
    def _calc_win_pct(team_id: int, games: list[Game]) -> float:
        if not games:
            return 0.5
        wins = 0
        for g in games:
            if g.home_team_id == team_id and (g.home_score or 0) > (g.away_score or 0):
                wins += 1
            elif g.away_team_id == team_id and (g.away_score or 0) > (g.home_score or 0):
                wins += 1
        return wins / len(games)

    @staticmethod
    def _calc_ppg(team_id: int, games: list[Game], default_ppg: float = 100.0) -> float:
        if not games:
            return default_ppg
        total = 0.0
        for g in games:
            if g.home_team_id == team_id:
                total += g.home_score or 0
            else:
                total += g.away_score or 0
        return total / len(games)

    @staticmethod
    def _calc_papg(team_id: int, games: list[Game], default_ppg: float = 100.0) -> float:
        if not games:
            return default_ppg
        total = 0.0
        for g in games:
            if g.home_team_id == team_id:
                total += g.away_score or 0
            else:
                total += g.home_score or 0
        return total / len(games)

    @staticmethod
    def _calc_rest_days(game_date, games: list[Game]) -> float:
        if not games:
            return 3.0
        most_recent = games[0]
        delta = game_date - most_recent.game_date
        rest = delta.days if isinstance(delta, timedelta) else delta.total_seconds() / 86400
        return min(rest, 7.0)
