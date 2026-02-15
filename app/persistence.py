"""
Persistence Layer for CMA Tool.

Defines abstract SessionStore and concrete implementations:
- RedisSessionStore (Production)
- MemorySessionStore (Testing/Fallback)
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

try:
    import redis.asyncio as redis
except ImportError:
    redis = None
    logger.warning("redis-py not installed. redis.asyncio unavailable.")

logger = logging.getLogger(__name__)


class SessionStore(ABC):
    """Abstract base class for session persistence."""

    @abstractmethod
    async def get(self, session_id: str) -> Dict[str, Any] | None:
        """Retrieve session data."""
        pass

    @abstractmethod
    async def save(self, session_id: str, data: Dict[str, Any], ttl: int | None = None) -> None:
        """Save session data."""
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Delete session data."""
        pass


class RedisSessionStore(SessionStore):
    """Redis-backed session store."""

    def __init__(self, redis_url: str):
        if redis is None:
            raise RuntimeError("RedisSessionStore requires 'redis' package.")
        self.redis = redis.from_url(redis_url, decode_responses=True)
        logger.info(f"Initialized RedisSessionStore with URL: {redis_url}")

    async def get(self, session_id: str) -> Dict[str, Any] | None:
        try:
            data = await self.redis.get(f"session:{session_id}")
            return json.loads(data) if data else None
        except Exception as e:
            logger.error(f"Redis get failed for {session_id}: {e}")
            return None

    async def save(self, session_id: str, data: Dict[str, Any], ttl: int | None = None) -> None:
        try:
            await self.redis.set(
                f"session:{session_id}",
                json.dumps(data),
                ex=ttl
            )
        except Exception as e:
            logger.error(f"Redis save failed for {session_id}: {e}")
            raise e

    async def delete(self, session_id: str) -> None:
        try:
            await self.redis.delete(f"session:{session_id}")
        except Exception as e:
            logger.error(f"Redis delete failed for {session_id}: {e}")


class MemorySessionStore(SessionStore):
    """In-memory session store for testing/fallback."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}
        logger.info("Initialized MemorySessionStore")

    async def get(self, session_id: str) -> Dict[str, Any] | None:
        return self._store.get(session_id)

    async def save(self, session_id: str, data: Dict[str, Any], ttl: int | None = None) -> None:
        self._store[session_id] = data

    async def delete(self, session_id: str) -> None:
        if session_id in self._store:
            del self._store[session_id]
