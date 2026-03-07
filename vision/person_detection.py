from ultralytics import YOLO

model = YOLO("yolov8n.pt")

def detect_people(frame):

    results = model(frame, verbose=False)

    detections = []

    for result in results:

        if result.boxes is None:
            continue

        for box in result.boxes:

            cls = int(box.cls[0])

            if cls == 0:  # person class

                x1, y1, x2, y2 = map(int, box.xyxy[0])

                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                detections.append((x1, y1, x2, y2, cx, cy))

    return detections