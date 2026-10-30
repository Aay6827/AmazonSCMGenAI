import threading
import time


class TokenBucket:
    """Per-key token bucket. capacity == per_minute, refilled continuously."""

    def __init__(self, per_minute: int, clock=time.monotonic):
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self.clock = clock
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        with self._lock:
            now = self.clock()
            tokens, last = self._state.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1 - 1e-9:
                self._state[key] = (max(0.0, tokens - 1), now)
                return True, 0.0
            self._state[key] = (tokens, now)
            return False, round((1 - tokens) / self.rate, 1)