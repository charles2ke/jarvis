"""Simple JSON backed memory used by Jarvis skills."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_MEMORY_PATH = Path(
    os.environ.get("JARVIS_HOME", Path.home() / ".jarvis")
) / "memory.json"


class Memory:
    """Key/value store persisted as JSON.

    When ``path`` is ``None`` the memory is kept in RAM only, which keeps unit
    tests and one-off sessions free of side effects.
    """

    def __init__(self, path: Path | str | None = DEFAULT_MEMORY_PATH) -> None:
        self.path = Path(path) if path is not None else None
        self._data: Dict[str, Any] = {}
        self._session_data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(loaded, dict):
            self._data = loaded

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, indent=2, sort_keys=True)
        # Write to a sibling temporary file and swap it in, so an interrupted
        # write never leaves a truncated memory file behind.
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def append(self, key: str, value: Any) -> List[Any]:
        items = list(self._data.get(key, []))
        items.append(value)
        self.set(key, items)
        return items

    def get_session(self, key: str, default: Any = None) -> Any:
        return self._session_data.get(key, default)

    def append_session(self, key: str, value: Any) -> List[Any]:
        items = list(self._session_data.get(key, []))
        items.append(value)
        self._session_data[key] = items
        return items

    def clear_session(self, key: str | None = None) -> None:
        if key is None:
            self._session_data = {}
        else:
            self._session_data.pop(key, None)

    def clear(self, key: str | None = None) -> None:
        if key is None:
            self._data = {}
        else:
            self._data.pop(key, None)
        self._save()
