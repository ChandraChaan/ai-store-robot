#!/usr/bin/env python3
"""AI Store Robot - entry point.

  python main.py                      camera + voice (settings from config.json / env)
  python main.py --source 0           use the Mac webcam
  python main.py --source http://192.168.1.5:4747/video --rotate 90   phone camera (DroidCam / IP Webcam)
  python main.py --text               no camera or mic: chat with the robot by typing (great for testing)
  python main.py --no-window          headless (e.g. over SSH); watch the dashboard instead
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.config import Settings, load_settings  # noqa: E402
from utils.events import events  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="AI Store Robot")
    ap.add_argument("--source", help="camera index (0) or stream URL")
    ap.add_argument("--rotate", type=int, choices=[0, 90, 180, 270])
    ap.add_argument("--text", action="store_true", help="text chat mode, no camera / microphone")
    ap.add_argument("--no-window", action="store_true", help="do not open the OpenCV window")
    ap.add_argument("--no-llm", action="store_true", help="rule-based understanding only (skip Ollama)")
    ap.add_argument("--no-voice", action="store_true", help="print replies instead of speaking")
    ap.add_argument("--no-dashboard", action="store_true")
    ap.add_argument("--lang", choices=["te", "hi", "en"], help="language the robot speaks")
    ap.add_argument("--stt", choices=["auto", "faster-whisper", "whisper", "typed", "none"])
    ap.add_argument("--stt-model", help="whisper size: tiny/base/small/medium")
    ap.add_argument("--tts", choices=["say", "edge", "none"])
    ap.add_argument("--robot", choices=["sim", "serial"])
    ap.add_argument("--port", help="serial port of the robot (with --robot serial)")
    ap.add_argument("--write-config", action="store_true", help="write config.example.json with all settings and exit")
    return ap.parse_args(argv)


def apply_args(settings: Settings, args: argparse.Namespace) -> Settings:
    if args.source is not None:
        settings.camera_source = args.source
    if args.rotate is not None:
        settings.rotate = args.rotate
    if args.no_window:
        settings.show_window = False
    if args.no_llm:
        settings.use_llm = False
    if args.no_voice:
        settings.tts_backend = "none"
    if args.no_dashboard:
        settings.dashboard = False
    if args.lang:
        settings.language = args.lang
    if args.stt:
        settings.stt_backend = args.stt
    if args.stt_model:
        settings.stt_model = args.stt_model
    if args.tts:
        settings.tts_backend = args.tts
    if args.robot:
        settings.robot_backend = args.robot
    if args.port:
        settings.robot_port = args.port
    if args.text:
        settings.stt_backend = "typed"
    return settings


def build(settings: Settings):
    """Create every component. Heavy imports happen here so --help stays fast."""
    from ai.brain import Brain
    from ai.conversation_engine import ConversationEngine
    from robot.robot_control import create_robot
    from store.inventory import Inventory
    from store.ledger import Ledger
    from store.store_controller import StoreController
    from voice.speech_to_text import Listener
    from voice.text_to_speech import Speaker

    inventory = Inventory(settings.products_file)
    ledger = Ledger(settings.database_file)
    robot = create_robot(settings, shelves=inventory.shelves, on_event=lambda text: events.add("robot", text))
    speaker = Speaker(settings.tts_backend, settings.language, settings.tts_rate)
    listener = Listener(
        settings.stt_backend, settings.stt_model, settings.stt_language, settings.stt_max_seconds,
        settings.stt_silence_seconds, settings.stt_start_timeout, speaker=speaker,
    )
    store = StoreController(inventory, ledger, robot=robot, settings=settings, on_event=events.add)
    brain = Brain(inventory, settings)
    engine = ConversationEngine(store, brain, speaker, listener, settings)
    return inventory, ledger, robot, speaker, listener, store, brain, engine


def run_text_mode(settings: Settings) -> int:
    inventory, ledger, robot, speaker, listener, store, brain, engine = build(settings)
    dashboard = start_dashboard_if_enabled(settings, inventory, ledger, store, robot)
    print("\nText mode. Type what a customer would say (Telugu, Tenglish, Hindi or English). 'quit' to exit.\n")
    greeting = store.begin_session()
    print("Robot:", greeting)
    speaker.say(greeting, block=False)
    try:
        while True:
            try:
                text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in ("quit", "exit"):
                break
            if not text:
                continue
            reply = engine.handle_text(text)
            print("Robot:", reply)
            speaker.say(reply, block=False)
            if not store.conversation_active:
                store.end_session()
                print("\n--- new customer ---")
                greeting = store.begin_session()
                print("Robot:", greeting)
                speaker.say(greeting, block=False)
    finally:
        store.end_session()
        speaker.wait(5)
        speaker.shutdown()
        if dashboard:
            dashboard.shutdown()
    return 0


def start_dashboard_if_enabled(settings, inventory, ledger, store, robot):
    if not settings.dashboard:
        return None
    from dashboard.server import DashboardState, start_dashboard

    state = DashboardState(settings, inventory, ledger, store, robot)
    server = start_dashboard(state, settings.dashboard_port)
    return _DashboardHandle(server, state) if server else None


class _DashboardHandle:
    def __init__(self, server, state):
        self.server = server
        self.state = state

    def shutdown(self):
        self.server.shutdown()


def run_camera_mode(settings: Settings) -> int:
    import cv2

    from camera.camera_stream import CameraStream
    from vision.person_detection import PersonDetector, draw_detections
    from vision.presence import PresenceEvent, PresenceTracker

    inventory, ledger, robot, speaker, listener, store, brain, engine = build(settings)
    dashboard = start_dashboard_if_enabled(settings, inventory, ledger, store, robot)

    print("Loading person detector...")
    detector = PersonDetector(settings.yolo_model, settings.person_conf, settings.yolo_imgsz)
    listener.warm_up()
    if brain.llm_ready:
        brain.ollama.warm_up()
    tracker = PresenceTracker(settings.near_area_ratio, settings.enter_frames, settings.leave_seconds, settings.greet_cooldown_seconds)
    camera = CameraStream(settings.camera_source, settings.rotate, settings.frame_width).start()
    visits_dir = Path(settings.visits_dir)
    if settings.save_visit_snapshots:
        visits_dir.mkdir(parents=True, exist_ok=True)

    events.add("system", f"{settings.store_name} robot started (camera={settings.camera_source}, lang={settings.language})")
    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))

    frame_no = 0
    detections = []
    fps_t, fps_n, fps = time.monotonic(), 0, 0.0
    last_frame_warning = 0.0
    try:
        while not stop["flag"]:
            frame = camera.read()
            if frame is None:
                if time.monotonic() - last_frame_warning > 5:
                    last_frame_warning = time.monotonic()
                    print("Waiting for camera frames...")
                time.sleep(0.05)
                continue
            frame_no += 1
            if frame_no % max(1, settings.detect_every_n_frames) == 0:
                detections = detector.detect(frame)
                for event in tracker.update(detections, frame.shape):
                    if event is PresenceEvent.ENTER:
                        events.add("presence", "customer at the counter")
                        if settings.save_visit_snapshots:
                            cv2.imwrite(str(visits_dir / time.strftime("visit_%Y%m%d_%H%M%S.jpg")), frame)
                        engine.start()
                    elif event is PresenceEvent.LEAVE:
                        events.add("presence", "customer left")
                        engine.stop(farewell=engine.active)
                if tracker.present and not engine.active and not store.conversation_active:
                    # conversation finished on its own (customer said bye); wait for them to walk away
                    pass

            # overlay
            draw_detections(frame, detections, settings.near_area_ratio)
            fps_n += 1
            if time.monotonic() - fps_t >= 1.0:
                fps, fps_n, fps_t = fps_n / (time.monotonic() - fps_t), 0, time.monotonic()
            status = f"{tracker.status_text()}  talk={'yes' if engine.active else 'no'}  llm={'on' if brain.llm_ready else 'off'}  {fps:.0f}fps"
            cv2.putText(frame, status, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            cv2.putText(frame, status, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1)
            if dashboard:
                dashboard.state.presence_text = tracker.status_text()
                dashboard.state.set_frame(frame)
            if settings.show_window:
                cv2.imshow("AI Store Robot", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("g"):  # manual trigger: start a conversation now
                    events.add("presence", "manual start (g)")
                    engine.start()
                if key == ord("l"):  # manual: customer left
                    engine.stop()
                    tracker.force_leave()
    finally:
        print("Shutting down...")
        engine.stop(farewell=False)
        engine.join(3)
        camera.stop()
        speaker.shutdown()
        if dashboard:
            dashboard.shutdown()
        if settings.show_window:
            cv2.destroyAllWindows()
        ledger.close()
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.write_config:
        from utils.config import save_example_config

        print("wrote", save_example_config())
        return 0
    settings = apply_args(load_settings(), args)
    os.chdir(Path(__file__).resolve().parent)  # yolov8n.pt and data/ are relative to the project
    print(f"Starting {settings.store_name} robot")
    if args.text:
        return run_text_mode(settings)
    return run_camera_mode(settings)


if __name__ == "__main__":
    raise SystemExit(main())
