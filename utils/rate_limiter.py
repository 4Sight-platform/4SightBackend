"""
Rate limiter for external API calls.

Implements per-origin rate limiting with exponential backoff
to respect external API quotas and prevent blocking.
"""

import asyncio
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class RateLimitState:
    """Tracks rate limit state for a specific origin."""
    last_request_time: float = 0.0
    consecutive_failures: int = 0
    backoff_until: float = 0.0


class RateLimiter:
    """
    Per-origin rate limiter with exponential backoff.
    
    Features:
    - Configurable requests per second
    - Exponential backoff on failures (max 3 retries)
    - Per-origin tracking
    - Thread-safe using asyncio locks
    
    Args:
        requests_per_second: Maximum requests per second per origin
        max_retries: Maximum retry attempts
        base_backoff: Base backoff time in seconds
        max_backoff: Maximum backoff time in seconds
    """
    
    def __init__(
        self,
        requests_per_second: float = 1.0,
        max_retries: int = 3,
        base_backoff: float = 1.0,
        max_backoff: float = 30.0
    ):
        self.min_interval = 1.0 / requests_per_second
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        
        self._states: Dict[str, RateLimitState] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
    
    async def _get_lock(self, origin: str) -> asyncio.Lock:
        """Get or create a lock for an origin."""
        async with self._global_lock:
            if origin not in self._locks:
                self._locks[origin] = asyncio.Lock()
            return self._locks[origin]
    
    async def _get_state(self, origin: str) -> RateLimitState:
        """Get or create state for an origin."""
        async with self._global_lock:
            if origin not in self._states:
                self._states[origin] = RateLimitState()
            return self._states[origin]
    
    async def acquire(self, origin: str) -> None:
        """
        Acquire permission to make a request to an origin.
        
        This will wait if necessary to respect rate limits and backoff.
        
        Args:
            origin: Origin identifier (e.g., "pagespeed", "serpapi")
        """
        lock = await self._get_lock(origin)
        state = await self._get_state(origin)
        
        async with lock:
            now = time.time()
            
            # Check if we're in backoff period
            if now < state.backoff_until:
                wait_time = state.backoff_until - now
                logger.debug(f"Rate limiter: waiting {wait_time:.2f}s for backoff on {origin}")
                await asyncio.sleep(wait_time)
                now = time.time()
            
            # Check minimum interval
            elapsed = now - state.last_request_time
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                logger.debug(f"Rate limiter: waiting {wait_time:.2f}s for rate limit on {origin}")
                await asyncio.sleep(wait_time)
            
            state.last_request_time = time.time()
    
    async def report_success(self, origin: str) -> None:
        """Report a successful request to reset failure counters."""
        state = await self._get_state(origin)
        state.consecutive_failures = 0
        state.backoff_until = 0.0
    
    async def report_failure(self, origin: str) -> bool:
        """
        Report a failed request and determine if retry is allowed.
        
        Args:
            origin: Origin identifier
            
        Returns:
            True if retry is allowed, False if max retries exceeded
        """
        state = await self._get_state(origin)
        state.consecutive_failures += 1
        
        if state.consecutive_failures > self.max_retries:
            logger.warning(f"Rate limiter: max retries exceeded for {origin}")
            return False
        
        # Exponential backoff: base * 2^(failures-1)
        backoff = min(
            self.base_backoff * (2 ** (state.consecutive_failures - 1)),
            self.max_backoff
        )
        state.backoff_until = time.time() + backoff
        
        logger.debug(f"Rate limiter: backing off {backoff:.2f}s for {origin} (failure {state.consecutive_failures})")
        return True
    
    def reset(self, origin: Optional[str] = None) -> None:
        """Reset rate limiter state."""
        if origin:
            if origin in self._states:
                self._states[origin] = RateLimitState()
        else:
            self._states.clear()


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def with_rate_limit(origin: str) -> Callable:
    """
    Decorator to apply rate limiting to an async function.
    
    Args:
        origin: Origin identifier for rate limiting
        
    Example:
        @with_rate_limit("pagespeed")
        async def call_pagespeed_api(url: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            limiter = get_rate_limiter()
            
            await limiter.acquire(origin)
            
            try:
                result = await func(*args, **kwargs)
                await limiter.report_success(origin)
                return result
            except Exception as e:
                can_retry = await limiter.report_failure(origin)
                if not can_retry:
                    raise
                raise
        
        return wrapper
    
    return decorator
