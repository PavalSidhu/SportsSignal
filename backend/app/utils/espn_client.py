import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
SUMMARY_BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"

SPORT_PATHS = {
    "NFL": "football/nfl",
    "NBA": "basketball/nba",
    "NCAAB": "basketball/mens-college-basketball",
    "NCAAF": "football/college-football",
}

# Season date ranges (approximate)
SEASON_DATE_RANGES = {
    "NFL": {"start_month": 9, "start_day": 1, "end_month": 2, "end_day": 15},
    "NCAAB": {"start_month": 11, "start_day": 1, "end_month": 4, "end_day": 15},
    "NCAAF": {"start_month": 8, "start_day": 15, "end_month": 1, "end_day": 31},
}


class ESPNClient:
    """Async client for the ESPN Hidden API (NFL/NCAAB/NCAAF)."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        self._request_interval = 0.5  # ~120 req/min (ESPN is generous)

    async def _request(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await asyncio.sleep(self._request_interval)
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _sport_path(self, sport: str) -> str:
        path = SPORT_PATHS.get(sport.upper())
        if not path:
            raise ValueError(f"Unsupported ESPN sport: {sport}")
        return path

    async def get_teams(self, sport: str) -> list[dict[str, Any]]:
        """Fetch all teams for a sport from ESPN."""
        sport_path = self._sport_path(sport)
        url = f"{BASE_URL}/{sport_path}/teams"
        data = await self._request(url, params={"limit": 500})

        teams = []
        for group in data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
            teams.append(group)
        return teams

    async def get_games(self, sport: str, season: int, groups: str | None = None) -> list[dict[str, Any]]:
        """Fetch games for a season by iterating day-by-day through the season.

        ESPN scoreboard requires date-by-date queries.
        Use groups="50" for NCAAB (D1) or groups="80" for NCAAF (FBS) to
        get all games instead of just featured ones.
        """
        sport_path = self._sport_path(sport)
        ranges = SEASON_DATE_RANGES.get(sport.upper())
        if not ranges:
            return []

        # Build date range for the season
        # All ESPN sports span two calendar years
        start = datetime(season, ranges["start_month"], ranges["start_day"])
        end_year = season + 1 if ranges["end_month"] <= ranges["start_month"] else season
        end = datetime(end_year, ranges["end_month"], ranges["end_day"])

        all_games: list[dict[str, Any]] = []
        seen_ids: set[str | None] = set()
        current = start

        # Iterate day-by-day through the season date range
        while current <= end:
            date_str = current.strftime("%Y%m%d")
            url = f"{BASE_URL}/{sport_path}/scoreboard"
            try:
                params: dict[str, Any] = {"dates": date_str, "limit": 200}
                if groups:
                    params["groups"] = groups
                data = await self._request(url, params=params)
                events = data.get("events", [])
                for event in events:
                    # Skip duplicates: the same game can appear on adjacent
                    # days (e.g. a late-night game spanning midnight).
                    event_id = event.get("id")
                    if event_id in seen_ids:
                        continue
                    seen_ids.add(event_id)

                    # Preserve the API's season data (especially "type" for
                    # postseason detection). Only inject "year" as a fallback
                    # if the API didn't return it.
                    api_season = event.get("season") or {}
                    if isinstance(api_season, dict):
                        api_season.setdefault("year", season)
                    else:
                        api_season = {"year": season}
                    event["season"] = api_season

                    all_games.append(event)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    pass  # No games on this date
                else:
                    logger.warning("ESPN API error for %s on %s: %s", sport, date_str, e)
            except httpx.HTTPError as e:
                logger.warning("ESPN request failed for %s on %s: %s", sport, date_str, e)

            current += timedelta(days=1)  # Day-by-day for complete coverage

        logger.info("Fetched %d ESPN %s games for season %d", len(all_games), sport, season)
        return all_games

    async def get_game_summary(self, sport: str, event_id: str) -> dict[str, Any] | None:
        """Fetch game summary with boxscore stats from ESPN.

        Returns a dict with 'home' and 'away' keys containing team stats,
        or None if data is unavailable. Works for NBA, NCAAB, NCAAF, and NFL.
        """
        sport_path = SPORT_PATHS.get(sport.upper())
        if not sport_path:
            return None

        url = f"{SUMMARY_BASE_URL}/{sport_path}/summary"
        try:
            data = await self._request(url, params={"event": event_id})
        except Exception:
            logger.warning("Failed to fetch ESPN summary for %s event %s", sport, event_id)
            return None

        boxscore = data.get("boxscore", {})
        teams_data = boxscore.get("teams", [])
        if len(teams_data) < 2:
            return None

        # ESPN boxscore teams[0] is away, teams[1] is home (typically)
        # but we identify by homeAway field from the main event data
        players_data = boxscore.get("players", [])

        def _extract_basketball_stats(stat_entries: list) -> dict[str, Any]:
            """Extract basketball box score stats (NBA/NCAAB).

            Each entry in stat_entries has top-level 'labels' and 'totals' keys.
            """
            stats: dict[str, Any] = {}
            for stat_entry in stat_entries:
                labels = stat_entry.get("labels", [])
                totals = stat_entry.get("totals", [])
                if not labels or not totals:
                    continue
                stat_map = dict(zip(labels, totals))

                # Parse FG, 3PT, FT from "made-attempted" format
                for field, keys in [
                    ("fg", ("FG", "FGM-A")),
                    ("3pt", ("3PT", "3FG", "3FGM-A")),
                    ("ft", ("FT", "FTM-A")),
                ]:
                    for key in keys:
                        val = stat_map.get(key, "")
                        if "-" in str(val):
                            parts = str(val).split("-")
                            try:
                                stats[f"{field}m"] = int(parts[0])
                                stats[f"{field}a"] = int(parts[1])
                            except (ValueError, IndexError):
                                pass
                            break

                # Rename 3pt -> fg3 for consistency with the plan
                if "3ptm" in stats:
                    stats["fg3m"] = stats.pop("3ptm")
                    stats["fg3a"] = stats.pop("3pta", 0)

                # Integer stats
                for label, stat_key in [
                    ("REB", "reb"), ("OREB", "oreb"), ("DREB", "dreb"),
                    ("AST", "ast"), ("STL", "stl"), ("BLK", "blk"),
                    ("TO", "tov"), ("PF", "pf"), ("PTS", "pts"),
                ]:
                    if label in stat_map:
                        try:
                            stats[stat_key] = int(stat_map[label])
                        except (ValueError, TypeError):
                            pass

            return stats

        def _extract_football_stats(stat_entries: list) -> dict[str, Any]:
            """Extract football box score stats (NFL/NCAAF).

            Each entry in stat_entries has 'type', 'labels', and 'totals'.
            ESPN sometimes returns type=null, so we also detect by labels.
            """
            stats: dict[str, Any] = {}
            for stat_entry in stat_entries:
                stat_type = stat_entry.get("type") or ""
                labels = stat_entry.get("labels", [])
                totals = stat_entry.get("totals", [])
                if not labels or not totals:
                    continue
                stat_map = dict(zip(labels, totals))

                # Detect type from labels when ESPN returns null type
                if not stat_type:
                    if "C/ATT" in labels:
                        stat_type = "passing"
                    elif "CAR" in labels:
                        stat_type = "rushing"
                    elif "LOST" in labels and "FUM" in labels:
                        stat_type = "fumbles"

                if stat_type == "passing":
                    ca = stat_map.get("C/ATT", "0/0")
                    if "/" in str(ca):
                        parts = str(ca).split("/")
                        try:
                            stats["pass_completions"] = int(parts[0])
                            stats["pass_attempts"] = int(parts[1])
                        except (ValueError, IndexError):
                            pass
                    try:
                        stats["passing_yards"] = int(stat_map.get("YDS", 0))
                    except (ValueError, TypeError):
                        pass
                    try:
                        stats["passing_td"] = int(stat_map.get("TD", 0))
                    except (ValueError, TypeError):
                        pass
                    try:
                        stats["interceptions"] = int(stat_map.get("INT", 0))
                    except (ValueError, TypeError):
                        pass

                elif stat_type == "rushing":
                    try:
                        stats["rushing_yards"] = int(stat_map.get("YDS", 0))
                    except (ValueError, TypeError):
                        pass
                    try:
                        stats["rushing_carries"] = int(stat_map.get("CAR", 0))
                    except (ValueError, TypeError):
                        pass
                    try:
                        stats["rushing_td"] = int(stat_map.get("TD", 0))
                    except (ValueError, TypeError):
                        pass

                elif stat_type == "fumbles":
                    try:
                        stats["fumbles_lost"] = int(stat_map.get("LOST", 0))
                    except (ValueError, TypeError):
                        pass

            stats["total_yards"] = stats.get("passing_yards", 0) + stats.get("rushing_yards", 0)
            stats["turnovers"] = stats.get("interceptions", 0) + stats.get("fumbles_lost", 0)
            return stats

        # Determine home/away team IDs from the event header
        header = data.get("header", {})
        competitions = header.get("competitions", [{}])
        competitors = competitions[0].get("competitors", []) if competitions else []

        home_team_id = None
        away_team_id = None
        for comp in competitors:
            tid = comp.get("team", {}).get("id") or comp.get("id")
            if comp.get("homeAway") == "home":
                home_team_id = str(tid)
            elif comp.get("homeAway") == "away":
                away_team_id = str(tid)

        # Match players_data entries to home/away by team ID
        # (players array order doesn't necessarily match header order)
        home_player_stats = {}
        away_player_stats = {}
        for pd in players_data:
            pd_team_id = str(pd.get("team", {}).get("id", ""))
            if pd_team_id == home_team_id:
                home_player_stats = pd
            elif pd_team_id == away_team_id:
                away_player_stats = pd

        sport_upper = sport.upper()
        if sport_upper in ("NBA", "NCAAB"):
            home_stats = _extract_basketball_stats(
                home_player_stats.get("statistics", [])
            )
            away_stats = _extract_basketball_stats(
                away_player_stats.get("statistics", [])
            )
        elif sport_upper in ("NFL", "NCAAF"):
            home_stats = _extract_football_stats(
                home_player_stats.get("statistics", [])
            )
            away_stats = _extract_football_stats(
                away_player_stats.get("statistics", [])
            )

            # Also extract team-level stats from the teams section
            # Match teams_data to home/away by team ID
            for team_entry in teams_data:
                te_team_id = str(team_entry.get("team", {}).get("id", ""))
                target = home_stats if te_team_id == home_team_id else away_stats
                team_stats_list = team_entry.get("statistics", [])
                for ts in team_stats_list:
                    label = (ts.get("label") or "").lower()
                    display = ts.get("displayValue", "0")
                    try:
                        if label == "1st downs":
                            target["first_downs"] = int(display)
                        elif label == "3rd down efficiency":
                            if "-" in display:
                                parts = display.split("-")
                                target["third_down_conv"] = int(parts[0])
                                target["third_down_att"] = int(parts[1])
                        elif label == "penalties":
                            if "-" in display:
                                parts = display.split("-")
                                target["penalties"] = int(parts[0])
                                target["penalty_yards"] = int(parts[1])
                        elif label == "total yards":
                            target["total_yards"] = int(display)
                        elif label == "total plays":
                            target["total_plays"] = int(display)
                        elif label == "rushing attempts":
                            target.setdefault("rushing_carries", int(display))
                        elif label == "comp/att":
                            if "/" in display:
                                parts = display.split("/")
                                target.setdefault("pass_completions", int(parts[0]))
                                target.setdefault("pass_attempts", int(parts[1]))
                        elif label == "turnovers":
                            target["turnovers"] = int(display)
                        elif label == "possession":
                            target["time_of_possession"] = display
                    except (ValueError, TypeError):
                        pass
        else:
            return None

        return {"home": home_stats, "away": away_stats}

    async def close(self) -> None:
        await self._client.aclose()
