import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api-web.nhle.com/v1"


class NHLClient:
    """Async client for the NHL Official API."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=10.0, read=15.0, pool=10.0),
            follow_redirects=True,
        )
        self._request_interval = 2.0  # ~30 req/min

    async def _request(self, url: str, timeout: float = 15.0) -> dict[str, Any]:
        await asyncio.sleep(self._request_interval)
        response = await asyncio.wait_for(
            self._client.get(url),
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    async def get_teams(self) -> list[dict[str, Any]]:
        """Fetch all NHL teams from the standings endpoint."""
        data = await self._request(f"{BASE_URL}/standings/now")
        return data.get("standings", [])

    async def get_games(self, season: int) -> list[dict[str, Any]]:
        """Fetch all regular-season games for a season by paginating week-by-week.

        The NHL schedule endpoint returns one week per request and provides
        nextStartDate/previousStartDate for pagination.
        Season param is the start year (e.g. 2024 for the 2024-25 season).
        """
        # Start from the regular season start — use October 1 of the season year
        current_date = f"{season}-10-01"
        all_games: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        season_id = int(f"{season}{season + 1}")

        while current_date:
            data = await self._request(f"{BASE_URL}/schedule/{current_date}")

            for week in data.get("gameWeek", []):
                week_date = week.get("date", "")
                for game in week.get("games", []):
                    game_id = game.get("id")
                    game_season = game.get("season", 0)

                    # Only include games from the target season
                    if game_season != season_id:
                        continue
                    # Skip preseason (gameType 1) and all-star (4)
                    if game.get("gameType") not in (2, 3):
                        continue
                    if game_id in seen_ids:
                        continue

                    seen_ids.add(game_id)
                    # Attach the date from the week entry since games don't have gameDate
                    game["gameDate"] = week_date
                    all_games.append(game)

            next_date = data.get("nextStartDate")
            if not next_date or next_date <= current_date:
                break
            # Stop if we've gone past the season (July of next year)
            if next_date > f"{season + 1}-07-01":
                break
            current_date = next_date

        logger.info("Fetched %d NHL games for season %d-%d", len(all_games), season, season + 1)
        return all_games

    async def get_boxscore(self, game_id: int) -> dict[str, Any] | None:
        """Fetch boxscore data for a specific game.

        Returns a dict with 'home' and 'away' keys containing team stats,
        or None if data is unavailable.
        """
        try:
            data = await self._request(f"{BASE_URL}/gamecenter/{game_id}/boxscore")
        except Exception:
            logger.warning("Failed to fetch NHL boxscore for game %s", game_id)
            return None

        player_stats = data.get("playerByGameStats", {})
        home_players = player_stats.get("homeTeam", {})
        away_players = player_stats.get("awayTeam", {})

        def _aggregate_team(team_data: dict) -> dict[str, Any]:
            goalies = team_data.get("goalies", [])
            forwards = team_data.get("forwards", [])
            defense = team_data.get("defense", [])
            skaters = forwards + defense

            total_shots = sum(p.get("sog", 0) for p in skaters)
            total_hits = sum(p.get("hits", 0) for p in skaters)
            total_blocked = sum(p.get("blockedShots", 0) for p in skaters)
            total_giveaways = sum(p.get("giveaways", 0) for p in skaters)
            total_takeaways = sum(p.get("takeaways", 0) for p in skaters)
            total_faceoff_wins = sum(
                round(p.get("faceoffWinningPctg", 0) * p.get("faceoffs", 0))
                for p in skaters if p.get("faceoffs", 0) > 0
            )
            total_faceoffs = sum(p.get("faceoffs", 0) for p in skaters)

            total_saves = 0
            total_sa = 0
            for g in goalies:
                sa = g.get("shotsAgainst", 0)
                sv = g.get("saves", 0)
                total_saves += sv
                total_sa += sa

            save_pct = total_saves / total_sa if total_sa > 0 else 0.0

            return {
                "shots": total_shots,
                "saves": total_saves,
                "save_pct": round(save_pct, 4),
                "hits": total_hits,
                "blocked_shots": total_blocked,
                "giveaways": total_giveaways,
                "takeaways": total_takeaways,
                "faceoff_wins": round(total_faceoff_wins),
                "faceoff_total": total_faceoffs,
            }

        home_team_data = data.get("homeTeam", {})
        away_team_data = data.get("awayTeam", {})

        home_stats = _aggregate_team(home_players)
        away_stats = _aggregate_team(away_players)

        home_stats["goals"] = home_team_data.get("score", 0)
        away_stats["goals"] = away_team_data.get("score", 0)

        # Fetch PP/PK data from the right-rail endpoint (not in boxscore)
        try:
            rr_data = await self._request(f"{BASE_URL}/gamecenter/{game_id}/right-rail")
            team_game_stats = rr_data.get("teamGameStats", [])
            for stat in team_game_stats:
                category = stat.get("category", "")
                if category == "powerPlay":
                    home_pp = stat.get("homeValue", "0/0")
                    away_pp = stat.get("awayValue", "0/0")
                    if "/" in str(home_pp):
                        parts = str(home_pp).split("/")
                        home_stats["pp_goals"] = int(parts[0])
                        home_stats["pp_opportunities"] = int(parts[1])
                    if "/" in str(away_pp):
                        parts = str(away_pp).split("/")
                        away_stats["pp_goals"] = int(parts[0])
                        away_stats["pp_opportunities"] = int(parts[1])
                elif category == "faceoffWinningPctg":
                    # Also grab faceoff data from right-rail as a more reliable source
                    pass
        except Exception:
            logger.warning("Failed to fetch right-rail data for game %s", game_id)

        # Compute PK from opponent's PP
        home_stats.setdefault("pp_goals", 0)
        home_stats.setdefault("pp_opportunities", 0)
        away_stats.setdefault("pp_goals", 0)
        away_stats.setdefault("pp_opportunities", 0)
        home_stats["pk_goals_against"] = away_stats["pp_goals"]
        home_stats["pk_opportunities"] = away_stats["pp_opportunities"]
        away_stats["pk_goals_against"] = home_stats["pp_goals"]
        away_stats["pk_opportunities"] = home_stats["pp_opportunities"]

        return {"home": home_stats, "away": away_stats}

    async def close(self) -> None:
        await self._client.aclose()
