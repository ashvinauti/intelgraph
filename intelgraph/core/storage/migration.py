from typing import Any, Protocol


class MigrationFn(Protocol):
    def __call__(self, conn: Any, schema: str) -> None: ...


MIGRATIONS: dict[int, MigrationFn] = {}


def register(version: int) -> MigrationFn:
    def wrapper(fn: MigrationFn) -> MigrationFn:
        MIGRATIONS[version] = fn
        return fn

    return wrapper


@register(1)
def initial_schema(conn: Any, schema: str) -> None:
    statements = [s.strip() for s in schema.split(";") if s.strip()]
    for stmt in statements:
        conn.execute(stmt + ";")


def run_migrations(conn: Any, schema: str, current: int, target: int | None = None) -> int:
    target = target or max(MIGRATIONS.keys())
    for version in range(current + 1, target + 1):
        if version in MIGRATIONS:
            MIGRATIONS[version](conn, schema)
    return target
