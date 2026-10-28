"""Project settings.

Priority (lowest to highest): defaults below -> config.json in project root
-> environment variables prefixed with STORE_ (e.g. STORE_LANGUAGE=hi)
-> command line flags in main.py.

Cameras are a dict of named roles. Any phone running DroidCam or IP Webcam
works; run `python tools/find_phones.py` to discover them on your Wi-Fi.

  "cameras": {
    "door":    {"source": "http://192.168.1.21:4747/video", "rotate": 90},
    "counter": {"source": "http://192.168.1.22:4747/video", "rotate": 0, "roi": [0, 0.3, 1, 0.7]},
    "shop":    {"source": "http://192.168.1.23:8080/video"}
  }

With one camera only, give it the role "door"; it is used for the counter as well.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_FILE = ROOT / "config.json"

CAMERA_ROLES = ("door", "counter", "shop")


@dataclass
class CameraConfig:
    source: str = "0"             # webcam index or stream URL
    rotate: int = 0               # 0, 90, 180, 270
    roi: list[float] | None = None  # [x, y, w, h] as fractions, only used for the counter
    width: int = 640

    def to_dict(self) -> dict:
        d = {"source": self.source, "rotate": self.rotate, "width": self.width}
        if self.roi:
            d["roi"] = self.roi
        return d


@dataclass
class Settings:
    store_name: str = "AI Kirana Store"
    store_info: str = "Open every day 7am to 9pm. We accept UPI and khata (credit) for members."
    currency: str = "INR"

    # ---- cameras ----
    cameras: dict = field(default_factory=lambda: {"door": {"source": "0", "rotate": 0}})
    detect_every_n_frames: int = 2
    show_window: bool = True

    # ---- person detection / presence ----
    yolo_model: str = "yolov8n.pt"
    yolo_imgsz: int = 480
    person_conf: float = 0.4
    near_area_ratio: float = 0.06
    enter_frames: int = 6
    leave_seconds: float = 4.0
    greet_cooldown_seconds: float = 12.0
    save_visit_snapshots: bool = True

    # ---- counter product recognition ----
    counter_enabled: bool = True
    counter_fps: float = 3.0                # how often the counter frame is analysed
    counter_min_area_ratio: float = 0.004   # ignore blobs smaller than this fraction of the ROI
    counter_diff_threshold: int = 32        # pixel difference vs empty-counter reference (0-255)
    counter_match_threshold: float = 0.62   # cosine similarity needed to accept a product
    counter_stable_seconds: float = 1.2     # items must stay the same this long before billing
    counter_reference_refresh_seconds: float = 20.0
    embedding_model: str = "vit_small_patch14_dinov2.lvd142m"

    # ---- voice ----
    language: str = "te"
    tts_backend: str = "say"
    tts_rate: int = 170
    stt_backend: str = "auto"
    stt_model: str = "small"
    stt_language: str = "te"
    stt_max_seconds: float = 8.0
    stt_silence_seconds: float = 1.2
    stt_start_timeout: float = 5.0

    # ---- brain ----
    use_llm: bool = True
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b-instruct"
    ollama_timeout: float = 60.0
    max_silent_turns: int = 3

    # ---- payments ----
    upi_id: str = ""                        # your UPI ID, e.g. shopname@okaxis. Empty = QR disabled
    upi_payee_name: str = ""                # name shown in the UPI app (defaults to store_name)
    accept_cash: bool = True                # owner present and can take cash
    payment_timeout_seconds: float = 180.0  # how long to wait for a UPI payment before reminding
    payment_webhook_token: str = ""         # secret for POST /api/payment_received from a phone forwarder

    # ---- integrations ----
    sheets_webhook_url: str = ""            # Google Apps Script web-app URL (see integrations/apps_script.gs)
    sheets_token: str = ""                  # shared secret, same value as in the script

    # ---- dashboard / screens ----
    dashboard: bool = True
    dashboard_port: int = 8008

    # ---- data ----
    products_file: str = str(DATA_DIR / "products.json")
    database_file: str = str(DATA_DIR / "store.db")
    visits_dir: str = str(DATA_DIR / "visits")
    learned_dir: str = str(DATA_DIR / "learned")
    outbox_file: str = str(DATA_DIR / "outbox.jsonl")

    # ---- camera helpers ----
    def camera(self, role: str) -> CameraConfig | None:
        raw = self.cameras.get(role)
        if raw is None:
            return None
        if isinstance(raw, (str, int)):
            raw = {"source": str(raw)}
        return CameraConfig(
            source=str(raw.get("source", "0")), rotate=int(raw.get("rotate", 0)),
            roi=raw.get("roi"), width=int(raw.get("width", 640)),
        )

    def counter_camera_role(self) -> str:
        return "counter" if "counter" in self.cameras else "door"

    def to_dict(self) -> dict:
        return asdict(self)


def _coerce(value, target):
    if isinstance(target, bool):
        return str(value).strip().lower() in ("1", "true", "yes", "on") if isinstance(value, str) else bool(value)
    if isinstance(target, int):
        return int(value)
    if isinstance(target, float):
        return float(value)
    if isinstance(target, dict):
        return json.loads(value) if isinstance(value, str) else dict(value)
    return str(value)


def load_settings(config_path: Path | None = None) -> Settings:
    settings = Settings()
    path = config_path or CONFIG_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"config.json is not valid JSON: {exc}")
        for f in fields(Settings):
            if f.name in data:
                setattr(settings, f.name, _coerce(data[f.name], getattr(settings, f.name)))
    for f in fields(Settings):
        env_key = "STORE_" + f.name.upper()
        if env_key in os.environ:
            setattr(settings, f.name, _coerce(os.environ[env_key], getattr(settings, f.name)))
    return settings


def save_settings_patch(patch: dict, path: Path | None = None) -> Path:
    """Merge a few keys into config.json (used by the phone finder and dashboard)."""
    path = path or CONFIG_FILE
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data.update(patch)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def save_example_config(path: Path | None = None) -> Path:
    path = path or (ROOT / "config.example.json")
    example = Settings().to_dict()
    example["cameras"] = {
        "door": {"source": "http://192.168.1.21:4747/video", "rotate": 90},
        "counter": {"source": "http://192.168.1.22:4747/video", "rotate": 0, "roi": [0, 0.25, 1, 0.75]},
    }
    example["upi_id"] = "yourshop@okaxis"
    path.write_text(json.dumps(example, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
