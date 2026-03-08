import cv2
from ultralytics import YOLO
from voice.text_to_speech import speak
from ai.conversation_engine import start_conversation

def start_camera():

    model = YOLO("yolov8n.pt")

    cap = cv2.VideoCapture("http://192.168.43.196:4747/video")

    previous_positions = {}
    crossed_ids = {}

    LINE_Y = 450

    while True:

        ret, frame = cap.read()
        if not ret:
            print("Camera not working")
            break

        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        height, width = frame.shape[:2]

        # draw entrance line
        cv2.line(frame,(0,LINE_Y),(width,LINE_Y),(0,0,255),3)

        results = model.track(frame, persist=True, classes=[0])

        if results[0].boxes is not None:

            boxes = results[0].boxes.xyxy.cpu().numpy()
            ids = results[0].boxes.id
            classes = results[0].boxes.cls.cpu().numpy()
            confidences = results[0].boxes.conf.cpu().numpy()

            if ids is not None:

                ids = ids.cpu().numpy()

                for box, track_id, cls, conf in zip(boxes, ids, classes, confidences):

                    if conf < 0.4:
                        continue

                    if int(cls) != 0:
                        continue

                    x1, y1, x2, y2 = map(int, box)

                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)

                    # draw box
                    cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)

                    # draw center
                    cv2.circle(frame,(cx,cy),6,(255,0,0),-1)

                    cv2.putText(frame,f"ID {int(track_id)}",(x1,y1-10),
                                cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,255,0),2)

                    if track_id in previous_positions:

                        prev_y = previous_positions[track_id]

                        # entering
                        if prev_y < LINE_Y and cy >= LINE_Y:

                            if track_id not in crossed_ids:

                                print("Person entering")

                                speak("Swagatham dukananiki swagatham")
                                start_conversation()
                                crossed_ids[track_id] = "in"

                        # leaving
                        elif prev_y > LINE_Y and cy <= LINE_Y:

                            if track_id not in crossed_ids:

                                print("Person leaving")

                                speak("Dhanyavadalu malli randi")

                                crossed_ids[track_id] = "out"

                    previous_positions[track_id] = cy

        cv2.imshow("AI Store Camera",frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("w"):
            LINE_Y -= 10

        elif key == ord("s"):
            LINE_Y += 10

        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()