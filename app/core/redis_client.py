"""Redis client for state management."""

import redis
from typing import Optional
from ..config import settings


class RedisClient:
    """Redis client wrapper for state management."""

    def __init__(self):
        self._client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            encoding="utf-8"
        )

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """Set key with expiration time."""
        return self._client.setex(key, seconds, value)

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        return self._client.get(key)

    async def delete(self, key: str) -> int:
        """Delete key."""
        return self._client.delete(key)

    def close(self):
        """Close Redis connection."""
        self._client.close()


# Global Redis client instance
redis_client = RedisClient()
