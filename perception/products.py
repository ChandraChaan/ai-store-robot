"""Library of learned products: embeddings + sample photos under data/learned/<key>/."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np


class ProductLibrary:
    def __init__(self, learned_dir: str | Path):
        self.dir = Path(learned_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.vectors: np.ndarray = np.zeros((0, 384), dtype=np.float32)
        self.labels: list[str] = []
        self.areas: dict[str, list[float]] = {}
        self.load()

    # ---- persistence ----
    @property
    def _index_file(self) -> Path:
        return self.dir / "index.npz"

    def load(self) -> None:
        with self._lock:
            if self._index_file.exists():
                data = np.load(self._index_file, allow_pickle=False)
                self.vectors = data["vectors"].astype(np.float32)
                self.labels = [str(x) for x in data["labels"]]
                meta = json.loads(str(data["meta"])) if "meta" in data else {}
                self.areas = {k: list(map(float, v)) for k, v in meta.get("areas", {}).items()}
            else:
                self.vectors = np.zeros((0, 384), dtype=np.float32)
                self.labels, self.areas = [], {}

    def save(self) -> None:
        with self._lock:
            tmp = self._index_file.with_suffix(".tmp.npz")
            np.savez(tmp, vectors=self.vectors, labels=np.array(self.labels), meta=json.dumps({"areas": self.areas}))
            tmp.replace(self._index_file)

    # ---- editing ----
    def add(self, key: str, vectors: np.ndarray, areas: list[float] | None = None, crops: list | None = None) -> int:
        with self._lock:
            if vectors.size == 0:
                return 0
            if self.vectors.shape[1] != vectors.shape[1]:
                self.vectors = np.zeros((0, vectors.shape[1]), dtype=np.float32)
            self.vectors = np.vstack([self.vectors, vectors.astype(np.float32)])
            self.labels += [key] * len(vectors)
            if areas:
                self.areas.setdefault(key, []).extend(float(a) for a in areas)
                self.areas[key] = self.areas[key][-200:]
            if crops:
                import cv2

                folder = self.dir / key
                folder.mkdir(parents=True, exist_ok=True)
                stamp = int(time.time() * 1000)
                for i, crop in enumerate(crops[:20]):
                    cv2.imwrite(str(folder / f"{stamp}_{i}.jpg"), crop)
            self.save()
            return len(vectors)

    def forget(self, key: str) -> int:
        with self._lock:
            keep = [i for i, lbl in enumerate(self.labels) if lbl != key]
            removed = len(self.labels) - len(keep)
            self.vectors = self.vectors[keep] if keep else np.zeros((0, self.vectors.shape[1]), dtype=np.float32)
            self.labels = [self.labels[i] for i in keep]
            self.areas.pop(key, None)
            self.save()
            return removed

    # ---- queries ----
    def keys(self) -> list[str]:
        return sorted(set(self.labels))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for lbl in self.labels:
            out[lbl] = out.get(lbl, 0) + 1
        return out

    def median_area(self, key: str) -> float | None:
        vals = self.areas.get(key)
        return float(np.median(vals)) if vals else None

    def match(self, vec: np.ndarray, top_k: int = 3) -> tuple[str | None, float]:
        """Best product for an embedding: mean of its top-k similarities. Returns (key, score)."""
        with self._lock:
            if len(self.labels) == 0:
                return None, 0.0
            sims = self.vectors @ vec.astype(np.float32)
            best_key, best_score = None, -1.0
            for key in set(self.labels):
                idx = [i for i, lbl in enumerate(self.labels) if lbl == key]
                top = np.sort(sims[idx])[-top_k:]
                score = float(top.mean())
                if score > best_score:
                    best_key, best_score = key, score
            return best_key, best_score

    def match_many(self, vecs: np.ndarray) -> list[tuple[str | None, float]]:
        return [self.match(v) for v in vecs]
