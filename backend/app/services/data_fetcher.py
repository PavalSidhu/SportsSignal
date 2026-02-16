import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, Player, Team
from app.models.game_boxscore import GameBoxscore
from app.services.cache_manager import (
    GAMES_TTL,
    PLAYERS_TTL,
    TEAMS_TTL,
    get_cache_manager,
)
from app.utils.api_client import get_api_client
from app.utils.sport_config import get_sport_config

logger = logging.getLogger(__name__)

# BallDontLie -> ESPN abbreviation mapping for NBA teams that differ
_BDL_TO_ESPN_ABBREV: dict[str, str] = {
    "GSW": "GS",
    "NYK": "NY",
    "NOP": "NO",
    "SAS": "SA",
    "UTA": "UTAH",
    "WAS": "WSH",
}

# Approximate US Eastern offset for UTC -> local date conversion.
# Most North American sports operate on US time; this ensures games
# appear on the correct calendar date in the UI.
_US_EASTERN_OFFSET = timedelta(hours=-5)


def _parse_utc_to_eastern(date_str: str | None) -> datetime:
    """Parse an ISO date/datetime string and convert UTC to approx US Eastern.

    BallDontLie, NHL, MLB, and ESPN APIs all return times in UTC.
    A game at 7pm ET on Jan 5 is "2026-01-06T00:00:00Z" in UTC.
    Without conversion the UI would show it on Jan 6 — one day late.
    """
    if not date_str or not isinstance(date_str, str):
        return datetime.utcnow()
    try:
        game_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if game_date.tzinfo is not None:
            # Convert UTC to approximate US Eastern, then strip tzinfo
            game_date = (game_date + _US_EASTERN_OFFSET).replace(tzinfo=None)
        else:
            # Already naive (date-only string like "2026-01-05") — keep as-is
            pass
    except ValueError:
        try:
            game_date = datetime.fromisoformat(date_str[:10])
        except ValueError:
            game_date = datetime.utcnow()
    return game_date


# ---------------------------------------------------------------------------
# NBA transforms (BallDontLie API)
# ---------------------------------------------------------------------------

def _transform_nba_team(raw: dict[str, Any], sport: str = "NBA") -> dict[str, Any]:
    """Map BallDontLie team response fields to our Team model columns."""
    return {
        "external_id": str(raw["id"]),
        "sport": sport,
        "name": raw["full_name"],
        "abbreviation": raw["abbreviation"],
        "city": raw.get("city", ""),
        "conference": raw.get("conference", ""),
        "division": raw.get("division", ""),
    }


def _transform_nba_player(
    raw: dict[str, Any], team_lookup: dict[str, int], sport: str = "NBA"
) -> dict[str, Any]:
    """Map BallDontLie player response fields to our Player model columns."""
    team_data = raw.get("team", {})
    team_external_id = str(team_data.get("id")) if team_data and team_data.get("id") else None
    return {
        "external_id": str(raw["id"]),
        "sport": sport,
        "first_name": raw.get("first_name", ""),
        "last_name": raw.get("last_name", ""),
        "position": raw.get("position", ""),
        "jersey_number": raw.get("jersey_number", ""),
        "team_id": team_lookup.get(team_external_id) if team_external_id else None,
    }


def _transform_nba_game(
    raw: dict[str, Any], team_lookup: dict[str, int], sport: str = "NBA"
) -> dict[str, Any] | None:
    """Map BallDontLie game response fields to our Game model columns."""
    home_team = raw.get("home_team", {})
    visitor_team = raw.get("visitor_team", {})

    home_ext_id = str(home_team.get("id")) if isinstance(home_team, dict) else str(home_team)
    away_ext_id = str(visitor_team.get("id")) if isinstance(visitor_team, dict) else str(visitor_team)

    home_id = team_lookup.get(home_ext_id)
    away_id = team_lookup.get(away_ext_id)

    if home_id is None or away_id is None:
        logger.warning(
            "Skipping game %s: could not resolve team IDs (home=%s, away=%s)",
            raw.get("id"),
            home_ext_id,
            away_ext_id,
        )
        return None

    # Parse game date – prefer "datetime" (full ISO with time) over "date"
    # (date-only). BallDontLie returns both; "datetime" has actual tip-off time.
    # Convert UTC to US Eastern so games appear on the correct calendar date.
    date_str = raw.get("datetime") or raw.get("date", "")
    game_date = _parse_utc_to_eastern(date_str)

    # Determine status – only mark "Final" when the API explicitly says so.
    # BallDontLie returns "Final" for finished games and other strings
    # (e.g. a tip-off time like "7:30 PM ET") for scheduled/future games.
    # Previously this also checked `home_team_score` which incorrectly
    # marked any game with score data as Final (e.g. projected scores for
    # future games or in-progress games).
    status_raw = raw.get("status", "")
    status = "Final" if status_raw == "Final" else "scheduled"

    # Period scores from BallDontLie period data
    home_scores = raw.get("home_team_score_by_period", [])
    away_scores = raw.get("visitor_team_score_by_period", [])
    home_period_scores = home_scores if home_scores else []
    away_period_scores = away_scores if away_scores else []

    return {
        "external_id": str(raw["id"]),
        "sport": sport,
        "season": raw.get("season", 0),
        "game_date": game_date,
        "status": status,
        "is_postseason": bool(raw.get("postseason", False)),
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": raw.get("home_team_score"),
        "away_score": raw.get("visitor_team_score"),
        "home_period_scores": home_period_scores,
        "away_period_scores": away_period_scores,
    }


# ---------------------------------------------------------------------------
# NHL transforms (NHL Official API)
# ---------------------------------------------------------------------------

def _transform_nhl_team(raw: dict[str, Any]) -> dict[str, Any]:
    """Map NHL API standings entry to Team model columns."""
    return {
        "external_id": str(raw.get("teamAbbrev", {}).get("default", "")),
        "sport": "NHL",
        "name": raw.get("teamName", {}).get("default", ""),
        "abbreviation": raw.get("teamAbbrev", {}).get("default", ""),
        "city": raw.get("placeName", {}).get("default", ""),
        "conference": raw.get("conferenceName", ""),
        "division": raw.get("divisionName", ""),
        "logo_url": raw.get("teamLogo", ""),
    }


def _transform_nhl_game(
    raw: dict[str, Any], team_lookup: dict[str, int]
) -> dict[str, Any] | None:
    """Map NHL API schedule game to Game model columns."""
    home_abbr = raw.get("homeTeam", {}).get("abbrev", "")
    away_abbr = raw.get("awayTeam", {}).get("abbrev", "")

    home_id = team_lookup.get(home_abbr)
    away_id = team_lookup.get(away_abbr)

    if home_id is None or away_id is None:
        return None

    # Prefer startTimeUTC for precise time, fallback to gameDate (date only)
    game_date_str = raw.get("startTimeUTC", raw.get("gameDate", ""))
    game_date = _parse_utc_to_eastern(game_date_str)

    state = raw.get("gameState", "")
    if state in ("OFF", "FINAL"):
        status = "Final"
    elif state in ("LIVE", "CRIT"):
        status = "in_progress"
    else:
        status = "scheduled"

    home_score = raw.get("homeTeam", {}).get("score")
    away_score = raw.get("awayTeam", {}).get("score")

    # Period scores from game detail (populated separately if available)
    home_period_scores = raw.get("home_period_scores") or []
    away_period_scores = raw.get("away_period_scores") or []

    season_str = str(raw.get("season", ""))
    season = int(season_str[:4]) if len(season_str) >= 4 else 0

    game_type = raw.get("gameType", 2)
    is_postseason = game_type == 3

    return {
        "external_id": str(raw.get("id", "")),
        "sport": "NHL",
        "season": season,
        "game_date": game_date,
        "status": status,
        "is_postseason": is_postseason,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": home_score,
        "away_score": away_score,
        "home_period_scores": home_period_scores,
        "away_period_scores": away_period_scores,
    }


# ---------------------------------------------------------------------------
# MLB transforms (MLB Stats API)
# ---------------------------------------------------------------------------

def _transform_mlb_team(raw: dict[str, Any]) -> dict[str, Any]:
    """Map MLB API team to Team model columns."""
    return {
        "external_id": str(raw.get("id", "")),
        "sport": "MLB",
        "name": raw.get("name", ""),
        "abbreviation": raw.get("abbreviation", ""),
        "city": raw.get("locationName", ""),
        "conference": raw.get("league", {}).get("name", ""),
        "division": raw.get("division", {}).get("name", ""),
    }


def _transform_mlb_game(
    raw: dict[str, Any], team_lookup: dict[str, int]
) -> dict[str, Any] | None:
    """Map MLB API schedule game to Game model columns."""
    teams_data = raw.get("teams", {})
    home_data = teams_data.get("home", {})
    away_data = teams_data.get("away", {})

    home_ext_id = str(home_data.get("team", {}).get("id", ""))
    away_ext_id = str(away_data.get("team", {}).get("id", ""))

    home_id = team_lookup.get(home_ext_id)
    away_id = team_lookup.get(away_ext_id)

    if home_id is None or away_id is None:
        return None

    game_date_str = raw.get("gameDate", raw.get("officialDate", ""))
    game_date = _parse_utc_to_eastern(game_date_str)

    status_code = raw.get("status", {}).get("statusCode", "")
    if status_code == "F":
        status = "Final"
    elif status_code in ("I", "IR"):
        status = "in_progress"
    else:
        status = "scheduled"

    home_score = home_data.get("score")
    away_score = away_data.get("score")

    # Inning scores from linescore if available
    home_period_scores = raw.get("home_period_scores") or []
    away_period_scores = raw.get("away_period_scores") or []

    season = int(raw.get("season", game_date.year))
    game_type = raw.get("gameType", "R")
    is_postseason = game_type in ("F", "D", "L", "W", "P")

    return {
        "external_id": str(raw.get("gamePk", "")),
        "sport": "MLB",
        "season": season,
        "game_date": game_date,
        "status": status,
        "is_postseason": is_postseason,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": home_score,
        "away_score": away_score,
        "home_period_scores": home_period_scores,
        "away_period_scores": away_period_scores,
    }


# ---------------------------------------------------------------------------
# ESPN transforms (NCAAB / NCAAF)
# ---------------------------------------------------------------------------

def _transform_espn_team(raw: dict[str, Any], sport: str) -> dict[str, Any]:
    """Map ESPN API team to Team model columns."""
    team = raw.get("team", raw)
    return {
        "external_id": str(team.get("id", "")),
        "sport": sport,
        "name": team.get("displayName", team.get("name", "")),
        "abbreviation": team.get("abbreviation", ""),
        "city": team.get("location", ""),
        "conference": team.get("groups", {}).get("name", "") if isinstance(team.get("groups"), dict) else "",
        "division": "",
        "logo_url": team.get("logos", [{}])[0].get("href", "") if team.get("logos") else "",
    }


def _transform_espn_game(
    raw: dict[str, Any], team_lookup: dict[str, int], sport: str
) -> dict[str, Any] | None:
    """Map ESPN API scoreboard event to Game model columns."""
    competitors = raw.get("competitions", [{}])[0].get("competitors", [])
    if len(competitors) < 2:
        return None

    # ESPN lists home/away via homeAway field
    home_data = None
    away_data = None
    for c in competitors:
        if c.get("homeAway") == "home":
            home_data = c
        else:
            away_data = c

    if not home_data or not away_data:
        return None

    home_ext_id = str(home_data.get("team", {}).get("id", ""))
    away_ext_id = str(away_data.get("team", {}).get("id", ""))

    home_id = team_lookup.get(home_ext_id)
    away_id = team_lookup.get(away_ext_id)

    if home_id is None or away_id is None:
        return None

    game_date_str = raw.get("date", "")
    game_date = _parse_utc_to_eastern(game_date_str)

    status_type = raw.get("status", {}).get("type", {}).get("name", "")
    if status_type == "STATUS_FINAL":
        status = "Final"
    elif status_type == "STATUS_IN_PROGRESS":
        status = "in_progress"
    else:
        status = "scheduled"

    home_score_str = home_data.get("score")
    away_score_str = away_data.get("score")
    home_score = int(home_score_str) if home_score_str and home_score_str.isdigit() else None
    away_score = int(away_score_str) if away_score_str and away_score_str.isdigit() else None

    # Extract period/half scores from linescores.
    # ESPN returns linescores as [{value: int}, ...].  Guard against None
    # values by falling back to 0.
    home_linescores = home_data.get("linescores", [])
    away_linescores = away_data.get("linescores", [])
    home_period_scores = [int(ls.get("value") or 0) for ls in home_linescores] if home_linescores else []
    away_period_scores = [int(ls.get("value") or 0) for ls in away_linescores] if away_linescores else []

    season_data = raw.get("season", {})
    season = int(season_data.get("year", game_date.year)) if isinstance(season_data, dict) else game_date.year

    # Determine postseason from season type
    season_type = season_data.get("type", 2) if isinstance(season_data, dict) else 2
    is_postseason = season_type == 3

    return {
        "external_id": str(raw.get("id", "")),
        "sport": sport,
        "season": season,
        "game_date": game_date,
        "status": status,
        "is_postseason": is_postseason,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_score": home_score,
        "away_score": away_score,
        "home_period_scores": home_period_scores,
        "away_period_scores": away_period_scores,
    }


# ---------------------------------------------------------------------------
# DataFetcher service
# ---------------------------------------------------------------------------

class DataFetcher:
    """High-level service that fetches, transforms, and upserts sports data."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cache = get_cache_manager()

    async def _get_team_lookup(self, sport: str) -> dict[str, int]:
        """Build a mapping of external_id -> internal id for teams."""
        result = await self.session.execute(
            select(Team.id, Team.external_id).where(Team.sport == sport)
        )
        return {row.external_id: row.id for row in result.all()}

    async def fetch_and_store_teams(self, sport: str) -> None:
        """Fetch all teams from the API and upsert into the database."""
        cache_key = f"teams_{sport}"
        if self.cache.is_fresh(cache_key, TEAMS_TTL):
            logger.info("Teams cache for %s is fresh, skipping fetch", sport)
            return

        config = get_sport_config(sport)
        logger.info("Fetching teams for %s via %s", sport, config.api_source)

        if config.api_source == "balldontlie":
            client = get_api_client()
            response = await client.get_teams(sport=sport)
            raw_teams = response.get("data", [])
            teams = [_transform_nba_team(t, sport) for t in raw_teams]
        elif config.api_source == "nhl_api":
            from app.utils.nhl_client import NHLClient
            client = NHLClient()
            raw_teams = await client.get_teams()
            teams = [_transform_nhl_team(t) for t in raw_teams]
            await client.close()
        elif config.api_source == "mlb_api":
            from app.utils.mlb_client import MLBClient
            client = MLBClient()
            raw_teams = await client.get_teams()
            teams = [_transform_mlb_team(t) for t in raw_teams]
            await client.close()
        elif config.api_source == "espn":
            from app.utils.espn_client import ESPNClient
            client = ESPNClient()
            raw_teams = await client.get_teams(sport)
            teams = [_transform_espn_team(t, sport) for t in raw_teams]
            await client.close()
        else:
            logger.error("Unknown api_source: %s", config.api_source)
            return

        if not teams:
            logger.warning("No teams returned from API for %s", sport)
            return

        logger.info("Upserting %d teams for %s", len(teams), sport)

        stmt = pg_insert(Team).values(teams)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_teams_sport_external_id",
            set_={
                "name": stmt.excluded.name,
                "abbreviation": stmt.excluded.abbreviation,
                "city": stmt.excluded.city,
                "conference": stmt.excluded.conference,
                "division": stmt.excluded.division,
                "logo_url": stmt.excluded.logo_url,
            },
        )
        await self.session.execute(stmt)
        await self.session.commit()

        self.cache.mark_fetched(cache_key)
        logger.info("Teams for %s upserted successfully", sport)

    async def fetch_and_store_players(self, sport: str) -> None:
        """Fetch all player pages from the API and upsert into the database."""
        config = get_sport_config(sport)
        if config.api_source != "balldontlie":
            logger.info("Player fetching not supported for %s, skipping", sport)
            return

        cache_key = f"players_{sport}"
        if self.cache.is_fresh(cache_key, PLAYERS_TTL):
            logger.info("Players cache for %s is fresh, skipping fetch", sport)
            return

        logger.info("Fetching players for %s", sport)
        client = get_api_client()
        team_lookup = await self._get_team_lookup(sport)

        players: list[dict[str, Any]] = []
        async for raw_player in client.paginate(
            client.get_players, sport=sport
        ):
            transformed = _transform_nba_player(raw_player, team_lookup, sport)
            players.append(transformed)

        if not players:
            logger.warning("No players returned from API for %s", sport)
            return

        logger.info("Upserting %d players for %s", len(players), sport)

        chunk_size = 500
        for i in range(0, len(players), chunk_size):
            chunk = players[i : i + chunk_size]
            stmt = pg_insert(Player).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_players_sport_external_id",
                set_={
                    "first_name": stmt.excluded.first_name,
                    "last_name": stmt.excluded.last_name,
                    "position": stmt.excluded.position,
                    "jersey_number": stmt.excluded.jersey_number,
                    "team_id": stmt.excluded.team_id,
                },
            )
            await self.session.execute(stmt)

        await self.session.commit()
        self.cache.mark_fetched(cache_key)
        logger.info("Players for %s upserted successfully", sport)

    async def fetch_and_store_games(
        self, sport: str, seasons: list[int]
    ) -> None:
        """Fetch game data for the given seasons and upsert into the database."""
        cache_key = f"games_{sport}_{'_'.join(str(s) for s in seasons)}"
        if self.cache.is_fresh(cache_key, GAMES_TTL):
            logger.info("Games cache for %s seasons %s is fresh, skipping", sport, seasons)
            return

        config = get_sport_config(sport)
        logger.info("Fetching games for %s, seasons=%s via %s", sport, seasons, config.api_source)
        team_lookup = await self._get_team_lookup(sport)

        games: list[dict[str, Any]] = []

        if config.api_source == "balldontlie":
            client = get_api_client()
            async for raw_game in client.paginate(
                client.get_games, sport=sport, seasons=seasons
            ):
                transformed = _transform_nba_game(raw_game, team_lookup, sport)
                if transformed is not None:
                    games.append(transformed)

        elif config.api_source == "nhl_api":
            from app.utils.nhl_client import NHLClient
            client = NHLClient()
            for season in seasons:
                raw_games = await client.get_games(season)
                for raw_game in raw_games:
                    transformed = _transform_nhl_game(raw_game, team_lookup)
                    if transformed is not None:
                        games.append(transformed)
            await client.close()

        elif config.api_source == "mlb_api":
            from app.utils.mlb_client import MLBClient
            client = MLBClient()
            for season in seasons:
                raw_games = await client.get_games(season)
                for raw_game in raw_games:
                    transformed = _transform_mlb_game(raw_game, team_lookup)
                    if transformed is not None:
                        games.append(transformed)
            await client.close()

        elif config.api_source == "espn":
            from app.utils.espn_client import ESPNClient
            client = ESPNClient()
            for season in seasons:
                raw_games = await client.get_games(sport, season, groups=config.espn_groups)
                for raw_game in raw_games:
                    transformed = _transform_espn_game(raw_game, team_lookup, sport)
                    if transformed is not None:
                        games.append(transformed)
            await client.close()

        if not games:
            logger.warning("No games returned from API for %s seasons %s", sport, seasons)
            return

        # Deduplicate by external_id (keep last occurrence)
        seen: dict[str, int] = {}
        for i, g in enumerate(games):
            seen[g["external_id"]] = i
        games = [games[i] for i in sorted(seen.values())]

        logger.info("Upserting %d games for %s", len(games), sport)

        chunk_size = 500
        for i in range(0, len(games), chunk_size):
            chunk = games[i : i + chunk_size]
            stmt = pg_insert(Game).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_games_sport_external_id",
                set_={
                    "season": stmt.excluded.season,
                    "game_date": stmt.excluded.game_date,
                    "status": stmt.excluded.status,
                    "is_postseason": stmt.excluded.is_postseason,
                    "home_team_id": stmt.excluded.home_team_id,
                    "away_team_id": stmt.excluded.away_team_id,
                    "home_score": stmt.excluded.home_score,
                    "away_score": stmt.excluded.away_score,
                    "home_period_scores": stmt.excluded.home_period_scores,
                    "away_period_scores": stmt.excluded.away_period_scores,
                },
            )
            await self.session.execute(stmt)

        await self.session.commit()
        self.cache.mark_fetched(cache_key)
        logger.info("Games for %s seasons %s upserted successfully", sport, seasons)

    async def fetch_and_store_boxscores(
        self, sport: str, season: int | None = None, batch_size: int = 50
    ) -> int:
        """Fetch and store boxscore data for completed games missing boxscore records.

        Returns the number of boxscores stored.
        """
        config = get_sport_config(sport)

        # Find completed games that lack boxscore records
        from sqlalchemy import and_, not_, exists

        subq = (
            select(GameBoxscore.game_id)
            .where(GameBoxscore.game_id == Game.id)
            .correlate(Game)
            .exists()
        )

        query = (
            select(Game)
            .where(
                Game.sport == sport,
                Game.status == "Final",
                ~subq,
            )
            .order_by(Game.game_date.asc())
        )
        if season is not None:
            query = query.where(Game.season == season)

        result = await self.session.execute(query)
        games = list(result.scalars().all())

        if not games:
            logger.info("No games missing boxscores for %s", sport)
            return 0

        logger.info(
            "Found %d %s games missing boxscores, fetching...", len(games), sport
        )

        # Build abbreviation lookup for team matching (internal_id -> abbreviation)
        abbrev_result = await self.session.execute(
            select(Team.id, Team.abbreviation).where(Team.sport == sport)
        )
        id_to_abbrev = {row.id: row.abbreviation for row in abbrev_result.all()}

        stored = 0
        client = None

        try:
            if config.api_source == "nhl_api":
                from app.utils.nhl_client import NHLClient
                client = NHLClient()

                for i, game in enumerate(games):
                    boxscore_data = await client.get_boxscore(int(game.external_id))
                    if boxscore_data is None:
                        continue

                    for side, team_id in [
                        ("home", game.home_team_id),
                        ("away", game.away_team_id),
                    ]:
                        stats = boxscore_data.get(side, {})
                        if stats:
                            stmt = pg_insert(GameBoxscore).values(
                                game_id=game.id,
                                team_id=team_id,
                                sport=sport,
                                stats=stats,
                            )
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_boxscore_game_team",
                                set_={"stats": stmt.excluded.stats},
                            )
                            await self.session.execute(stmt)
                            stored += 1

                    if (i + 1) % batch_size == 0:
                        await self.session.commit()
                        logger.info(
                            "Progress: %d/%d %s games processed (%d boxscores stored)",
                            i + 1, len(games), sport, stored,
                        )

            elif config.api_source == "mlb_api":
                from app.utils.mlb_client import MLBClient
                client = MLBClient()

                for i, game in enumerate(games):
                    boxscore_data = await client.get_boxscore(int(game.external_id))
                    if boxscore_data is None:
                        continue

                    for side, team_id in [
                        ("home", game.home_team_id),
                        ("away", game.away_team_id),
                    ]:
                        stats = boxscore_data.get(side, {})
                        if stats:
                            stmt = pg_insert(GameBoxscore).values(
                                game_id=game.id,
                                team_id=team_id,
                                sport=sport,
                                stats=stats,
                            )
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_boxscore_game_team",
                                set_={"stats": stmt.excluded.stats},
                            )
                            await self.session.execute(stmt)
                            stored += 1

                    if (i + 1) % batch_size == 0:
                        await self.session.commit()
                        logger.info(
                            "Progress: %d/%d %s games processed (%d boxscores stored)",
                            i + 1, len(games), sport, stored,
                        )

            elif config.api_source == "balldontlie":
                # NBA: external_ids are BallDontLie IDs, not ESPN event IDs.
                # We look up ESPN event IDs by querying the scoreboard per date
                # and matching games by team abbreviation.
                stored = await self._fetch_boxscores_via_espn_scoreboard(
                    games, sport, id_to_abbrev, batch_size,
                )

            elif config.api_source == "espn":
                # NCAAB, NCAAF, NFL: external_ids are ESPN event IDs, use directly
                from app.utils.espn_client import ESPNClient
                client = ESPNClient()

                for i, game in enumerate(games):
                    boxscore_data = await client.get_game_summary(
                        sport, game.external_id
                    )
                    if boxscore_data is None:
                        continue

                    for side, team_id in [
                        ("home", game.home_team_id),
                        ("away", game.away_team_id),
                    ]:
                        stats = boxscore_data.get(side, {})
                        if stats:
                            stmt = pg_insert(GameBoxscore).values(
                                game_id=game.id,
                                team_id=team_id,
                                sport=sport,
                                stats=stats,
                            )
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_boxscore_game_team",
                                set_={"stats": stmt.excluded.stats},
                            )
                            await self.session.execute(stmt)
                            stored += 1

                    if (i + 1) % batch_size == 0:
                        await self.session.commit()
                        logger.info(
                            "Progress: %d/%d %s games processed (%d boxscores stored)",
                            i + 1, len(games), sport, stored,
                        )

        finally:
            if client and hasattr(client, "close"):
                await client.close()

        await self.session.commit()
        logger.info(
            "Boxscore fetching complete for %s: stored %d boxscores from %d games",
            sport, stored, len(games),
        )
        return stored

    async def _fetch_boxscores_via_espn_scoreboard(
        self,
        games: list,
        sport: str,
        id_to_abbrev: dict[int, str],
        batch_size: int,
    ) -> int:
        """Fetch boxscores for games whose external_ids are NOT ESPN event IDs.

        Groups games by date, queries the ESPN scoreboard for each date,
        matches games by team abbreviation, then fetches summaries using
        the discovered ESPN event ID.
        """
        from collections import defaultdict
        from datetime import timedelta
        from app.utils.espn_client import ESPNClient

        client = ESPNClient()
        stored = 0

        # Group games by date string (YYYYMMDD).
        # game_date is stored in UTC, but ESPN scoreboard uses US local dates.
        # Shift by -5h (approx US Eastern) so late-night UTC games (e.g. midnight
        # UTC = 7pm ET) are grouped to the correct ESPN scoreboard date.
        games_by_date: dict[str, list] = defaultdict(list)
        for game in games:
            eastern_approx = game.game_date - timedelta(hours=5)
            date_str = eastern_approx.strftime("%Y%m%d")
            games_by_date[date_str].append(game)

        dates = sorted(games_by_date.keys())
        logger.info(
            "NBA boxscore fetch: %d games across %d unique dates",
            len(games), len(dates),
        )

        total_processed = 0

        try:
            for date_idx, date_str in enumerate(dates):
                date_games = games_by_date[date_str]

                # Fetch ESPN scoreboard for this date
                from app.utils.espn_client import BASE_URL, SPORT_PATHS
                sport_path = SPORT_PATHS.get(sport.upper())
                if not sport_path:
                    continue

                try:
                    scoreboard = await client._request(
                        f"{BASE_URL}/{sport_path}/scoreboard",
                        params={"dates": date_str, "limit": 200},
                    )
                except Exception:
                    logger.warning("Failed to fetch ESPN scoreboard for %s on %s", sport, date_str)
                    total_processed += len(date_games)
                    continue

                events = scoreboard.get("events", [])

                # Build a lookup: (home_abbrev, away_abbrev) -> espn_event_id
                espn_events: dict[tuple[str, str], str] = {}
                for event in events:
                    competitors = (
                        event.get("competitions", [{}])[0].get("competitors", [])
                    )
                    home_abbrev = None
                    away_abbrev = None
                    for c in competitors:
                        abbrev = c.get("team", {}).get("abbreviation", "")
                        if c.get("homeAway") == "home":
                            home_abbrev = abbrev
                        else:
                            away_abbrev = abbrev
                    if home_abbrev and away_abbrev:
                        espn_events[(home_abbrev, away_abbrev)] = str(event.get("id", ""))

                # Match our games to ESPN events
                for game in date_games:
                    home_abbrev = id_to_abbrev.get(game.home_team_id, "")
                    away_abbrev = id_to_abbrev.get(game.away_team_id, "")

                    # Map BallDontLie abbreviations to ESPN equivalents
                    home_espn = _BDL_TO_ESPN_ABBREV.get(home_abbrev, home_abbrev)
                    away_espn = _BDL_TO_ESPN_ABBREV.get(away_abbrev, away_abbrev)

                    espn_event_id = espn_events.get((home_espn, away_espn))
                    if not espn_event_id:
                        total_processed += 1
                        continue

                    # Fetch the full summary/boxscore
                    boxscore_data = await client.get_game_summary(sport, espn_event_id)
                    if boxscore_data is None:
                        total_processed += 1
                        continue

                    for side, team_id in [
                        ("home", game.home_team_id),
                        ("away", game.away_team_id),
                    ]:
                        stats = boxscore_data.get(side, {})
                        if stats:
                            stmt = pg_insert(GameBoxscore).values(
                                game_id=game.id,
                                team_id=team_id,
                                sport=sport,
                                stats=stats,
                            )
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_boxscore_game_team",
                                set_={"stats": stmt.excluded.stats},
                            )
                            await self.session.execute(stmt)
                            stored += 1

                    total_processed += 1

                # Commit after each date
                await self.session.commit()

                if (date_idx + 1) % 10 == 0:
                    logger.info(
                        "Progress: %d/%d dates, %d/%d games processed (%d boxscores stored)",
                        date_idx + 1, len(dates), total_processed, len(games), stored,
                    )
        finally:
            await client.close()

        return stored
