import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


class JSONOutput:
    def __init__(self, pretty: bool = False) -> None:
        self._pretty = pretty
        self._indent = 2 if pretty else None

    def emit(self, data: Any, stream: TextIO | None = None) -> str:
        serialized = self._serialize(data)
        output = json.dumps(serialized, indent=self._indent, default=str)

        if stream:
            stream.write(output)
            stream.write("\n")
        else:
            print(output)

        return output

    def write_file(self, data: Any, path: str | Path) -> Path:
        path = Path(path)
        serialized = self._serialize(data)
        with open(path, "w") as f:
            json.dump(serialized, f, indent=self._indent, default=str)
        return path

    @staticmethod
    def _serialize(obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, datetime):
            return obj.astimezone(UTC).isoformat()
        if isinstance(obj, dict):
            return {k: JSONOutput._serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [JSONOutput._serialize(item) for item in obj]
        if is_dataclass(obj):
            return JSONOutput._serialize(asdict(obj))
        return str(obj)
