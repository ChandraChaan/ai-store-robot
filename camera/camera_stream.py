import cv2
import time
from vision.person_detection import detect_people
from voice.text_to_speech import speak


def start_camera():

    cap = cv2.VideoCapture("http://192.168.43.196:4747/video")

    previous_center = None
    last_event_time = 0
    cooldown = 4

    while True:

        ret, frame = cap.read()

        if not ret:
            break

        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

        detections = detect_people(frame)

        current_time = time.time()

        if len(detections) > 0:

            person = detections[0]

            x1, y1, x2, y2 = person["bbox"]
            cx, cy = person["center"]

            # draw detection box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)

            if previous_center is not None:

                movement = cy - previous_center

                # entering store
                if movement > 25 and current_time - last_event_time > cooldown:
                    print("Customer entering")
                    speak("Hello welcome to the store")
                    last_event_time = current_time

                # leaving store
                if movement < -25 and current_time - last_event_time > cooldown:
                    print("Customer leaving")
                    speak("Thank you, bye")
                    last_event_time = current_time

            previous_center = cy

        cv2.imshow("AI Store Camera", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()