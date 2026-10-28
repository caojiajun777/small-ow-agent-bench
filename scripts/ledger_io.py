"""Cross-process locked JSON evidence updates.

The lock covers the entire read/mutate/replace operation. All cooperating
writers must use this module. Slot ownership itself belongs in the SQLite
ClaimStore, not in JSON file existence or an unlocked compare-and-replace.
"""

from __future__ import annotations

import errno
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


class LedgerConflict(RuntimeError):
    """The expected state/token no longer owns a JSON record."""


@contextmanager
def process_lock(path: Path, timeout: float = 30.0):
    """Lock a stable sidecar using the OS; never unlink a lock inode."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out locking {path.name}") from exc
                time.sleep(0.025)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_visit(path: Path) -> dict | None:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None

def _replace_json(path: Path, payload: dict) -> None:
    """Caller holds process_lock; every writer gets a distinct temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Windows readers/AV may briefly open the destination without delete
        # sharing. Keep ownership and the same complete temp file throughout
        # bounded retries; do not fall back to truncating the destination.
        deadline = time.monotonic() + 5.0
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                if os.name != "nt" or getattr(exc, "winerror", None) not in {5, 32, 33}:
                    raise
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.025)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _expected(current: dict | None, expected_status, expected_token) -> bool:
    if current is None:
        return expected_status is None and expected_token is None
    if expected_status is not None:
        allowed = {expected_status} if isinstance(expected_status, str) else set(expected_status)
        if current.get("status") not in allowed:
            return False
    if expected_token is not None and current.get("claim_token") != expected_token:
        return False
    return True


def write_atomic(
    path: Path, payload: dict, *, overwrite: bool = True,
    expected_status=None, expected_token: str | None = None, timeout: float = 30.0,
) -> None:
    """Write under an OS process lock; overwrite=False preserves evidence."""
    path = Path(path)
    with process_lock(path, timeout):
        if not overwrite and path.exists():
            raise FileExistsError(path)
        if not _expected(read_visit(path), expected_status, expected_token):
            raise LedgerConflict(f"Visit state/owner changed: {path.name}")
        _replace_json(path, payload)


def update_visit(
    path: Path, mutate, attempts: int = 6, *, expected_status=None,
    expected_token: str | None = None, timeout: float = 30.0,
) -> bool:
    """Read/mutate/write under a real process lock.

    True means an actual write. False means missing/mismatched state or a
    callback no-op. attempts is retained for legacy call compatibility.
    """
    del attempts
    path = Path(path)
    with process_lock(path, timeout):
        current = read_visit(path)
        if current is None or not _expected(current, expected_status, expected_token):
            return False
        if not mutate(current):
            return False
        _replace_json(path, current)
        return True
