import asyncio
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Token-bucket rate limiter for API calls."""

    def __init__(self, rate: float = 5.0, period: float = 60.0):
        self.rate = rate
        self.period = period
        self.tokens = rate
        self.max_tokens = rate
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * (self.rate / self.period))
        self.last_refill = now

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                # Calculate wait time until a token is available
                wait = (1.0 - self.tokens) * (self.period / self.rate)
                logger.debug("Rate limiter: waiting %.2f seconds for token", wait)
                await asyncio.sleep(wait)


class BallDontLieClient:
    """Async client for the BallDontLie API with rate limiting and retry logic."""

    BASE_URLS = {
        "nba": "https://api.balldontlie.io/v1",
        "nfl": "https://api.balldontlie.io/v1/nfl",
    }
    MAX_RETRIES = 3

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        # Be conservative: 4 req per 60s to avoid 429s
        self.rate_limiter = TokenBucketRateLimiter(rate=4.0, period=60.0)
        self._client = httpx.AsyncClient(
            headers={"Authorization": api_key},
            timeout=httpx.Timeout(30.0),
        )

    def _base_url(self, sport: str) -> str:
        return self.BASE_URLS.get(sport.lower(), self.BASE_URLS["nba"])

    async def _request(
        self, method: str, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a rate-limited request with exponential backoff retry."""
        for attempt in range(self.MAX_RETRIES):
            await self.rate_limiter.acquire()
            try:
                response = await self._client.request(method, url, params=params)

                if response.status_code == 403:
                    logger.warning(
                        "403 Forbidden (locked endpoint on free tier): %s", url
                    )
                    return {"data": []}

                if response.status_code == 429 or response.status_code >= 500:
                    # Wait longer on 429 to let rate limit window reset
                    wait = 15 if response.status_code == 429 else 2 ** attempt
                    logger.warning(
                        "Received %d from %s, retrying in %ds (attempt %d/%d)",
                        response.status_code,
                        url,
                        wait,
                        attempt + 1,
                        self.MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as exc:
                if attempt < self.MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "HTTP error %s, retrying in %ds (attempt %d/%d)",
                        exc,
                        wait,
                        attempt + 1,
                        self.MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

        # All retries exhausted for 429/5xx
        logger.error("All %d retries exhausted for %s", self.MAX_RETRIES, url)
        return {"data": []}

    async def get_teams(self, sport: str = "nba") -> dict[str, Any]:
        """Fetch all teams for a sport."""
        url = f"{self._base_url(sport)}/teams"
        return await self._request("GET", url)

    async def get_players(
        self, sport: str = "nba", cursor: int | None = None
    ) -> dict[str, Any]:
        """Fetch a page of players for a sport."""
        url = f"{self._base_url(sport)}/players"
        params: dict[str, Any] = {"per_page": 100}
        if cursor is not None:
            params["cursor"] = cursor
        return await self._request("GET", url, params=params)

    async def get_games(
        self,
        sport: str = "nba",
        seasons: list[int] | None = None,
        dates: list[str] | None = None,
        cursor: int | None = None,
    ) -> dict[str, Any]:
        """Fetch a page of games with optional filters."""
        url = f"{self._base_url(sport)}/games"
        params: dict[str, Any] = {"per_page": 100}
        if seasons:
            params["seasons[]"] = seasons
        if dates:
            params["dates[]"] = dates
        if cursor is not None:
            params["cursor"] = cursor
        return await self._request("GET", url, params=params)

    async def get_game_stats(self, game_id: int) -> dict[str, Any]:
        """Fetch box-score stats for a specific game."""
        url = f"{self._base_url('nba')}/stats"
        params: dict[str, Any] = {"game_ids[]": [game_id], "per_page": 100}
        return await self._request("GET", url, params=params)

    async def paginate(
        self,
        fetch_func,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Auto-pagination helper that yields all items across pages."""
        cursor: int | None = None
        while True:
            response = await fetch_func(cursor=cursor, **kwargs)
            data = response.get("data", [])
            for item in data:
                yield item

            meta = response.get("meta", {})
            next_cursor = meta.get("next_cursor")
            if next_cursor is None:
                break
            cursor = next_cursor

    async def close(self) -> None:
        await self._client.aclose()


_client_instance: BallDontLieClient | None = None


def get_api_client() -> BallDontLieClient:
    """Singleton accessor for the BallDontLie API client."""
    global _client_instance
    if _client_instance is None:
        _client_instance = BallDontLieClient(api_key=settings.balldontlie_api_key)
    return _client_instance
