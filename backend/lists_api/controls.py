"""Single-process controls. Replace with gateway/global controls before scaling replicas."""

import hashlib
import hmac
import secrets
import time
from collections import OrderedDict, deque
from typing import Any


class RateLimiter:
    def __init__(self, limit: int, max_subjects: int = 10000) -> None:
        self.limit, self.max_subjects = limit, max_subjects
        self.windows: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, subject: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        # Ordered by last access, so inactive subjects can be removed without a full scan.
        while self.windows:
            oldest = next(iter(self.windows))
            if self.windows[oldest][-1] > now - 60:
                break
            self.windows.popitem(last=False)
        if subject not in self.windows and len(self.windows) >= self.max_subjects:
            return False
        window = self.windows.setdefault(subject, deque())
        self.windows.move_to_end(subject)
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= self.limit:
            return False
        window.append(now)
        return True


class ResultCache:
    def __init__(self, ttl: float, capacity: int = 256) -> None:
        self.ttl, self.capacity = ttl, capacity
        self.secret = secrets.token_bytes(32)
        self.values: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def key(self, subject: str, payload: str) -> str:
        return hmac.new(
            self.secret, (subject + "\0" + payload).encode(), hashlib.sha256
        ).hexdigest()

    def get(self, key: str) -> Any:
        now = time.monotonic()
        for expired in [k for k, (expires, _) in self.values.items() if expires <= now]:
            del self.values[expired]
        if self.ttl <= 0 or key not in self.values:
            return None
        self.values.move_to_end(key)
        return self.values[key][1]

    def put(self, key: str, value: Any) -> None:
        if self.ttl <= 0:
            return
        self.values[key] = (time.monotonic() + self.ttl, value)
        self.values.move_to_end(key)
        while len(self.values) > self.capacity:
            self.values.popitem(last=False)
