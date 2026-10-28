"""Counter recognition on synthetic frames with a fake embedder (no model download)."""
import numpy as np
import pytest

from perception.counter import CounterItem, CounterRecognizer, ItemStabilizer, signature
from perception.products import ProductLibrary


class ColorEmbedder:
    """Embeds a crop as its normalised mean colour: enough to tell red from blue items apart."""
    dim = 3

    def load(self):
        pass

    def embed(self, crops):
        if not crops:
            return np.zeros((0, 3), dtype=np.float32)
        vecs = np.array([c.reshape(-1, 3).mean(axis=0) for c in crops], dtype=np.float32) + 1e-3
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


class S:
    counter_min_area_ratio = 0.002
    counter_diff_threshold = 32
    counter_match_threshold = 0.9
    counter_stable_seconds = 1.0
    counter_reference_refresh_seconds = 5.0
    cameras = {"door": {"source": "0"}}

    def camera(self, role):
        from core.config import CameraConfig
        return CameraConfig(source="0")

    def counter_camera_role(self):
        return "door"


def blank(h=240, w=320):
    return np.full((h, w, 3), 200, dtype=np.uint8)


def put(frame, x, y, w, h, colour):
    frame[y:y + h, x:x + w] = colour
    return frame


@pytest.fixture
def recognizer(inventory, tmp_path):
    lib = ProductLibrary(tmp_path / "learned")
    rec = CounterRecognizer(S(), inventory, lib, ColorEmbedder())
    rec.set_reference(blank())
    return rec


def test_learn_then_recognize_two_products(recognizer):
    red, blue = (40, 40, 220), (220, 60, 40)
    n, msg = recognizer.learn_from_frame(put(blank(), 40, 60, 60, 80, red), "coke")
    assert n == 1 and msg == "ok"
    recognizer.learn_from_frame(put(blank(), 200, 50, 50, 50, blue), "chips")
    frame = put(put(blank(), 30, 70, 60, 80, red), 220, 60, 50, 50, blue)
    items = recognizer.recognize(frame)
    assert sorted(i.key for i in items) == ["chips", "coke"]
    assert all(i.score > 0.9 for i in items)


def test_unknown_item_and_empty_counter(recognizer):
    recognizer.learn_from_frame(put(blank(), 40, 60, 60, 80, (40, 40, 220)), "coke")
    items = recognizer.recognize(put(blank(), 100, 100, 40, 40, (20, 200, 20)))
    assert len(items) == 1 and items[0].key is None
    assert recognizer.recognize(blank()) == []


def test_quantity_from_area(recognizer):
    for _ in range(3):
        recognizer.learn_from_frame(put(blank(), 40, 60, 40, 60, (40, 40, 220)), "coke")
    items = recognizer.recognize(put(blank(), 40, 60, 80, 60, (40, 40, 220)))   # two cokes side by side, touching
    assert len(items) == 1 and items[0].key == "coke" and items[0].qty == 2


def test_person_boxes_are_ignored(recognizer):
    recognizer.exclude_boxes = [(0, 0, 160, 240)]
    frame = put(blank(), 20, 20, 100, 200, (10, 10, 10))   # a person-shaped blob on the left
    assert recognizer.recognize(frame) == []


def test_stabilizer_waits_then_emits_once():
    clock = {"t": 0.0}
    st = ItemStabilizer(1.0, clock=lambda: clock["t"])
    a = [CounterItem("coke", "Coke", 0.9, (0, 0, 1, 1), 2)]
    assert st.update(a) is None
    clock["t"] = 0.5
    assert st.update(a) is None
    clock["t"] = 1.1
    assert signature(st.update(a)) == (("coke", 2),)
    clock["t"] = 2.0
    assert st.update(a) is None                                  # unchanged: no repeat
    b = a + [CounterItem("chips", "Chips", 0.9, (0, 0, 1, 1), 1)]
    assert st.update(b) is None                                  # changed: wait again
    clock["t"] = 3.5
    assert signature(st.update(b)) == (("chips", 1), ("coke", 2))


def test_library_persist_and_forget(tmp_path):
    lib = ProductLibrary(tmp_path / "learned")
    lib.add("coke", np.array([[1, 0, 0]], dtype=np.float32), [0.01])
    lib.add("chips", np.array([[0, 1, 0]], dtype=np.float32), [0.02])
    again = ProductLibrary(tmp_path / "learned")
    assert again.keys() == ["chips", "coke"] and again.median_area("coke") == 0.01
    assert again.match(np.array([0.9, 0.1, 0], dtype=np.float32))[0] == "coke"
    assert again.forget("coke") == 1 and again.keys() == ["chips"]
