import cv2
import threading
from ultralytics import YOLO
import time
from voice.text_to_speech import speak
from ai.conversation_engine import start_conversation
from utils import config


def start_camera():

    model = YOLO("yolov8n.pt")

    cap = cv2.VideoCapture("http://192.168.43.196:4747/video")

    previous_area = None
    last_event = None

    while True:

        ret, frame = cap.read()
        if not ret:
            print("Camera not working")
            break

        # rotate for phone camera
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        # improve brightness balance
        frame = cv2.convertScaleAbs(frame, alpha=1.2, beta=20)

        results = model(frame, verbose=False)

        if results[0].boxes is not None:

            boxes = results[0].boxes.xyxy.cpu().numpy()
            classes = results[0].boxes.cls.cpu().numpy()
            confidences = results[0].boxes.conf.cpu().numpy()

            for box, cls, conf in zip(boxes, classes, confidences):

                if int(cls) != 0:
                    continue

                if conf < 0.35:
                    continue

                x1, y1, x2, y2 = map(int, box)

                width = x2 - x1
                height = y2 - y1

                area = width * height

                # draw person box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0,255,0), 2)

                cv2.putText(
                    frame,
                    f"Person {conf:.2f}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0,255,0),
                    2
                )

                if previous_area is not None:

                    # person coming closer
                    if area > previous_area * 1.25:

                        if last_event != "enter":

                            print("Customer approaching")

                            speak("Swagatham dukananiki swagatham")

                            time.sleep(2)

                            config.customer_inside = True

                            threading.Thread(
                                target=start_conversation,
                                daemon=True
                            ).start()

                            last_event = "enter"

                    # person moving away
                    elif area < previous_area * 0.75:

                        if last_event != "leave":

                            print("Customer leaving")

                            config.customer_inside = False

                            speak("Dhanyavadalu malli randi")

                            last_event = "leave"

                previous_area = area

        cv2.imshow("AI Store Camera", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()