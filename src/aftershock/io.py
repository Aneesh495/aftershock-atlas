"""Atomic, bounded file ownership and canonical byte identities."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


@contextlib.contextmanager
def atomic_path(path: Path) -> Iterator[Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        yield temporary
        with temporary.open("rb") as f:
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    with atomic_path(path) as temporary:
        temporary.write_bytes(canonical(value) + b"\n")


def read_json(path: Path, limit: int = 32_000_000) -> Any:
    if path.stat().st_size > limit:
        raise ValueError(f"JSON exceeds {limit} bytes: {path.name}")
    return json.loads(path.read_bytes())


def append_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as f:
        f.write(canonical(value) + b"\n")
        f.flush()
        os.fsync(f.fileno())


def source_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def contained(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Path escapes owned directory")
    return path


@contextlib.contextmanager
def exclusive(path: Path) -> Iterator[None]:
    """Reject concurrent writers; lock files include the owning process for recovery."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)
