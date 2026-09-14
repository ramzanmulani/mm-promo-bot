"""Tiny JSON state store. Committed back to the repo by the workflows.

Two files:
  state/history.json  - what has been posted, and where the rotation is.
  state/pending.json  - the single item currently awaiting approval.

Everything is written atomically so a cancelled Actions run cannot leave
half a file behind.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone

from .config import STATE_DIR

HISTORY = STATE_DIR / "history.json"
PENDING = STATE_DIR / "pending.json"

_DEFAULT_HISTORY = {
    "last_posted_at": None,      # ISO8601 UTC of the last SUCCESSFUL publish
    "rotation_index": 0,         # which track is next
    "track_cursor": {},          # track name -> index into that track's list
    "posted": [],                # append-only log, newest last
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path, default):
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        # Corrupt state must never wedge the bot forever.
        return json.loads(json.dumps(default))


def _write(path, data) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(STATE_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_history() -> dict:
    h = _read(HISTORY, _DEFAULT_HISTORY)
    for k, v in _DEFAULT_HISTORY.items():
        h.setdefault(k, json.loads(json.dumps(v)))
    return h


def write_history(h: dict) -> None:
    _write(HISTORY, h)


def read_pending():
    if not PENDING.exists():
        return None
    data = _read(PENDING, None)
    return data or None


def write_pending(p: dict) -> None:
    _write(PENDING, p)


def clear_pending() -> None:
    if PENDING.exists():
        PENDING.unlink()


def record_posted(entry: dict) -> None:
    h = read_history()
    entry = dict(entry)
    entry["at"] = _now()
    h["posted"].append(entry)
    h["posted"] = h["posted"][-200:]
    h["last_posted_at"] = entry["at"]
    write_history(h)
