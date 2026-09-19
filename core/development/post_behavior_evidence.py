"""Content-addressed, durable local evidence for every post-behavior boundary."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
from core.atomic_json_file import write_json_atomically

@dataclass(frozen=True)
class PostBehaviorEvidenceStore:
    root: Path

    def record(self, label: str, payload: object) -> str:
        value = asdict(payload) if is_dataclass(payload) and not isinstance(payload, type) else payload
        content = json.dumps({"kind": label, "payload": value}, sort_keys=True, indent=2, default=_json_value)
        digest = sha256(content.encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{digest}.json"
        if path.exists():
            if path.read_text(encoding="utf-8").strip() != content:
                raise ValueError("content-addressed post-behavior evidence was altered")
        else:
            write_json_atomically(path, json.loads(content))
        return str(path)



def _json_value(value: object) -> object:
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unsupported evidence value: {type(value).__name__}")
