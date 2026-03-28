"""JSONL and file I/O helpers."""

import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dicts."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write a list of dicts to a JSONL file (overwrites)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for record in records:
            f.write(json.dumps(record, default=str) + "\n")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append a single record to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def write_markdown(path: Path, content: str) -> None:
    """Write markdown content to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
