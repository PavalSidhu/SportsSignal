import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://statsapi.mlb.com/api/v1"


class MLBClient:
    """Async client for the MLB Stats API."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._request_interval = 1.0  # ~60 req/min

    async def _request(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await asyncio.sleep(self._request_interval)
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def get_teams(self) -> list[dict[str, Any]]:
        """Fetch all MLB teams."""
        data = await self._request(f"{BASE_URL}/teams", params={"sportId": 1})
        return data.get("teams", [])

    # Regular season + all playoff round types
    GAME_TYPES: list[str] = ["R", "F", "D", "L", "W"]

    async def get_games(self, season: int) -> list[dict[str, Any]]:
        """Fetch all regular-season and postseason games for a season with linescore data.

        Game types fetched:
          R = regular season
          F = wild card
          D = division series
          L = league championship series
          W = world series
        """
        all_games: list[dict[str, Any]] = []

        for game_type in self.GAME_TYPES:
            params = {
                "sportId": 1,
                "season": season,
                "gameType": game_type,
                "hydrate": "linescore",
            }
            data = await self._request(f"{BASE_URL}/schedule", params=params)

            count = 0
            for date_entry in data.get("dates", []):
                for game in date_entry.get("games", []):
                    game["season"] = season
                    game["gameType"] = game_type
                    # Extract inning scores from linescore
                    linescore = game.get("linescore", {})
                    innings = linescore.get("innings", [])
                    if innings:
                        game["home_period_scores"] = [
                            inning.get("home", {}).get("runs", 0) for inning in innings
                        ]
                        game["away_period_scores"] = [
                            inning.get("away", {}).get("runs", 0) for inning in innings
                        ]
                    all_games.append(game)
                    count += 1

            if count > 0:
                logger.info(
                    "Fetched %d MLB games (type=%s) for season %d",
                    count,
                    game_type,
                    season,
                )

        logger.info(
            "Fetched %d total MLB games for season %d", len(all_games), season
        )
        return all_games

    async def get_game_detail(self, game_id: int) -> dict[str, Any]:
        """Fetch linescore for a specific game."""
        data = await self._request(f"{BASE_URL}/game/{game_id}/linescore")
        return data

    async def get_boxscore(self, game_pk: int) -> dict[str, Any] | None:
        """Fetch boxscore data for a specific game.

        Returns a dict with 'home' and 'away' keys containing batting and
        pitching stats, or None if data is unavailable.
        """
        try:
            data = await self._request(f"{BASE_URL}/game/{game_pk}/boxscore")
        except Exception:
            logger.warning("Failed to fetch MLB boxscore for game %s", game_pk)
            return None

        teams_data = data.get("teams", {})

        def _extract_team(team_data: dict) -> dict[str, Any]:
            team_stats = team_data.get("teamStats", {})
            batting = team_stats.get("batting", {})
            pitching = team_stats.get("pitching", {})

            # Find probable/starting pitcher info
            pitchers = team_data.get("pitchers", [])
            players = team_data.get("players", {})
            pitcher_name = ""
            pitcher_era = 0.0
            pitcher_whip = 0.0
            pitcher_ip = 0.0
            pitcher_k = 0
            pitcher_bb = 0

            # Look for the starting pitcher (first pitcher listed)
            if pitchers:
                starter_id = f"ID{pitchers[0]}"
                starter_data = players.get(starter_id, {})
                person = starter_data.get("person", {})
                pitcher_name = person.get("fullName", "")
                starter_stats = starter_data.get("stats", {}).get("pitching", {})
                pitcher_era_str = starter_stats.get("era", "0.00")
                try:
                    pitcher_era = float(pitcher_era_str)
                except (ValueError, TypeError):
                    pitcher_era = 0.0
                pitcher_ip_str = starter_stats.get("inningsPitched", "0.0")
                try:
                    pitcher_ip = float(pitcher_ip_str)
                except (ValueError, TypeError):
                    pitcher_ip = 0.0
                pitcher_k = starter_stats.get("strikeOuts", 0)
                pitcher_bb = starter_stats.get("baseOnBalls", 0)
                # Compute starter WHIP from their game stats
                starter_hits = starter_stats.get("hits", 0)
                starter_walks = starter_stats.get("baseOnBalls", 0)
                if pitcher_ip > 0:
                    pitcher_whip = round((starter_hits + starter_walks) / pitcher_ip, 3)

            # Parse total team innings pitched
            team_ip_str = pitching.get("inningsPitched", "0.0") or "0.0"
            try:
                team_ip = float(team_ip_str)
            except (ValueError, TypeError):
                team_ip = 0.0

            return {
                "runs": batting.get("runs", 0),
                "hits": batting.get("hits", 0),
                "errors": team_stats.get("fielding", {}).get("errors", 0),
                "left_on_base": batting.get("leftOnBase", 0),
                "strikeouts": batting.get("strikeOuts", 0),
                "walks": batting.get("baseOnBalls", 0),
                "home_runs": batting.get("homeRuns", 0),
                "stolen_bases": batting.get("stolenBases", 0),
                "batting_avg": round(batting.get("hits", 0) / max(batting.get("atBats", 1), 1), 3),
                "at_bats": batting.get("atBats", 0),
                "total_bases": batting.get("totalBases", 0),
                "doubles": batting.get("doubles", 0),
                "triples": batting.get("triples", 0),
                "pitcher_name": pitcher_name,
                "pitcher_era": pitcher_era,
                "pitcher_whip": pitcher_whip,
                "pitcher_ip": pitcher_ip,
                "pitcher_k": pitcher_k,
                "pitcher_bb": pitcher_bb,
                "team_ip": team_ip,
                "earned_runs": pitching.get("earnedRuns", 0),
                "pitching_strikeouts": pitching.get("strikeOuts", 0),
                "pitching_walks": pitching.get("baseOnBalls", 0),
                "pitching_hits": pitching.get("hits", 0),
                "team_era": round(float(pitching.get("era", "0.00") or "0.00"), 2),
                "team_whip": round(
                    (pitching.get("baseOnBalls", 0) + pitching.get("hits", 0))
                    / max(team_ip, 0.1),
                    3,
                ),
            }

        home_data = teams_data.get("home", {})
        away_data = teams_data.get("away", {})

        return {
            "home": _extract_team(home_data),
            "away": _extract_team(away_data),
        }

    async def close(self) -> None:
        await self._client.aclose()
