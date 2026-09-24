import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )


class ExponentialBackoff:
    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self._policy = policy or RetryPolicy()

    def execute(self, fn: Callable[[], Any], context: str = "") -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._policy.max_retries + 1):
            try:
                return fn()
            except self._policy.retryable_exceptions as e:
                last_exc = e
                if attempt < self._policy.max_retries:
                    delay = self._compute_delay(attempt)
                    time.sleep(delay)
                else:
                    break
            except Exception as e:
                raise e

        raise RuntimeError(
            f"Operation failed after {self._policy.max_retries + 1} attempts"
            f"{' [' + context + ']' if context else ''}: {last_exc}"
        ) from last_exc

    def _compute_delay(self, attempt: int) -> float:
        delay = self._policy.base_delay * (2**attempt)
        delay = min(delay, self._policy.max_delay)
        if self._policy.jitter:
            delay *= 1.0 + random.random() * 0.5
        return delay
