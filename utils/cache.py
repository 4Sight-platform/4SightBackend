"""
In-memory LRU cache for SEO Maturity Grader.

Provides caching for external API responses to reduce rate limit pressure
and improve response times. Default TTL is 6 hours.
"""

import hashlib
import time
from functools import wraps
from typing import Any, Callable, Optional, TypeVar
from cachetools import TTLCache
import threading

# Type variable for generic cache functions
T = TypeVar('T')

# Global cache instances with thread-safe access
_cache_lock = threading.Lock()
_caches: dict = {}


def get_cache(
    name: str, 
    maxsize: int = 1000, 
    ttl: int = 21600  # 6 hours in seconds
) -> TTLCache:
    """
    Get or create a named cache instance.
    
    Args:
        name: Cache namespace (e.g., "pagespeed", "serp")
        maxsize: Maximum number of items in cache
        ttl: Time-to-live in seconds (default 6 hours)
        
    Returns:
        TTLCache instance for the namespace
    """
    with _cache_lock:
        if name not in _caches:
            _caches[name] = TTLCache(maxsize=maxsize, ttl=ttl)
        return _caches[name]


def make_cache_key(*args, **kwargs) -> str:
    """
    Create a deterministic cache key from arguments.
    
    Args:
        *args: Positional arguments
        **kwargs: Keyword arguments
        
    Returns:
        MD5 hash string as cache key
    """
    # Sort kwargs for determinism
    sorted_kwargs = sorted(kwargs.items())
    key_parts = [str(arg) for arg in args] + [f"{k}={v}" for k, v in sorted_kwargs]
    key_string = "|".join(key_parts)
    
    # Use MD5 for fast hashing (not cryptographic, just for key uniqueness)
    return hashlib.md5(key_string.encode()).hexdigest()


def cache_result(
    cache_name: str,
    ttl: Optional[int] = None,
    key_prefix: str = ""
) -> Callable:
    """
    Decorator to cache function results.
    
    Args:
        cache_name: Name of the cache to use
        ttl: Optional TTL override (uses cache default if None)
        key_prefix: Optional prefix for cache keys
        
    Returns:
        Decorator function
        
    Example:
        @cache_result("pagespeed", key_prefix="psi")
        async def get_pagespeed_metrics(url: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            cache = get_cache(cache_name, ttl=ttl) if ttl else get_cache(cache_name)
            cache_key = key_prefix + make_cache_key(*args, **kwargs)
            
            # Check cache
            with _cache_lock:
                if cache_key in cache:
                    return cache[cache_key]
            
            # Call function
            result = await func(*args, **kwargs)
            
            # Store in cache
            with _cache_lock:
                cache[cache_key] = result
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            cache = get_cache(cache_name, ttl=ttl) if ttl else get_cache(cache_name)
            cache_key = key_prefix + make_cache_key(*args, **kwargs)
            
            # Check cache
            with _cache_lock:
                if cache_key in cache:
                    return cache[cache_key]
            
            # Call function
            result = func(*args, **kwargs)
            
            # Store in cache
            with _cache_lock:
                cache[cache_key] = result
            
            return result
        
        # Return appropriate wrapper based on whether function is async
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def clear_cache(cache_name: Optional[str] = None) -> None:
    """
    Clear cache contents.
    
    Args:
        cache_name: Specific cache to clear, or None to clear all
    """
    with _cache_lock:
        if cache_name:
            if cache_name in _caches:
                _caches[cache_name].clear()
        else:
            for cache in _caches.values():
                cache.clear()


def get_cache_stats(cache_name: str) -> dict:
    """
    Get cache statistics.
    
    Args:
        cache_name: Cache to get stats for
        
    Returns:
        Dict with cache statistics
    """
    with _cache_lock:
        if cache_name not in _caches:
            return {"exists": False}
        
        cache = _caches[cache_name]
        return {
            "exists": True,
            "size": len(cache),
            "maxsize": cache.maxsize,
            "ttl": cache.ttl,
        }
