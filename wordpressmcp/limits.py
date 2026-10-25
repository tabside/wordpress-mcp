"""Audit log and in-memory rate limits."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from typing import Any

from .config import Settings

audit_logger = logging.getLogger("wordpressmcp.audit")


def audit(event: str, **fields: Any) -> None:
    """One JSON line per security-relevant event. Never contains passwords, tokens or content."""
    audit_logger.info(json.dumps({"event": event, "ts": int(time.time()), **fields}, ensure_ascii=False, default=str))


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__("rate limited")
        self.retry_after = retry_after


class MemoryLimiter:
    """Sliding windows in process memory (the service runs as a single process)."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, window: float, now: float) -> deque[float]:
        q = self._events[key]
        while q and q[0] < now - window:
            q.popleft()
        return q

    def check_login(self, ip: str) -> None:
        now = time.time()
        window = self._settings.login_failure_window
        q = self._prune(f"loginfail:{ip}", window, now)
        if len(q) >= self._settings.login_failures_per_ip:
            raise RateLimited(int(q[0] + window - now) + 1)

    def record_login_failure(self, ip: str) -> None:
        self._events[f"loginfail:{ip}"].append(time.time())

    def check_tool_call(self, user: str) -> None:
        now = time.time()
        q = self._prune(f"tool:{user}", 60, now)
        if len(q) >= self._settings.tool_calls_per_minute:
            raise RateLimited(int(q[0] + 60 - now) + 1)
        q.append(now)
