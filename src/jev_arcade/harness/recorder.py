"""Replay storage as JSONL, one episode per line.

The point is to watch a run again, or re-analyse confidence buckets, without
spending a second round of API calls on it.
"""

from __future__ import annotations

import json
from pathlib import Path

from jev_arcade.types import Episode

__all__ = ["write_jsonl", "read_jsonl", "append_jsonl"]


def write_jsonl(path: str | Path, episodes: list[Episode]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for episode in episodes:
            fh.write(json.dumps(episode.to_dict(), ensure_ascii=False) + "\n")
    return out


def append_jsonl(path: str | Path, episode: Episode) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(episode.to_dict(), ensure_ascii=False) + "\n")
    return out


def read_jsonl(path: str | Path) -> list[Episode]:
    out = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(Episode.from_dict(json.loads(line)))
    return out
