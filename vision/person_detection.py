from ultralytics import YOLO

# load lightweight YOLO model
model = YOLO("yolov8n.pt")


def detect_people(frame):
    """
    Detect people using YOLO and return list of detections.
    Each detection returns center coordinates and bounding box.
    """

    results = model(frame, verbose=False)

    detections = []

    for result in results:

        if result.boxes is None:
            continue

        for box in result.boxes:

            cls = int(box.cls[0])

            # YOLO class 0 = person
            if cls == 0:

                x1, y1, x2, y2 = map(int, box.xyxy[0])

                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                detections.append({
                    "bbox": (x1, y1, x2, y2),
                    "center": (cx, cy)
                })

    return detections