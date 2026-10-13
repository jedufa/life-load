from __future__ import annotations

import datetime as dt
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses the process-local lock.
    fcntl = None

_LOCKS_GUARD = threading.Lock()
_LOCKS: Dict[str, "_PathLock"] = {}


class _PathLock:
    """A re-entrant thread lock with an advisory cross-process lock."""

    def __init__(self, path: Path) -> None:
        self._thread_lock = threading.RLock()
        self._lock_path = path.with_name(f".{path.name}.lock")
        self._held = threading.local()

    def __enter__(self) -> "_PathLock":
        self._thread_lock.acquire()
        depth = int(getattr(self._held, "depth", 0))
        if depth == 0 and fcntl is not None:
            handle = None
            try:
                self._lock_path.parent.mkdir(parents=True, exist_ok=True)
                handle = self._lock_path.open("a+")
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except Exception:
                if handle is not None:
                    handle.close()
                self._thread_lock.release()
                raise
            self._held.handle = handle
        self._held.depth = depth + 1
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        depth = int(getattr(self._held, "depth", 1)) - 1
        if depth <= 0:
            handle = getattr(self._held, "handle", None)
            if handle is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()
                del self._held.handle
            self._held.depth = 0
        else:
            self._held.depth = depth
        self._thread_lock.release()


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_lock(path: Path) -> _PathLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _PathLock(path.resolve())
            _LOCKS[key] = lock
        return lock


def read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def read_json_dict_strict(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def write_json_atomic(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
    payload = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        # Persist the directory entry as well, when the platform exposes a
        # directory file descriptor. This closes the crash window between the
        # replace and the directory metadata reaching durable storage.
        try:
            dir_fd = os.open(path.parent, os.O_DIRECTORY)
        except (AttributeError, OSError):
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def read_jsonl_strict(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text:
            continue
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError(f"expected JSON object on line {idx} in {path}")
        rows.append(obj)
    return rows
