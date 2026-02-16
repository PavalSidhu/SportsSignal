import logging
import time

logger = logging.getLogger(__name__)

# Default TTLs in seconds
TEAMS_TTL = 7 * 86400  # 7 days
PLAYERS_TTL = 86400  # 1 day
GAMES_TTL = 6 * 3600  # 6 hours
STANDINGS_TTL = 12 * 3600  # 12 hours
INJURIES_TTL = 2 * 3600  # 2 hours
STATS_TTL = 86400  # 1 day


class CacheManager:
    """Simple in-memory cache freshness tracker using timestamps."""

    def __init__(self) -> None:
        self._last_fetched: dict[str, float] = {}

    def is_fresh(self, key: str, ttl_seconds: int) -> bool:
        """Check whether the cached data for `key` is still within its TTL."""
        last = self._last_fetched.get(key)
        if last is None:
            return False
        age = time.time() - last
        fresh = age < ttl_seconds
        if fresh:
            logger.debug("Cache hit for '%s' (age=%.0fs, ttl=%ds)", key, age, ttl_seconds)
        else:
            logger.debug("Cache stale for '%s' (age=%.0fs, ttl=%ds)", key, age, ttl_seconds)
        return fresh

    def mark_fetched(self, key: str) -> None:
        """Record the current time as the last-fetch timestamp for `key`."""
        self._last_fetched[key] = time.time()
        logger.debug("Marked '%s' as fetched", key)


_cache_manager_instance: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Singleton accessor for the CacheManager."""
    global _cache_manager_instance
    if _cache_manager_instance is None:
        _cache_manager_instance = CacheManager()
    return _cache_manager_instance
