import contextlib
import uuid
from collections.abc import Generator
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("_correlation_id", default="")


class CorrelationID:
    def __init__(self, value: str | None = None) -> None:
        self._id: str = value or uuid.uuid4().hex[:16]
        self._token: object | None = None

    @property
    def id(self) -> str:
        return self._id

    @contextlib.contextmanager
    def bind(self) -> Generator[None, None, None]:
        token = _correlation_id.set(self._id)
        self._token = token
        try:
            yield
        finally:
            _correlation_id.reset(token)

    def get_current() -> str:
        return _correlation_id.get()

    def __str__(self) -> str:
        return self._id

    def __repr__(self) -> str:
        return f"CorrelationID({self._id!r})"
