import cv2
from vision.person_detection import detect_people
from voice.text_to_speech import speak

def start_camera():

    cap = cv2.VideoCapture(0)

    greeted = False

    while True:

        ret, frame = cap.read()

        if not ret:
            break

        person_detected = detect_people(frame)

        if person_detected and not greeted:
            print("Person detected")
            speak("Hello, welcome to the store")
            greeted = True

        cv2.imshow("AI Store Camera", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()