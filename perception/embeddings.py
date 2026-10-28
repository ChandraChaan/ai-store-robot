"""Image embeddings for product matching (DINOv2-small through timm, runs on CPU)."""
from __future__ import annotations

import threading
import time

import numpy as np


class Embedder:
    def __init__(self, model_name: str = "vit_small_patch14_dinov2.lvd142m", size: int = 224):
        self.model_name = model_name
        self.size = size
        self._model = None
        self._lock = threading.Lock()
        self.dim = 384

    def load(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            import timm
            import torch

            t0 = time.time()
            print(f"Loading product embedding model '{self.model_name}' (first run downloads ~90 MB)...")
            torch.set_num_threads(max(1, torch.get_num_threads() // 2))
            self._model = timm.create_model(self.model_name, pretrained=True, num_classes=0, img_size=self.size).eval()
            cfg = timm.data.resolve_data_config({}, model=self._model)
            self._mean = np.array(cfg["mean"], dtype=np.float32).reshape(1, 1, 3)
            self._std = np.array(cfg["std"], dtype=np.float32).reshape(1, 1, 3)
            self.dim = int(self._model.num_features)
            print(f"Embedding model ready in {time.time() - t0:.1f}s")

    def _prep(self, crop_bgr: np.ndarray) -> np.ndarray:
        import cv2

        h, w = crop_bgr.shape[:2]
        side = max(h, w)
        canvas = np.full((side, side, 3), 255, dtype=np.uint8)  # pad to square on white
        y0, x0 = (side - h) // 2, (side - w) // 2
        canvas[y0:y0 + h, x0:x0 + w] = crop_bgr
        rgb = cv2.cvtColor(cv2.resize(canvas, (self.size, self.size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        arr = (rgb.astype(np.float32) / 255.0 - self._mean) / self._std
        return arr.transpose(2, 0, 1)

    def embed(self, crops: list[np.ndarray]) -> np.ndarray:
        if not crops:
            return np.zeros((0, self.dim), dtype=np.float32)
        self.load()
        import torch

        batch = torch.from_numpy(np.stack([self._prep(c) for c in crops]))
        with torch.no_grad():
            vecs = self._model(batch).cpu().numpy().astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-8
        return vecs / norms
