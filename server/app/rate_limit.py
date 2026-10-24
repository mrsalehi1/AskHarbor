import math
import time
from collections import OrderedDict
from collections.abc import Callable


class FixedWindowRateLimiter:
    """Per-client fixed window counter kept only in process memory.

    The caller passes a transient key, normally the client address. Nothing is
    written to disk or shared between processes, and the table never holds
    more than ``max_clients`` entries: expired windows are dropped first, then
    the oldest live window. A ``limit`` of 0 disables limiting entirely.

    Each worker process has its own counters, so with several uvicorn workers
    the effective limit is multiplied by the worker count. Enforce the limit at
    a reverse proxy instead when running more than one worker.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int,
        max_clients: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self.clock = clock
        self._windows: OrderedDict[str, tuple[float, int]] = OrderedDict()

    @property
    def tracked_clients(self) -> int:
        return len(self._windows)

    def tracked_keys(self) -> list[str]:
        return list(self._windows)

    def reset(self) -> None:
        self._windows.clear()

    def peek(self, key: str) -> int | None:
        """Report whether ``key`` is currently over the limit without counting.

        Lets a caller refuse an attempt before doing the work, and count only
        the attempts it wants to count (for example failed logins only).
        """
        if self.limit <= 0:
            return None
        entry = self._windows.get(key)
        if entry is None:
            return None
        now = self.clock()
        start, count = entry
        if now - start >= self.window_seconds or count < self.limit:
            return None
        return max(1, math.ceil(start + self.window_seconds - now))

    def hit(self, key: str) -> int | None:
        """Record one request for ``key``.

        Returns ``None`` when the request is allowed, otherwise the whole number
        of seconds (at least 1) until the client's window resets, suitable for a
        Retry-After header.
        """
        if self.limit <= 0:
            return None
        now = self.clock()
        entry = self._windows.get(key)
        if entry is None or now - entry[0] >= self.window_seconds:
            if entry is not None:
                del self._windows[key]
            self._make_room(now)
            self._windows[key] = (now, 1)
            return None
        start, count = entry
        if count >= self.limit:
            return max(1, math.ceil(start + self.window_seconds - now))
        self._windows[key] = (start, count + 1)
        return None

    def _make_room(self, now: float) -> None:
        if len(self._windows) < self.max_clients:
            return
        expired = [
            key for key, (start, _) in self._windows.items() if now - start >= self.window_seconds
        ]
        for key in expired:
            del self._windows[key]
        while len(self._windows) >= self.max_clients:
            self._windows.popitem(last=False)
