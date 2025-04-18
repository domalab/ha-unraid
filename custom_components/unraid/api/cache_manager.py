"""Cache manager for Unraid integration."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
from collections import OrderedDict

_LOGGER = logging.getLogger(__name__)

class CacheItemPriority(Enum):
    """Priority levels for cache items."""
    LOW = 1      # Rarely changed data (e.g., disk mapping)
    MEDIUM = 2   # Semi-stable data (e.g., array configuration)
    HIGH = 3     # Frequently changing data (e.g., CPU usage)
    CRITICAL = 4 # Always fresh data (e.g., array status)

class CacheItem:
    """A cached item with metadata."""

    def __init__(
        self,
        key: str,
        value: Any,
        ttl: int,
        priority: CacheItemPriority,
        size: int = 0
    ) -> None:
        """Initialize a cache item."""
        self.key = key
        self.value = value
        self.ttl = ttl
        self.priority = priority
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        self.access_count = 0
        self.estimated_size = size or self._estimate_size(value)

    def access(self) -> None:
        """Record an access to this cache item."""
        self.last_accessed = datetime.now()
        self.access_count += 1

    def is_expired(self) -> bool:
        """Check if the cache item has expired."""
        return (datetime.now() - self.created_at).total_seconds() > self.ttl

    def time_to_expiry(self) -> float:
        """Get the time remaining until expiry in seconds."""
        expiry_time = self.created_at + timedelta(seconds=self.ttl)
        return max(0, (expiry_time - datetime.now()).total_seconds())

    def _estimate_size(self, value: Any) -> int:
        """Estimate the memory size of a value in bytes."""
        try:
            # Use a rough estimation based on object type
            if isinstance(value, (str, bytes, bytearray)):
                return len(value)
            elif isinstance(value, (int, float, bool, type(None))):
                return 8
            elif isinstance(value, dict):
                return sum(
                    self._estimate_size(k) + self._estimate_size(v)
                    for k, v in value.items()
                )
            elif isinstance(value, (list, tuple, set)):
                return sum(self._estimate_size(v) for v in value)
            else:
                # Conservative estimate for complex objects
                return 512
        except Exception:
            # Default fallback
            return 1024


class CacheManager:
    """Memory cache manager with TTL, size limits, and priority-based eviction."""

    def __init__(
        self,
        max_size_bytes: int = 50 * 1024 * 1024, # 50MB default
        cleanup_interval: int = 300 # 5 minutes
    ) -> None:
        """Initialize the cache manager."""
        self._cache: Dict[str, CacheItem] = OrderedDict()
        self._max_size_bytes = max_size_bytes
        self._cleanup_interval = cleanup_interval
        self._current_size_bytes = 0
        self._last_cleanup = datetime.now()
        self._hit_count = 0
        self._miss_count = 0

        # TTL defaults for different priority levels
        self._default_ttls = {
            CacheItemPriority.LOW: 3600,     # 1 hour
            CacheItemPriority.MEDIUM: 600,   # 10 minutes
            CacheItemPriority.HIGH: 120,     # 2 minutes
            CacheItemPriority.CRITICAL: 30   # 30 seconds
        }

        _LOGGER.debug(
            "CacheManager initialized with max size: %s MB, cleanup interval: %s seconds",
            max_size_bytes / 1024 / 1024,
            cleanup_interval
        )

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        priority: CacheItemPriority = CacheItemPriority.MEDIUM,
        size: int = 0
    ) -> None:
        """Set a value in the cache."""
        if ttl is None:
            ttl = self._default_ttls[priority]

        # Create cache item
        cache_item = CacheItem(key, value, ttl, priority, size)

        # If item already exists, adjust size accounting
        if key in self._cache:
            self._current_size_bytes -= self._cache[key].estimated_size

        # Add item and update size
        self._cache[key] = cache_item
        self._current_size_bytes += cache_item.estimated_size

        # Check if cleanup is needed
        self._check_cleanup()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the cache."""
        if key in self._cache:
            item = self._cache[key]

            if item.is_expired():
                # Remove expired item
                self._remove_item(key)
                self._miss_count += 1
                return default

            # Update access info
            item.access()
            self._hit_count += 1
            return item.value

        self._miss_count += 1
        return default

    def get_with_fallback(self, key: str, fallback_func: Callable[[], Any], ttl: Optional[int] = None,
                         priority: CacheItemPriority = CacheItemPriority.MEDIUM) -> Any:
        """Get a value from cache or compute using fallback function."""
        # Try to get from cache
        value = self.get(key)
        if value is not None:
            return value

        # Execute fallback
        try:
            value = fallback_func()
            # Store in cache if not None
            if value is not None:
                self.set(key, value, ttl, priority)
            return value
        except Exception as err:
            _LOGGER.error("Error in fallback for cache key %s: %s", key, err)
            return None

    def delete(self, key: str) -> None:
        """Delete an item from the cache."""
        if key in self._cache:
            self._remove_item(key)

    def invalidate_by_prefix(self, prefix: str) -> int:
        """Invalidate all cache items with keys starting with the prefix."""
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
        for key in keys_to_remove:
            self._remove_item(key)
        return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all items from the cache."""
        self._cache.clear()
        self._current_size_bytes = 0
        _LOGGER.debug("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        # Count items by priority
        priority_counts = {}
        for priority in CacheItemPriority:
            priority_counts[priority.name] = len([
                item for item in self._cache.values()
                if item.priority == priority
            ])

        # Calculate hit rate
        total_requests = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total_requests) * 100 if total_requests > 0 else 0

        return {
            "item_count": len(self._cache),
            "current_size_mb": round(self._current_size_bytes / 1024 / 1024, 2),
            "max_size_mb": round(self._max_size_bytes / 1024 / 1024, 2),
            "usage_percent": round((self._current_size_bytes / self._max_size_bytes) * 100, 2),
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate_percent": round(hit_rate, 2),
            "items_by_priority": priority_counts
        }

    def _remove_item(self, key: str) -> None:
        """Remove an item from the cache."""
        if key in self._cache:
            item = self._cache[key]
            self._current_size_bytes -= item.estimated_size
            del self._cache[key]

    def _check_cleanup(self) -> None:
        """Check if cleanup is needed and perform if necessary."""
        # Check time-based cleanup
        time_for_cleanup = (
            (datetime.now() - self._last_cleanup).total_seconds() > self._cleanup_interval
        )

        # Check size-based cleanup (at 75% capacity)
        size_threshold = self._max_size_bytes * 0.75
        size_cleanup_needed = self._current_size_bytes > size_threshold

        if time_for_cleanup or size_cleanup_needed:
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up expired items and evict if needed."""
        start_time = time.time()
        initial_count = len(self._cache)
        initial_size = self._current_size_bytes

        # First remove expired items
        expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired_keys:
            self._remove_item(key)

        # If still over limit, evict by priority and last access
        if self._current_size_bytes > self._max_size_bytes:
            # Sort items by priority (low first) and then by last access (oldest first)
            items_for_eviction = sorted(
                self._cache.items(),
                key=lambda x: (x[1].priority.value, x[1].last_accessed)
            )

            # Evict until under limit
            for key, _ in items_for_eviction:
                if self._current_size_bytes <= self._max_size_bytes * 0.7:  # 70% target
                    break
                self._remove_item(key)

        self._last_cleanup = datetime.now()

        # Log cleanup results
        elapsed = time.time() - start_time
        items_removed = initial_count - len(self._cache)
        bytes_freed = initial_size - self._current_size_bytes
        mb_freed = bytes_freed / 1024 / 1024

        _LOGGER.debug(
            "Cache cleanup: removed %d items (%.2f MB), %d items remaining, current size: %.2f/%.2f MB, took %.2fs",
            items_removed,
            mb_freed,
            len(self._cache),
            self._current_size_bytes / 1024 / 1024,
            self._max_size_bytes / 1024 / 1024,
            elapsed
        )