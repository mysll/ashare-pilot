"""Base class for all data sources with rate limiting and retry mechanism."""

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 30
    min_interval: float = 0.5
    max_interval: float = 2.0
    retry_times: int = 3
    retry_backoff: float = 2.0


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
]


class BaseDataSource(ABC):
    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self._last_request_time = 0.0
        self._request_count = 0
        self._minute_start = time.time()

    def _get_random_ua(self) -> str:
        return random.choice(USER_AGENTS)

    def _wait_for_rate_limit(self):
        elapsed = time.time() - self._last_request_time
        wait_time = self.config.min_interval + random.uniform(0, self.config.max_interval - self.config.min_interval)
        if elapsed < wait_time:
            time.sleep(wait_time - elapsed)
        self._last_request_time = time.time()

    def _check_rate_limit(self):
        now = time.time()
        if now - self._minute_start >= 60:
            self._request_count = 0
            self._minute_start = now
        if self._request_count >= self.config.requests_per_minute:
            wait_seconds = 60 - (now - self._minute_start)
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            self._request_count = 0
            self._minute_start = time.time()

    def _request_with_retry(self, url: str, **kwargs) -> Any:
        for attempt in range(self.config.retry_times):
            self._wait_for_rate_limit()
            self._check_rate_limit()
            try:
                result = self._make_request(url, **kwargs)
                self._request_count += 1
                return result
            except Exception as e:
                if attempt < self.config.retry_times - 1:
                    wait = self.config.retry_backoff ** attempt
                    time.sleep(wait)
                else:
                    raise e

    @abstractmethod
    def _make_request(self, url: str, **kwargs) -> Any:
        raise NotImplementedError

    @abstractmethod
    def _get_headers(self) -> dict:
        raise NotImplementedError