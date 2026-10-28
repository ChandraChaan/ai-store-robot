#!/usr/bin/env python3
"""AI Store Robot - entry point.

  python main.py                      cameras + voice (settings from config.json / env)
  python main.py --text               no camera or mic: type as a customer; /counter, /paid, /leave simulate hardware
  python main.py --voice              microphone + speaker only, no camera
  python main.py --door 0             use the Mac webcam as the door camera
  python main.py --door http://192.168.1.21:4747/video --counter http://192.168.1.22:4747/video --rotate 90
  python tools/find_phones.py         find phones running DroidCam / IP Webcam and save them as cameras
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import CAMERA_ROLES, Settings, load_settings  # noqa: E402
from core.events import events  # noqa: E402


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="AI Store Robot")
    for role in CAMERA_ROLES:
        ap.add_argument(f"--{role}", metavar="SRC", help=f"{role} camera: index (0) or stream URL")
    ap.add_argument("--source", metavar="SRC", help="same as --door (kept for old scripts)")
    ap.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], help="rotation applied to cameras given on the command line")
    ap.add_argument("--text", action="store_true", help="text chat mode, no camera / microphone")
    ap.add_argument("--voice", action="store_true", help="voice conversation without a camera (test mic + speaker)")
    ap.add_argument("--no-window", action="store_true", help="do not open OpenCV windows")
    ap.add_argument("--no-llm", action="store_true", help="rule-based understanding only (skip Ollama)")
    ap.add_argument("--no-voice", action="store_true", help="print replies instead of speaking")
    ap.add_argument("--no-counter", action="store_true", help="disable counter product recognition")
    ap.add_argument("--no-dashboard", action="store_true")
    ap.add_argument("--lang", choices=["te", "hi", "en"], help="language the robot speaks")
    ap.add_argument("--stt", choices=["auto", "faster-whisper", "whisper", "typed", "none"])
    ap.add_argument("--stt-model", help="whisper size: tiny/base/small/medium")
    ap.add_argument("--tts", choices=["say", "edge", "none"])
    ap.add_argument("--upi", metavar="UPI_ID", help="your UPI ID for the payment QR")
    ap.add_argument("--write-config", action="store_true", help="write config.example.json with all settings and exit")
    return ap.parse_args(argv)


def apply_args(settings: Settings, args: argparse.Namespace) -> Settings:
    cams = dict(settings.cameras)
    if args.source and not args.door:
        args.door = args.source
    for role in CAMERA_ROLES:
        src = getattr(args, role)
        if src is not None:
            cams[role] = {"source": src, "rotate": args.rotate if args.rotate is not None else 0}
    settings.cameras = cams
    if args.no_window:
        settings.show_window = False
    if args.no_llm:
        settings.use_llm = False
    if args.no_voice:
        settings.tts_backend = "none"
    if args.no_counter:
        settings.counter_enabled = False
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
    if args.upi:
        settings.upi_id = args.upi
    if args.text:
        settings.stt_backend = "typed"
    return settings


def build(settings: Settings, with_counter: bool = True) -> SimpleNamespace:
    """Create every component. Heavy imports happen here so --help stays fast."""
    from brain.conversation import ConversationEngine
    from brain.llm import Brain
    from core.visit import VisitManager
    from integrations.sheets import SheetsSync
    from shop.controller import StoreController
    from shop.inventory import Inventory
    from shop.ledger import Ledger
    from shop.payments import Payments
    from voice.speech_to_text import Listener
    from voice.text_to_speech import Speaker

    inventory = Inventory(settings.products_file)
    ledger = Ledger(settings.database_file)
    speaker = Speaker(settings.tts_backend, settings.language, settings.tts_rate)
    listener = Listener(settings.stt_backend, settings.stt_model, settings.stt_language, settings.stt_max_seconds,
                        settings.stt_silence_seconds, settings.stt_start_timeout, speaker=speaker)
    payments = Payments(settings, on_event=events.add)
    store = StoreController(inventory, ledger, payments=payments, settings=settings, on_event=events.add)
    brain = Brain(inventory, settings)
    engine = ConversationEngine(store, brain, speaker, listener, settings)
    sheets = SheetsSync(settings.sheets_webhook_url, settings.sheets_token, settings.outbox_file, on_event=events.add)
    if sheets.enabled:
        print("Google Sheets sync: on")

    counter = stabilizer = library = None
    if with_counter and settings.counter_enabled:
        from perception.counter import CounterRecognizer, ItemStabilizer
        from perception.embeddings import Embedder
        from perception.products import ProductLibrary

        library = ProductLibrary(settings.learned_dir)
        counter = CounterRecognizer(settings, inventory, library, Embedder(settings.embedding_model))
        stabilizer = ItemStabilizer(settings.counter_stable_seconds)
        if not library.keys():
            print("Counter: no products learned yet. Use the dashboard 'Learn this product' or tools/learn_products.py")
        else:
            print(f"Counter: {len(library.keys())} products learned")

    visit = VisitManager(settings, store, engine, payments, speaker, counter=counter, stabilizer=stabilizer, sheets=sheets, inventory=inventory)
    return SimpleNamespace(settings=settings, inventory=inventory, ledger=ledger, speaker=speaker, listener=listener, payments=payments,
                           store=store, brain=brain, engine=engine, sheets=sheets, counter=counter, stabilizer=stabilizer,
                           library=library, visit=visit)


def start_dashboard_if_enabled(app: SimpleNamespace, cameras: dict | None = None):
    if not app.settings.dashboard:
        return None
    from ui.server import DashboardState, start_dashboard

    state = DashboardState(app.settings, app.inventory, app.ledger, app.store, visit=app.visit, library=app.library,
                           counter=app.counter, cameras=cameras or {})
    server = start_dashboard(state, app.settings.dashboard_port)
    return SimpleNamespace(server=server, state=state, shutdown=server.shutdown) if server else None


def shutdown(app: SimpleNamespace, dashboard=None) -> None:
    app.engine.stop(farewell=False)
    app.engine.join(3)
    app.speaker.wait(5)
    app.speaker.shutdown()
    app.sheets.stop()
    if dashboard:
        dashboard.shutdown()
    app.ledger.close()


# ----------------------------------------------------------------------------- text mode
TEXT_HELP = """Commands (anything else is spoken by the customer):
  /counter coke 2, chips 1   the counter camera sees these items      /counter clear
  /paid                      UPI payment arrived                       /cash   customer paid cash
  /leave                     customer walked away                      /screen what the customer screen shows
  /help                      this list                                 quit"""


def run_text_mode(settings: Settings) -> int:
    from perception.counter import CounterItem

    app = build(settings, with_counter=False)
    dashboard = start_dashboard_if_enabled(app)
    print("\nText mode. Type what a customer would say (Telugu, Tenglish, Hindi or English).")
    print(TEXT_HELP + "\n")
    store, visit, speaker = app.store, app.visit, app.speaker

    def new_customer():
        store.next_visit_id = time.strftime("%Y%m%d-%H%M%S")
        greeting = store.begin_session()
        print("Robot:", greeting)
        speaker.say(greeting, block=False)

    def simulate_counter(spec: str) -> None:
        items = []
        if spec.strip().lower() not in ("clear", "empty", ""):
            for part in spec.split(","):
                bits = part.strip().split()
                if not bits:
                    continue
                qty = int(bits[-1]) if bits[-1].isdigit() else 1
                name = " ".join(bits[:-1]) if bits[-1].isdigit() else " ".join(bits)
                product = app.inventory.find(name) or app.inventory.get(name)
                if product is None:
                    items.append(CounterItem(None, name, 0.0, (0, 0, 0, 0), qty))
                else:
                    items.append(CounterItem(product.key, product.name, 0.9, (0, 0, 0, 0), qty))
        visit.counter_items = items
        reply = store.set_counter_items(items)
        print("Robot:", reply or "(no change)")
        if reply:
            speaker.say(reply, block=False)

    new_customer()
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
            if text.startswith("/"):
                cmd, _, rest = text[1:].partition(" ")
                cmd = cmd.lower()
                if cmd == "counter":
                    simulate_counter(rest)
                elif cmd == "paid":
                    print("(payment)", "ok" if visit.simulate_payment("upi", "text-mode") else "no pending bill")
                elif cmd == "cash":
                    print("(payment)", "ok" if visit.simulate_payment("cash", "text-mode") else "no pending bill")
                elif cmd == "leave":
                    visit.on_leave()
                elif cmd == "screen":
                    sc = visit.screen_state()
                    print(f"[screen] {sc['state']}: {sc['message_te']} / {sc['message_en']}  lines={len(sc['lines'])} total={sc['total']}")
                else:
                    print(TEXT_HELP)
            else:
                reply = app.engine.handle_text(text)
                print("Robot:", reply)
                speaker.say(reply, block=False)
            if store.session is not None and not store.conversation_active and not store.awaiting_payment:
                if store.session.bill_id is None or (app.ledger.get_bill(store.session.bill_id) or {}).get("status") != "pending":
                    visit.on_leave()
            if store.session is None:
                sc = visit.screen_state()
                print(f"[screen] {sc['state']}: {sc['message_te']}")
                print("\n--- next customer ---")
                new_customer()
    finally:
        if store.session is not None:
            visit.on_leave()
        shutdown(app, dashboard)
    return 0


# ----------------------------------------------------------------------------- voice mode
def run_voice_mode(settings: Settings) -> int:
    app = build(settings, with_counter=False)
    dashboard = start_dashboard_if_enabled(app)
    if app.listener.backend in ("typed", "none"):
        print(f"Voice mode needs a speech backend, but the listener is '{app.listener.backend}'. Install faster-whisper and sounddevice, or use --text.")
        return 1
    app.listener.warm_up()
    if app.brain.llm_ready:
        app.brain.ollama.warm_up()
    print("\nVoice mode. Speak after the greeting; say 'antey' / 'bye' to finish. Ctrl+C to quit.\n")
    try:
        while True:
            input("Press Enter when a customer arrives... ")
            app.visit.on_enter()
            while app.engine.active or app.store.awaiting_payment:
                app.engine.join(timeout=1.0)
                if not app.engine.active and app.store.awaiting_payment:
                    ans = input("Waiting for payment. [p]aid / [c]ash / [l]eft: ").strip().lower()
                    if ans.startswith("p"):
                        app.visit.simulate_payment("upi", "keyboard")
                    elif ans.startswith("c"):
                        app.visit.simulate_payment("cash", "keyboard")
                    elif ans.startswith("l"):
                        break
            app.visit.on_leave()
            print("--- conversation over ---\n")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        shutdown(app, dashboard)
    return 0


# ----------------------------------------------------------------------------- camera mode
def run_camera_mode(settings: Settings) -> int:
    import cv2

    from perception.camera import CameraStream
    from perception.person import PersonDetector, draw_detections
    from perception.presence import PresenceEvent, PresenceTracker

    app = build(settings)
    door_cfg = settings.camera("door")
    if door_cfg is None:
        print("No door camera configured. Run: python tools/find_phones.py   or   python main.py --door 0")
        return 1

    # one CameraStream per distinct source; roles may share a stream
    streams: dict[str, CameraStream] = {}
    role_stream: dict[str, CameraStream] = {}
    for role in CAMERA_ROLES:
        cfg = settings.camera(role)
        if cfg is None:
            continue
        if cfg.source not in streams:
            streams[cfg.source] = CameraStream(cfg.source, cfg.rotate, cfg.width)
        role_stream[role] = streams[cfg.source]
    counter_role = settings.counter_camera_role()

    dashboard = start_dashboard_if_enabled(app, cameras=role_stream)
    print("Loading person detector...")
    detector = PersonDetector(settings.yolo_model, settings.person_conf, settings.yolo_imgsz)
    app.listener.warm_up()
    if app.brain.llm_ready:
        app.brain.ollama.warm_up()
    if app.counter is not None and app.library and app.library.keys():
        app.counter.embedder.load()
    tracker = PresenceTracker(settings.near_area_ratio, settings.enter_frames, settings.leave_seconds, settings.greet_cooldown_seconds)
    for stream in streams.values():
        stream.start()
    visits_dir = Path(settings.visits_dir)
    if settings.save_visit_snapshots:
        visits_dir.mkdir(parents=True, exist_ok=True)

    events.add("system", f"{settings.store_name} started: cameras={list(role_stream)} counter={counter_role} lang={settings.language}"
                         f" upi={'on' if settings.upi_id else 'off'} sheets={'on' if app.sheets.enabled else 'off'}")
    print("Keys in a camera window: q quit · g start conversation · l customer left · r counter is empty · p paid (UPI) · c paid cash")
    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))

    frame_no, detections, fps, fps_n, fps_t, last_warn = 0, [], 0.0, 0, time.monotonic(), 0.0
    try:
        while not stop["flag"]:
            door = role_stream["door"].read()
            if door is None:
                if time.monotonic() - last_warn > 5:
                    last_warn = time.monotonic()
                    print("Waiting for door camera frames...")
                time.sleep(0.05)
                continue
            frame_no += 1
            if frame_no % max(1, settings.detect_every_n_frames) == 0:
                detections = detector.detect(door)
                for event in tracker.update(detections, door.shape):
                    if event is PresenceEvent.ENTER:
                        events.add("presence", "customer at the counter")
                        if settings.save_visit_snapshots:
                            cv2.imwrite(str(visits_dir / time.strftime("visit_%Y%m%d_%H%M%S.jpg")), door)
                        app.visit.on_enter(door)
                    elif event is PresenceEvent.LEAVE:
                        events.add("presence", "customer left")
                        app.visit.on_leave()

            # counter camera (may be the door camera itself)
            counter_frame = door if role_stream.get(counter_role) is role_stream["door"] else role_stream[counter_role].read()
            if counter_frame is not None and app.counter is not None:
                exclude = [d for d in detections] if counter_frame is door else []
                app.counter.exclude_boxes = [(d.x1, d.y1, d.x2, d.y2) for d in exclude]
                app.visit.on_counter_frame(counter_frame, person_near=tracker.present or tracker.max_area_ratio >= settings.near_area_ratio)

            # overlays
            shown: dict[str, object] = {}
            door_view = draw_detections(door.copy(), detections, settings.near_area_ratio)
            fps_n += 1
            if time.monotonic() - fps_t >= 1.0:
                fps, fps_n, fps_t = fps_n / (time.monotonic() - fps_t), 0, time.monotonic()
            status = f"{tracker.status_text()}  talk={'yes' if app.engine.active else 'no'}  screen={app.visit.screen_state()['state']}  {fps:.0f}fps"
            cv2.putText(door_view, status, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
            cv2.putText(door_view, status, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1)
            shown["door"] = door_view
            if counter_frame is not None and app.counter is not None:
                view = door_view if counter_frame is door else counter_frame.copy()
                rx, ry, rw, rh = app.counter.roi_rect(counter_frame)
                cv2.rectangle(view, (rx, ry), (rx + rw, ry + rh), (200, 200, 60), 1)
                for it in app.visit.counter_items:
                    x1, y1, x2, y2 = it.box
                    colour = (0, 220, 0) if it.known else (0, 140, 255)
                    cv2.rectangle(view, (x1, y1), (x2, y2), colour, 2)
                    cv2.putText(view, f"{it.qty}x {it.name} {it.score:.2f}", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, colour, 2)
                if not app.counter.has_reference:
                    cv2.putText(view, "press r when the counter is empty", (rx + 6, ry + rh - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 140, 255), 2)
                shown[counter_role] = view
            for role, stream in role_stream.items():
                if role not in shown and role != "door":
                    extra = stream.read()
                    if extra is not None:
                        shown[role] = extra
            if dashboard:
                dashboard.state.presence_text = tracker.status_text()
                for role, view in shown.items():
                    raw = door if role == "door" else (counter_frame if role == counter_role else view)
                    dashboard.state.set_frame(role, view, raw=raw)
            if settings.show_window:
                for role, view in shown.items():
                    cv2.imshow(f"AI Store Robot - {role}", view)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
                if key == ord("g"):
                    events.add("presence", "manual start (g)")
                    app.visit.on_enter(door)
                if key == ord("l"):
                    app.visit.on_leave()
                    tracker.force_leave()
                if key == ord("r") and counter_frame is not None:
                    app.visit.reset_counter_reference(counter_frame)
                if key == ord("p"):
                    app.visit.simulate_payment("upi", "keyboard")
                if key == ord("c"):
                    app.visit.simulate_payment("cash", "keyboard")
    finally:
        print("Shutting down...")
        for stream in streams.values():
            stream.stop()
        shutdown(app, dashboard)
        if settings.show_window:
            cv2.destroyAllWindows()
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.write_config:
        from core.config import save_example_config

        print("wrote", save_example_config())
        return 0
    settings = apply_args(load_settings(), args)
    os.chdir(Path(__file__).resolve().parent)
    print(f"Starting {settings.store_name}")
    if args.text:
        return run_text_mode(settings)
    if args.voice:
        return run_voice_mode(settings)
    return run_camera_mode(settings)


if __name__ == "__main__":
    raise SystemExit(main())
