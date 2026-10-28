#!/usr/bin/env python3
"""Find phones running a camera app on your Wi-Fi and save them as cameras.

Works with the free apps DroidCam (port 4747) and IP Webcam (port 8080) on
Android, and any phone app that serves an MJPEG stream.

  python tools/find_phones.py              # scan, test each stream, let you assign roles
  python tools/find_phones.py --assign door=http://192.168.1.21:4747/video counter=http://192.168.1.22:4747/video

Roles: door (sees customers; required), counter (sees the items placed on the
counter; optional, door camera is used if missing), shop (extra view; optional).
A phone can also be the customer screen: open http://<this-mac-ip>:8008/screen on it.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import CAMERA_ROLES, CONFIG_FILE, load_settings, save_settings_patch  # noqa: E402

CANDIDATES = [  # (port, path, app)
    (4747, "/video", "DroidCam"),
    (8080, "/video", "IP Webcam"),
    (8081, "/video", "IP Webcam"),
    (4747, "/mjpegfeed", "DroidCam (old)"),
]


def my_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def port_open(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan(prefix: str) -> list[tuple[str, int, str, str]]:
    hosts = [f"{prefix}.{i}" for i in range(1, 255)]
    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
        futures = {pool.submit(port_open, h, port): (h, port, path, app) for h in hosts for port, path, app in CANDIDATES}
        for fut in concurrent.futures.as_completed(futures):
            if fut.result():
                found.append(futures[fut])
    return sorted(set(found))


def test_stream(url: str) -> tuple[bool, str]:
    try:
        import cv2
    except ImportError:
        return True, "opencv not installed, skipped test"
    cap = cv2.VideoCapture(url)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return False, "no frames"
    h, w = frame.shape[:2]
    return True, f"{w}x{h}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--assign", nargs="*", metavar="ROLE=URL", help="skip scanning and save these cameras")
    ap.add_argument("--rotate", type=int, default=90, help="rotation for phones held upright (default 90)")
    args = ap.parse_args(argv)

    settings = load_settings()
    cameras = dict(settings.cameras)

    if args.assign:
        for pair in args.assign:
            role, _, url = pair.partition("=")
            if role not in CAMERA_ROLES or not url:
                print(f"bad assignment {pair!r}; roles are {', '.join(CAMERA_ROLES)}")
                return 1
            cameras[role] = {"source": url, "rotate": args.rotate}
        save_settings_patch({"cameras": cameras})
        print("Saved cameras to", CONFIG_FILE)
        return 0

    ip = my_ip()
    prefix = ip.rsplit(".", 1)[0]
    print(f"This Mac is {ip}. Scanning {prefix}.1-254 for DroidCam / IP Webcam phones...")
    found = scan(prefix)
    if not found:
        print("No phone camera found. On the phone: install DroidCam or IP Webcam (free), start the server,"
              " make sure it is on the same Wi-Fi, then run this again.")
        return 1

    streams = []
    for host, port, path, app in found:
        url = f"http://{host}:{port}{path}"
        ok, info = test_stream(url)
        print(f"  {'OK ' if ok else 'no '} {url:<40} {app:<14} {info}")
        if ok:
            streams.append(url)
    if not streams:
        return 1

    print("\nAssign roles (press Enter to skip a role). Current:", cameras)
    for role in CAMERA_ROLES:
        if not streams:
            break
        for i, url in enumerate(streams, 1):
            print(f"   {i}) {url}")
        choice = input(f"Which stream is the {role} camera? [1-{len(streams)} / Enter=skip]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(streams):
            url = streams.pop(int(choice) - 1)
            rot = input(f"Rotation for {role} (0/90/180/270) [default {args.rotate}]: ").strip()
            cameras[role] = {"source": url, "rotate": int(rot) if rot.isdigit() else args.rotate}
    save_settings_patch({"cameras": cameras})
    print(f"\nSaved to {CONFIG_FILE}:")
    for role, cam in cameras.items():
        print(f"  {role:<8} {cam}")
    print(f"\nCustomer screen: open http://{ip}:{settings.dashboard_port}/screen on a spare phone or tablet.")
    print(f"Owner dashboard: http://{ip}:{settings.dashboard_port}")
    print("Start the shop with: ./run.sh")
    try:
        subprocess.run(["say", "-v", "Rishi", "Cameras saved"], check=False, timeout=5)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
