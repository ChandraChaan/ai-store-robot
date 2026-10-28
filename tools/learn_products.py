#!/usr/bin/env python3
"""Teach the counter camera your products. No training, just photos.

  python tools/learn_products.py            # interactive, uses the counter camera from config.json
  python tools/learn_products.py --list     # what has been learned
  python tools/learn_products.py --forget coke

In the camera window:
  r  = the counter is EMPTY now (reference photo; do this first and whenever light changes)
  l  = learn: put ONE product on the counter, press l, type its key (coke) in the terminal,
       then slowly rotate the product for 6 seconds while it takes samples
  t  = test: shows what the camera recognises right now
  q  = quit
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import load_settings  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--forget", metavar="KEY")
    ap.add_argument("--source", help="override the counter camera source")
    ap.add_argument("--samples", type=int, default=12)
    ap.add_argument("--seconds", type=float, default=6.0)
    args = ap.parse_args(argv)

    settings = load_settings()
    from perception.products import ProductLibrary
    from shop.inventory import Inventory

    inventory = Inventory(settings.products_file)
    library = ProductLibrary(settings.learned_dir)
    if args.list:
        counts = library.counts()
        if not counts:
            print("Nothing learned yet.")
        for key, n in sorted(counts.items()):
            p = inventory.get(key)
            print(f"{key:<12} {n:>3} samples   {p.name if p else '(not in products.json)'}")
        return 0
    if args.forget:
        print(f"removed {library.forget(args.forget)} samples of {args.forget}")
        return 0

    import cv2

    from perception.camera import CameraStream
    from perception.counter import CounterRecognizer
    from perception.embeddings import Embedder

    role = settings.counter_camera_role()
    cfg = settings.camera(role)
    source = args.source or (cfg.source if cfg else "0")
    rotate = cfg.rotate if cfg and not args.source else 0
    print(f"Counter camera: {source} (role {role}). Known product keys: {', '.join(inventory.products)}")
    recognizer = CounterRecognizer(settings, inventory, library, Embedder(settings.embedding_model))
    recognizer.embedder.load()
    stream = CameraStream(source, rotate, cfg.width if cfg else 640).start()
    print(__doc__.split("In the camera window:")[1])

    try:
        while True:
            frame = stream.read_wait(5)
            if frame is None:
                print("waiting for camera...")
                continue
            view = frame.copy()
            rx, ry, rw, rh = recognizer.roi_rect(frame)
            cv2.rectangle(view, (rx, ry), (rx + rw, ry + rh), (200, 200, 60), 1)
            if recognizer.has_reference:
                for (x1, y1, x2, y2) in recognizer.segment(recognizer.roi_crop(frame)):
                    cv2.rectangle(view, (x1 + rx, y1 + ry), (x2 + rx, y2 + ry), (0, 200, 255), 2)
            else:
                cv2.putText(view, "press r with the counter EMPTY", (rx + 6, ry + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 140, 255), 2)
            cv2.putText(view, f"learned: {', '.join(f'{k}({n})' for k, n in library.counts().items()) or 'none'}", (8, view.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.imshow("Learn products", view)
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if key == ord("r"):
                recognizer.set_reference(frame)
                print("Empty counter reference saved.")
            if key == ord("t"):
                items = recognizer.recognize(frame)
                print("Recognised:", ", ".join(f"{it.qty}x {it.name} ({it.score:.2f})" for it in items) or "nothing")
            if key == ord("l"):
                if not recognizer.has_reference:
                    print("Press r first with the counter empty.")
                    continue
                pkey = input("Product key (e.g. coke): ").strip().lower().replace(" ", "_")
                product = inventory.get(pkey) or inventory.find(pkey)
                if product is None:
                    print(f"'{pkey}' is not in data/products.json. Add it there first.")
                    continue
                print(f"Learning {product.name}: rotate it slowly for {args.seconds:.0f} seconds...")
                added, t_end, gap = 0, time.time() + args.seconds, args.seconds / args.samples
                while time.time() < t_end:
                    f = stream.read()
                    if f is not None:
                        n, msg = recognizer.learn_from_frame(f, product.key)
                        added += n
                        v = f.copy()
                        cv2.putText(v, f"learning {product.key}: {added} samples", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 0), 2)
                        cv2.imshow("Learn products", v)
                        cv2.waitKey(1)
                    time.sleep(gap)
                print(f"Added {added} samples for {product.key}. Total: {library.counts().get(product.key, 0)}")
    finally:
        stream.stop()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
