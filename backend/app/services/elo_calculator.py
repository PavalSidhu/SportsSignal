import logging
from collections import defaultdict

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Team, TeamEloHistory
from app.utils.sport_config import get_sport_config

logger = logging.getLogger(__name__)


class EloCalculator:
    INITIAL_ELO = 1500

    def __init__(self, db: AsyncSession, sport: str = "NBA") -> None:
        self.db = db
        config = get_sport_config(sport)
        self.K_BASE = config.elo_k_base
        self.HOME_ADVANTAGE = config.elo_home_advantage
        self._season_regression = config.elo_season_regression

    def k_factor(self, mov: int, elo_diff: float) -> float:
        """Compute the adjusted K-factor based on margin of victory and ELO difference."""
        return self.K_BASE * ((abs(mov) + 3) ** 0.8) / (7.5 + 0.006 * abs(elo_diff))

    def calculate_expected(self, elo_a: float, elo_b: float) -> float:
        """Calculate the expected score for team A against team B."""
        return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))

    def update_elo(
        self,
        home_elo: float,
        away_elo: float,
        home_score: int,
        away_score: int,
    ) -> tuple[float, float]:
        """Update ELO ratings after a game. Returns (new_home_elo, new_away_elo)."""
        expected_home = self.calculate_expected(
            home_elo + self.HOME_ADVANTAGE, away_elo
        )
        expected_away = self.calculate_expected(
            away_elo, home_elo + self.HOME_ADVANTAGE
        )

        home_won = 1.0 if home_score > away_score else 0.0
        mov = home_score - away_score
        elo_diff = home_elo - away_elo

        k = self.k_factor(mov, elo_diff)

        new_home = home_elo + k * (home_won - expected_home)
        new_away = away_elo + k * ((1.0 - home_won) - expected_away)

        return new_home, new_away

    def season_reset(self, elo: float) -> float:
        """Regress ELO toward the mean between seasons."""
        return self._season_regression * elo + (1 - self._season_regression) * self.INITIAL_ELO

    async def calculate_all_elos(self, sport: str | None = None) -> None:
        """Recalculate all ELO ratings from scratch for a given sport.

        If sport is provided, it overrides the sport set at construction time
        by re-loading the config.
        """
        if sport is not None:
            config = get_sport_config(sport)
            self.K_BASE = config.elo_k_base
            self.HOME_ADVANTAGE = config.elo_home_advantage
            self._season_regression = config.elo_season_regression
        else:
            sport = "NBA"  # fallback for backward compatibility

        logger.info("Calculating all ELO ratings for sport=%s", sport)

        # Reset all teams to initial ELO
        await self.db.execute(
            update(Team)
            .where(Team.sport == sport)
            .values(current_elo=self.INITIAL_ELO)
        )

        # Clear existing ELO history for this sport's teams
        team_ids_result = await self.db.execute(
            select(Team.id).where(Team.sport == sport)
        )
        team_ids = [row[0] for row in team_ids_result.all()]

        if team_ids:
            await self.db.execute(
                delete(TeamEloHistory).where(TeamEloHistory.team_id.in_(team_ids))
            )

        # Query all completed games ordered by date
        result = await self.db.execute(
            select(Game)
            .where(Game.sport == sport, Game.status == "Final")
            .order_by(Game.game_date.asc())
        )
        games = result.scalars().all()

        if not games:
            logger.info("No completed games found for sport=%s", sport)
            return

        # Track current ELOs in memory
        elos: dict[int, float] = defaultdict(lambda: self.INITIAL_ELO)

        # Track current season to detect boundaries
        current_season: int | None = None
        history_records: list[TeamEloHistory] = []

        for game in games:
            # Detect season boundary and apply reset
            if current_season is not None and game.season != current_season:
                logger.info(
                    "Season change detected: %d -> %d, applying ELO reset",
                    current_season,
                    game.season,
                )
                for tid in list(elos.keys()):
                    elos[tid] = self.season_reset(elos[tid])

            current_season = game.season

            home_elo_before = elos[game.home_team_id]
            away_elo_before = elos[game.away_team_id]

            if game.home_score is None or game.away_score is None:
                continue

            new_home_elo, new_away_elo = self.update_elo(
                home_elo_before,
                away_elo_before,
                game.home_score,
                game.away_score,
            )

            elos[game.home_team_id] = new_home_elo
            elos[game.away_team_id] = new_away_elo

            # Create history records
            history_records.append(
                TeamEloHistory(
                    team_id=game.home_team_id,
                    game_id=game.id,
                    game_date=game.game_date,
                    elo_before=home_elo_before,
                    elo_after=new_home_elo,
                )
            )
            history_records.append(
                TeamEloHistory(
                    team_id=game.away_team_id,
                    game_id=game.id,
                    game_date=game.game_date,
                    elo_before=away_elo_before,
                    elo_after=new_away_elo,
                )
            )

        # Bulk insert history records
        if history_records:
            self.db.add_all(history_records)

        # Update current ELO for each team
        for team_id, elo in elos.items():
            await self.db.execute(
                update(Team).where(Team.id == team_id).values(current_elo=elo)
            )

        await self.db.flush()
        await self.db.commit()
        logger.info(
            "ELO calculation complete for sport=%s: processed %d games, updated %d teams",
            sport,
            len(games),
            len(elos),
        )
