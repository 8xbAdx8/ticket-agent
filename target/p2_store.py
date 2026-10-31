"""Batch storage for P2 generation: append-only, hashed, replayable."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("artifacts/runtime/p2-gen")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def sha_text(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


class Batch:
    def __init__(self, batch_id, root=ROOT, provider="deepseek", model=""):
        self.batch_id = batch_id
        self.dir = Path(root) / batch_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "raw").mkdir(exist_ok=True)
        self.manifest_path = self.dir / "batch.json"
        self.candidates_path = self.dir / "candidates.jsonl"
        self.events_path = self.dir / "generation_events.jsonl"
        self._manifest = json.loads(self.manifest_path.read_text(encoding="utf-8")) if self.manifest_path.is_file() else {
            "schema": "ticket-p2-batch/1", "batch_id": batch_id, "created_utc": now(),
            "provider": provider, "model": model, "structured_mode": "native_json",
            "prompt_version": "p2-gen/1", "status": "candidates",
            "requested": 0, "generated": 0, "failed": 0,
            "real_api_requests": 0, "tokens": {"prompt": 0, "completion": 0},
            "request_ids": [], "dimensions": {},
        }

    @property
    def manifest(self):
        return self._manifest

    def save_manifest(self, **updates):
        self._manifest.update(updates)
        self._manifest["updated_utc"] = now()
        self.manifest_path.write_text(json.dumps(self._manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        return self._manifest

    def count_candidates(self):
        if not self.candidates_path.is_file():
            return 0
        return sum(1 for line in self.candidates_path.read_text(encoding="utf-8").splitlines() if line.strip())

    def append(self, case):
        with self.candidates_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(case, ensure_ascii=False) + "\n")

    def load_candidates(self):
        if not self.candidates_path.is_file():
            return []
        return [json.loads(line) for line in self.candidates_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def save_raw(self, name, value):
        path = self.dir / "raw" / f"{name}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def write_json(self, name, value):
        path = self.dir / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    def read_json(self, name, default=None):
        path = self.dir / name
        if not path.is_file():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def record_generation(self, dimension, count, request_ids, usage, errors):
        dims = self._manifest.setdefault("dimensions", {})
        entry = dims.setdefault(dimension, {"generated": 0, "failed": 0, "requests": 0, "tokens": {"prompt": 0, "completion": 0}})
        entry["generated"] += count
        entry["failed"] += len(errors)
        entry["requests"] += len(request_ids)
        entry["tokens"]["prompt"] += usage.get("prompt") or 0
        entry["tokens"]["completion"] += usage.get("completion") or 0
        entry["errors"] = list(errors)[-10:]
        self._manifest["real_api_requests"] += len(request_ids)
        self._manifest["request_ids"].extend(request_ids)
        self._manifest["tokens"]["prompt"] += usage.get("prompt") or 0
        self._manifest["tokens"]["completion"] += usage.get("completion") or 0
        self._manifest["generated"] += count
        self._manifest["failed"] += len(errors)
        self.save_manifest()
