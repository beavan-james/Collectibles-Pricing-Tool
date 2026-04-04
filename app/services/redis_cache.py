import json
import os
from functools import wraps
from typing import Optional
import redis


class RedisCache:
    def __init__(self, url: str = None, ttl: int = 900):
        self.url = url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.ttl = ttl
        self._client: Optional[redis.Redis] = None
        self._connected = False

    def connect(self):
        try:
            self._client = redis.from_url(self.url, decode_responses=True)
            self._client.ping()
            self._connected = True
            print(f"Redis connected: {self.url}")
        except Exception as e:
            print(f"Redis connection failed: {e}")
            self._connected = False

    def disconnect(self):
        if self._client:
            self._client.close()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def get(self, key: str) -> Optional[dict]:
        if not self.is_connected:
            return None
        try:
            data = self._client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            print(f"Redis get error: {e}")
        return None

    def set(self, key: str, value: dict, ttl: int = None):
        if not self.is_connected:
            return False
        try:
            self._client.setex(key, ttl or self.ttl, json.dumps(value))
            return True
        except Exception as e:
            print(f"Redis set error: {e}")
        return False

    def delete(self, key: str):
        if not self.is_connected:
            return False
        try:
            self._client.delete(key)
            return True
        except Exception as e:
            print(f"Redis delete error: {e}")
        return False

    def clear_pattern(self, pattern: str):
        if not self.is_connected:
            return 0
        try:
            keys = self._client.keys(pattern)
            if keys:
                return self._client.delete(*keys)
        except Exception as e:
            print(f"Redis clear pattern error: {e}")
        return 0


cache = RedisCache()


def cached(key_builder, ttl: int = 900):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if cache.is_connected:
                cache_key = key_builder(*args, **kwargs)
                cached_result = cache.get(cache_key)
                if cached_result is not None:
                    return cached_result

            result = func(*args, **kwargs)

            if cache.is_connected and result is not None:
                cache_key = key_builder(*args, **kwargs)
                cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator
