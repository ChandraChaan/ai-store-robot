"""Project settings.

Priority (lowest to highest): defaults below -> config.json in project root
-> environment variables prefixed with STORE_ (e.g. STORE_CAMERA_SOURCE=0)
-> command line flags in main.py.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CONFIG_FILE = ROOT / "config.json"


@dataclass
class Settings:
    store_name: str = "AI Kirana Store"
    store_info: str = "Open every day 7am to 9pm. We accept cash, UPI and khata (credit) for regular customers."

    # ---- camera ----
    camera_source: str = "0"          # webcam index ("0") or URL (http://<phone-ip>:4747/video)
    rotate: int = 0                   # 0, 90, 180, 270 (phone cameras usually need 90)
    frame_width: int = 640            # frames are resized to this width before detection
    detect_every_n_frames: int = 2    # run YOLO on every Nth frame to save CPU
    show_window: bool = True

    # ---- person detection / presence ----
    yolo_model: str = "yolov8n.pt"
    yolo_imgsz: int = 480
    person_conf: float = 0.4
    near_area_ratio: float = 0.06     # box must cover this fraction of the frame to count as "at the counter"
    enter_frames: int = 6             # consecutive near-detections before ENTER fires
    leave_seconds: float = 4.0        # seconds with nobody near before LEAVE fires
    greet_cooldown_seconds: float = 12.0
    save_visit_snapshots: bool = True

    # ---- voice ----
    language: str = "te"              # te | hi | en  (language the robot speaks)
    tts_backend: str = "say"          # say | edge | none
    tts_rate: int = 170
    stt_backend: str = "auto"         # auto | faster-whisper | whisper | typed | none
    stt_model: str = "small"          # tiny | base | small | medium
    stt_language: str = "te"          # language hint for whisper ("auto" to detect)
    stt_max_seconds: float = 8.0
    stt_silence_seconds: float = 1.2
    stt_start_timeout: float = 5.0

    # ---- brain (local LLM through Ollama, free) ----
    use_llm: bool = True
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b-instruct"
    ollama_timeout: float = 60.0

    # ---- conversation ----
    max_silent_turns: int = 3

    # ---- robot ----
    robot_backend: str = "sim"        # sim | serial
    robot_port: str = "/dev/cu.usbserial-0001"
    robot_baud: int = 115200

    # ---- dashboard ----
    dashboard: bool = True
    dashboard_port: int = 8008

    # ---- data ----
    products_file: str = str(DATA_DIR / "products.json")
    database_file: str = str(DATA_DIR / "store.db")
    visits_dir: str = str(DATA_DIR / "visits")

    def to_dict(self) -> dict:
        return asdict(self)


def _coerce(value: str, target_type):
    if target_type is bool:
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    return str(value)


def load_settings(config_path: Path | None = None) -> Settings:
    settings = Settings()
    path = config_path or CONFIG_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(f"config.json is not valid JSON: {exc}")
        for f in fields(Settings):
            if f.name in data:
                setattr(settings, f.name, _coerce(data[f.name], type(getattr(settings, f.name))))
    for f in fields(Settings):
        env_key = "STORE_" + f.name.upper()
        if env_key in os.environ:
            setattr(settings, f.name, _coerce(os.environ[env_key], type(getattr(settings, f.name))))
    return settings


def save_example_config(path: Path | None = None) -> Path:
    path = path or (ROOT / "config.example.json")
    path.write_text(json.dumps(Settings().to_dict(), indent=2, ensure_ascii=False) + "\n")
    return path
