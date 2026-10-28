"""Person detection with YOLOv8-nano (runs on CPU/Apple-GPU, no cloud)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    conf: float

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    def area_ratio(self, frame_shape) -> float:
        h, w = frame_shape[:2]
        return self.area / float(max(1, h * w))


class PersonDetector:
    PERSON_CLASS = 0

    def __init__(self, model_path: str = "yolov8n.pt", conf: float = 0.4, imgsz: int = 480):
        from ultralytics import YOLO  # imported lazily: heavy

        self.model = YOLO(model_path)
        self.conf = conf
        self.imgsz = imgsz

    def detect(self, frame) -> list[Detection]:
        results = self.model.predict(
            frame, classes=[self.PERSON_CLASS], conf=self.conf, imgsz=self.imgsz, verbose=False
        )
        detections: list[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            boxes = result.boxes.xyxy.cpu().numpy()
            confs = result.boxes.conf.cpu().numpy()
            for box, conf in zip(boxes, confs):
                x1, y1, x2, y2 = map(int, box)
                detections.append(Detection(x1, y1, x2, y2, float(conf)))
        return detections


def draw_detections(frame, detections: list[Detection], near_ratio: float = 0.0):
    """Draw boxes on the frame. Near (at-counter) people are drawn in green, far ones in yellow."""
    import cv2

    for det in detections:
        near = det.area_ratio(frame.shape) >= near_ratio
        colour = (0, 220, 0) if near else (0, 200, 255)
        cv2.rectangle(frame, (det.x1, det.y1), (det.x2, det.y2), colour, 2)
        label = f"person {det.conf:.2f}" + (" NEAR" if near else "")
        cv2.putText(frame, label, (det.x1, max(15, det.y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 2)
    return frame


def detect_people(frame, detector: PersonDetector | None = None):
    """Backwards compatible helper returning (x1, y1, x2, y2, cx, cy) tuples."""
    global _default_detector
    if detector is None:
        if "_default_detector" not in globals() or _default_detector is None:
            _default_detector = PersonDetector()
        detector = _default_detector
    return [(d.x1, d.y1, d.x2, d.y2, *d.center) for d in detector.detect(frame)]


_default_detector: PersonDetector | None = None
