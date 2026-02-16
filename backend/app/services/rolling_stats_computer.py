"""Service to compute and store pre-computed rolling stats for teams.

Rolling stats are computed chronologically — for each game, the stats
represent the team's performance *before* that game.  This allows the
feature engineer to read rolling stats directly instead of querying
N games per prediction.
"""

import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Team, TeamEloHistory
from app.models.game_boxscore import GameBoxscore
from app.models.team_rolling_stats import TeamRollingStats

logger = logging.getLogger(__name__)

# EWMA decay factor for 10-game windows
EWMA_DECAY = 0.95


def _ewma(values: list[float], decay: float = EWMA_DECAY) -> float:
    """Compute exponentially weighted moving average."""
    if not values:
        return 0.0
    weight = 1.0
    total = 0.0
    weight_sum = 0.0
    for v in reversed(values):  # oldest first in reversed = newest first
        total += weight * v
        weight_sum += weight
        weight *= decay
    return total / weight_sum if weight_sum > 0 else 0.0


class RollingStatsComputer:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def compute_all(self, sport: str) -> int:
        """Recompute all rolling stats from scratch for a sport.

        Returns the number of rolling stat records created.
        """
        logger.info("Computing all rolling stats for %s", sport)

        # Clear existing rolling stats for this sport
        await self.db.execute(
            delete(TeamRollingStats).where(TeamRollingStats.sport == sport)
        )
        await self.db.flush()

        # Fetch all completed games in chronological order
        result = await self.db.execute(
            select(Game)
            .where(Game.sport == sport, Game.status == "Final")
            .order_by(Game.game_date.asc())
        )
        games = list(result.scalars().all())

        if not games:
            logger.info("No completed games for %s", sport)
            return 0

        # Pre-load all boxscores for this sport, keyed by (game_id, team_id)
        box_result = await self.db.execute(
            select(GameBoxscore).where(GameBoxscore.sport == sport)
        )
        boxscores: dict[tuple[int, int], dict] = {}
        for box in box_result.scalars().all():
            boxscores[(box.game_id, box.team_id)] = box.stats or {}

        # Pre-load ELO history keyed by (team_id, game_id)
        team_ids_result = await self.db.execute(
            select(Team.id).where(Team.sport == sport)
        )
        team_ids = [r[0] for r in team_ids_result.all()]

        elo_result = await self.db.execute(
            select(TeamEloHistory).where(TeamEloHistory.team_id.in_(team_ids))
        )
        elo_map: dict[tuple[int, int], float] = {}
        for eh in elo_result.scalars().all():
            # Store the ELO *before* the game
            elo_map[(eh.team_id, eh.game_id)] = eh.elo_before

        # Per-team game history (rolling windows)
        # Each entry: (game, is_home, score_for, score_against, boxscore_stats)
        team_history: dict[int, list[dict]] = defaultdict(list)
        records_created = 0

        for i, game in enumerate(games):
            if game.home_score is None or game.away_score is None:
                continue

            # Compute rolling stats for BOTH teams before this game
            for team_id, is_home in [
                (game.home_team_id, True),
                (game.away_team_id, False),
            ]:
                history = team_history[team_id]
                elo_before = elo_map.get((team_id, game.id), 1500.0)

                stats = self._compute_stats_from_history(
                    history, elo_before, sport, is_home
                )
                stats["elo"] = elo_before

                stmt = pg_insert(TeamRollingStats).values(
                    team_id=team_id,
                    game_id=game.id,
                    sport=sport,
                    as_of_date=game.game_date,
                    games_played=len(history),
                    stats=stats,
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_rolling_team_game",
                    set_={
                        "stats": stmt.excluded.stats,
                        "games_played": stmt.excluded.games_played,
                        "as_of_date": stmt.excluded.as_of_date,
                    },
                )
                await self.db.execute(stmt)
                records_created += 1

            # After computing stats, add this game to both teams' histories
            home_box = boxscores.get((game.id, game.home_team_id), {})
            away_box = boxscores.get((game.id, game.away_team_id), {})

            # Include opponent turnovers for true turnover margin (football)
            home_box_with_opp = dict(home_box)
            away_box_with_opp = dict(away_box)
            if sport in ("NFL", "NCAAF"):
                home_box_with_opp["opp_turnovers"] = away_box.get("turnovers", 0)
                away_box_with_opp["opp_turnovers"] = home_box.get("turnovers", 0)

            team_history[game.home_team_id].append({
                "game_id": game.id,
                "game_date": game.game_date,
                "is_home": True,
                "score_for": game.home_score,
                "score_against": game.away_score,
                "won": game.home_score > game.away_score,
                "boxscore": home_box_with_opp,
                "margin": game.home_score - game.away_score,
            })

            team_history[game.away_team_id].append({
                "game_id": game.id,
                "game_date": game.game_date,
                "is_home": False,
                "score_for": game.away_score,
                "score_against": game.home_score,
                "won": game.away_score > game.home_score,
                "boxscore": away_box_with_opp,
                "margin": game.away_score - game.home_score,
            })

            # Commit periodically
            if (i + 1) % 500 == 0:
                await self.db.commit()
                logger.info(
                    "Progress: %d/%d %s games processed (%d records)",
                    i + 1, len(games), sport, records_created,
                )

        await self.db.commit()
        logger.info(
            "Rolling stats complete for %s: %d records from %d games",
            sport, records_created, len(games),
        )
        return records_created

    def _compute_stats_from_history(
        self,
        history: list[dict],
        elo: float,
        sport: str,
        is_home: bool,
    ) -> dict:
        """Compute rolling stats from a team's game history."""
        if not history:
            return self._default_stats(sport)

        last_10 = history[-10:]
        last_20 = history[-20:]

        # Universal stats
        wins_10 = [1.0 if g["won"] else 0.0 for g in last_10]
        wins_20 = [1.0 if g["won"] else 0.0 for g in last_20]

        ppg_10 = [float(g["score_for"]) for g in last_10]
        ppg_20 = [float(g["score_for"]) for g in last_20]
        papg_10 = [float(g["score_against"]) for g in last_10]
        papg_20 = [float(g["score_against"]) for g in last_20]

        margin_10 = [float(g["margin"]) for g in last_10]

        home_games_10 = [g for g in last_10 if g["is_home"]]
        away_games_10 = [g for g in last_10 if not g["is_home"]]

        home_wins_10 = sum(1 for g in home_games_10 if g["won"])
        away_wins_10 = sum(1 for g in away_games_10 if g["won"])

        # Streak: count consecutive wins/losses from most recent
        streak = 0
        for g in reversed(history):
            if g["won"]:
                if streak >= 0:
                    streak += 1
                else:
                    break
            else:
                if streak <= 0:
                    streak -= 1
                else:
                    break

        stats = {
            "win_pct_10": _ewma(wins_10),
            "win_pct_20": _ewma(wins_20),
            "ppg_10": _ewma(ppg_10),
            "ppg_20": _ewma(ppg_20),
            "papg_10": _ewma(papg_10),
            "papg_20": _ewma(papg_20),
            "margin_avg_10": _ewma(margin_10),
            "home_win_pct_10": home_wins_10 / len(home_games_10) if home_games_10 else 0.5,
            "away_win_pct_10": away_wins_10 / len(away_games_10) if away_games_10 else 0.5,
            "streak": streak,
        }

        # Sport-specific stats from boxscores
        sport_stats = self._compute_sport_specific(last_10, sport)
        stats.update(sport_stats)

        # Round all float values
        for k, v in stats.items():
            if isinstance(v, float):
                stats[k] = round(v, 6)

        return stats

    def _compute_sport_specific(
        self, last_10: list[dict], sport: str
    ) -> dict:
        """Compute sport-specific rolling stats from boxscore data."""
        boxes = [g["boxscore"] for g in last_10 if g.get("boxscore")]

        if sport == "NBA":
            return self._compute_nba_stats(boxes, last_10)
        elif sport == "NHL":
            return self._compute_nhl_stats(boxes, last_10)
        elif sport == "MLB":
            return self._compute_mlb_stats(boxes, last_10)
        elif sport == "NCAAB":
            return self._compute_ncaab_stats(boxes, last_10)
        elif sport in ("NCAAF", "NFL"):
            return self._compute_football_stats(boxes, last_10)
        return {}

    def _compute_nba_stats(
        self, boxes: list[dict], last_10: list[dict]
    ) -> dict:
        """NBA Four Factors + advanced stats."""
        if not boxes:
            return {
                "efg_pct_10": 0.0, "tov_pct_10": 0.0, "ftr_10": 0.0,
                "oreb_pct_10": 0.0, "net_rating_10": 0.0,
                "ast_tov_ratio_10": 0.0, "pace_10": 0.0,
            }

        efg_vals = []
        tov_vals = []
        ftr_vals = []
        oreb_vals = []
        net_rating_vals = []

        for b in boxes:
            fgm = b.get("fgm", 0)
            fga = b.get("fga", 1) or 1
            fg3m = b.get("fg3m", 0) or b.get("3ptm", 0)
            ftm = b.get("ftm", 0)
            fta = b.get("fta", 0)
            oreb = b.get("oreb", 0)
            dreb = b.get("dreb", 0)
            tov = b.get("tov", 0)
            pts = b.get("pts", 0)
            ast = b.get("ast", 0)

            # eFG% = (FGM + 0.5 * 3PM) / FGA
            efg = (fgm + 0.5 * fg3m) / fga if fga > 0 else 0.0
            efg_vals.append(efg)

            # TOV% = TOV / (FGA + 0.44 * FTA + TOV)
            possessions_est = fga + 0.44 * fta + tov
            tov_pct = tov / possessions_est if possessions_est > 0 else 0.0
            tov_vals.append(tov_pct)

            # FTR = FTA / FGA
            ftr = fta / fga if fga > 0 else 0.0
            ftr_vals.append(ftr)

            # OREB% approximation
            total_reb = oreb + dreb
            oreb_pct = oreb / total_reb if total_reb > 0 else 0.0
            oreb_vals.append(oreb_pct)

        # Net rating from scoring (all games, not just those with boxscores)
        net_rating_vals = [float(g["score_for"] - g["score_against"]) for g in last_10]

        total_ast = sum(b.get("ast", 0) for b in boxes)
        total_tov = sum(b.get("tov", 0) for b in boxes)

        # Estimate pace from possessions: FGA + 0.44*FTA - OREB + TOV
        pace_vals = []
        for b in boxes:
            fga = b.get("fga", 0)
            fta = b.get("fta", 0)
            oreb = b.get("oreb", 0)
            tov = b.get("tov", 0)
            possessions = fga + 0.44 * fta - oreb + tov
            pace_vals.append(possessions)

        return {
            "efg_pct_10": _ewma(efg_vals),
            "tov_pct_10": _ewma(tov_vals),
            "ftr_10": _ewma(ftr_vals),
            "oreb_pct_10": _ewma(oreb_vals),
            "net_rating_10": _ewma(net_rating_vals) if net_rating_vals else 0.0,
            "ast_tov_ratio_10": total_ast / max(total_tov, 1),
            "pace_10": _ewma(pace_vals) if pace_vals else 0.0,
        }

    def _compute_nhl_stats(
        self, boxes: list[dict], last_10: list[dict]
    ) -> dict:
        """NHL goaltending + special teams stats."""
        if not boxes:
            return {
                "shots_per_game_10": 0.0, "save_pct_10": 0.0,
                "pp_pct_10": 0.0, "pk_pct_10": 0.0,
                "goals_per_game_10": 0.0, "goals_against_10": 0.0,
                "shot_diff_10": 0.0,
            }

        shots_vals = []
        save_pct_vals = []
        goals_vals = []
        total_pp_goals = 0
        total_pp_opp = 0
        total_pk_ga = 0
        total_pk_opp = 0
        shots_against_vals = []

        # Iterate last_10 to correctly pair boxscore data with game data
        for g in last_10:
            b = g.get("boxscore")
            if not b:
                continue
            shots_vals.append(float(b.get("shots", 0)))
            save_pct_vals.append(float(b.get("save_pct", 0)))
            goals_vals.append(float(b.get("goals", 0)))
            total_pp_goals += b.get("pp_goals", 0)
            total_pp_opp += b.get("pp_opportunities", 0)
            total_pk_ga += b.get("pk_goals_against", 0)
            total_pk_opp += b.get("pk_opportunities", 0)
            # Correctly paired: saves from boxscore + goals_against from same game
            saves = float(b.get("saves", 0))
            ga = float(g["score_against"])
            shots_against_vals.append(saves + ga)

        goals_against_vals = [float(g["score_against"]) for g in last_10]

        return {
            "shots_per_game_10": _ewma(shots_vals),
            "save_pct_10": _ewma(save_pct_vals),
            "pp_pct_10": total_pp_goals / max(total_pp_opp, 1),
            "pk_pct_10": 1.0 - (total_pk_ga / max(total_pk_opp, 1)),
            "goals_per_game_10": _ewma(goals_vals),
            "goals_against_10": _ewma(goals_against_vals),
            "shot_diff_10": _ewma(shots_vals) - _ewma(shots_against_vals) if shots_against_vals else 0.0,
        }

    def _compute_mlb_stats(
        self, boxes: list[dict], last_10: list[dict]
    ) -> dict:
        """MLB batting and pitching stats."""
        if not boxes:
            return {
                "ops_10": 0.0, "era_10": 0.0, "whip_10": 0.0,
                "k_bb_ratio_10": 0.0, "batting_avg_10": 0.0,
                "slug_pct_10": 0.0, "runs_per_game_10": 0.0,
            }

        total_hits = sum(b.get("hits", 0) for b in boxes)
        total_ab = sum(b.get("at_bats", 1) for b in boxes) or 1
        total_walks = sum(b.get("walks", 0) for b in boxes)
        total_k = sum(b.get("strikeouts", 0) for b in boxes)

        # Compute total_bases from component hits if not present in boxscore
        total_tb = 0
        for b in boxes:
            tb = b.get("total_bases", 0)
            if tb:
                total_tb += tb
            else:
                # Compute from components: singles + 2*doubles + 3*triples + 4*HR
                hits = b.get("hits", 0)
                doubles = b.get("doubles", 0)
                triples = b.get("triples", 0)
                hr = b.get("home_runs", 0)
                if "doubles" in b and "triples" in b:
                    singles = hits - doubles - triples - hr
                    total_tb += max(singles, 0) + 2 * doubles + 3 * triples + 4 * hr
                else:
                    # Fallback: rough approximation
                    total_tb += hits + 3 * hr

        batting_avg = total_hits / total_ab
        obp = (total_hits + total_walks) / (total_ab + total_walks) if (total_ab + total_walks) > 0 else 0.0
        slg = total_tb / total_ab

        # Use pitching K for K/BB ratio, prefer team-level pitching_strikeouts
        total_pitching_k = sum(
            b.get("pitching_strikeouts", 0) or b.get("pitcher_k", 0) for b in boxes
        )
        total_pitching_bb = sum(
            b.get("pitching_walks", 0) or b.get("pitcher_bb", 0) for b in boxes
        )

        # Per-game WHIP from boxscore (team_whip is computed per game now)
        whip_vals = [float(b.get("team_whip", 0)) for b in boxes if b.get("team_whip")]

        # Per-game ERA: iterate last_10 to correctly pair boxscore with game data
        era_vals = []
        for g in last_10:
            b = g.get("boxscore")
            if not b:
                continue
            team_ip = float(b.get("team_ip", 0))
            earned_runs = b.get("earned_runs", None)
            if team_ip > 0 and earned_runs is not None:
                game_era = (float(earned_runs) / team_ip) * 9.0
                era_vals.append(game_era)
            elif team_ip > 0:
                # Fallback: use total runs against / team IP
                runs_against = float(g["score_against"])
                game_era = (runs_against / team_ip) * 9.0
                era_vals.append(game_era)
            else:
                # Last resort: use pitcher_ip
                ip = float(b.get("pitcher_ip", 0))
                if ip > 0:
                    runs_against = float(g["score_against"])
                    game_era = (runs_against / ip) * 9.0
                    era_vals.append(game_era)

        runs_vals = [float(g["score_for"]) for g in last_10]

        return {
            "ops_10": obp + slg,
            "era_10": _ewma(era_vals) if era_vals else 0.0,
            "whip_10": _ewma(whip_vals) if whip_vals else 0.0,
            "k_bb_ratio_10": total_pitching_k / max(total_pitching_bb, 1),
            "batting_avg_10": batting_avg,
            "slug_pct_10": slg,
            "runs_per_game_10": _ewma(runs_vals),
        }

    def _compute_ncaab_stats(
        self, boxes: list[dict], last_10: list[dict]
    ) -> dict:
        """NCAAB Four Factors (same as NBA subset)."""
        if not boxes:
            return {
                "efg_pct_10": 0.0, "tov_pct_10": 0.0,
                "ftr_10": 0.0, "oreb_pct_10": 0.0,
            }

        efg_vals = []
        tov_vals = []
        ftr_vals = []
        oreb_vals = []

        for b in boxes:
            fgm = b.get("fgm", 0)
            fga = b.get("fga", 1) or 1
            fg3m = b.get("fg3m", 0) or b.get("3ptm", 0)
            ftm = b.get("ftm", 0)
            fta = b.get("fta", 0)
            oreb = b.get("oreb", 0)
            reb = b.get("reb", 0)
            tov = b.get("tov", 0)

            efg = (fgm + 0.5 * fg3m) / fga if fga > 0 else 0.0
            efg_vals.append(efg)

            possessions_est = fga + 0.44 * fta + tov
            tov_pct = tov / possessions_est if possessions_est > 0 else 0.0
            tov_vals.append(tov_pct)

            ftr = fta / fga if fga > 0 else 0.0
            ftr_vals.append(ftr)

            oreb_pct = oreb / reb if reb > 0 else 0.0
            oreb_vals.append(oreb_pct)

        return {
            "efg_pct_10": _ewma(efg_vals),
            "tov_pct_10": _ewma(tov_vals),
            "ftr_10": _ewma(ftr_vals),
            "oreb_pct_10": _ewma(oreb_vals),
        }

    def _compute_football_stats(
        self, boxes: list[dict], last_10: list[dict]
    ) -> dict:
        """NFL/NCAAF efficiency stats."""
        if not boxes:
            return {
                "yards_per_play_10": 0.0, "tov_margin_10": 0.0,
                "third_down_pct_10": 0.0,
            }

        ypp_vals = []
        tov_margin_vals = []
        third_down_vals = []

        for i, b in enumerate(boxes):
            total_yards = b.get("total_yards", 0)
            pass_att = b.get("pass_attempts", 0)
            rush_att = b.get("rushing_carries", 0)
            total_plays = pass_att + rush_att
            ypp = total_yards / total_plays if total_plays > 0 else 0.0
            ypp_vals.append(ypp)

            turnovers = b.get("turnovers", 0)
            # Use opponent turnovers from boxscore if available for true margin
            opp_turnovers = b.get("opp_turnovers", 0)
            if opp_turnovers > 0:
                tov_margin_vals.append(opp_turnovers - turnovers)
            else:
                # Fallback: negative own turnovers (approximation)
                tov_margin_vals.append(-turnovers)

            conv = b.get("third_down_conv", 0)
            att = b.get("third_down_att", 0)
            td_pct = conv / att if att > 0 else 0.0
            third_down_vals.append(td_pct)

        return {
            "yards_per_play_10": _ewma(ypp_vals),
            "tov_margin_10": _ewma(tov_margin_vals),
            "third_down_pct_10": _ewma(third_down_vals),
        }

    @staticmethod
    def _default_stats(sport: str) -> dict:
        """Return default (zero) stats when no history is available."""
        base = {
            "win_pct_10": 0.5, "win_pct_20": 0.5,
            "ppg_10": 0.0, "ppg_20": 0.0,
            "papg_10": 0.0, "papg_20": 0.0,
            "margin_avg_10": 0.0,
            "home_win_pct_10": 0.5, "away_win_pct_10": 0.5,
            "streak": 0, "elo": 1500.0,
        }

        sport_defaults = {
            "NBA": {"efg_pct_10": 0.0, "tov_pct_10": 0.0, "ftr_10": 0.0,
                     "oreb_pct_10": 0.0, "net_rating_10": 0.0,
                     "ast_tov_ratio_10": 0.0, "pace_10": 0.0},
            "NHL": {"shots_per_game_10": 0.0, "save_pct_10": 0.0,
                     "pp_pct_10": 0.0, "pk_pct_10": 0.0,
                     "goals_per_game_10": 0.0, "goals_against_10": 0.0,
                     "shot_diff_10": 0.0},
            "MLB": {"ops_10": 0.0, "era_10": 0.0, "whip_10": 0.0,
                     "k_bb_ratio_10": 0.0, "batting_avg_10": 0.0,
                     "slug_pct_10": 0.0, "runs_per_game_10": 0.0},
            "NCAAB": {"efg_pct_10": 0.0, "tov_pct_10": 0.0,
                       "ftr_10": 0.0, "oreb_pct_10": 0.0},
            "NCAAF": {"yards_per_play_10": 0.0, "tov_margin_10": 0.0,
                       "third_down_pct_10": 0.0},
            "NFL": {"yards_per_play_10": 0.0, "tov_margin_10": 0.0,
                     "third_down_pct_10": 0.0},
        }

        base.update(sport_defaults.get(sport, {}))
        return base
