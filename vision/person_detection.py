import cv2

# load pretrained human detection model
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

def detect_people(frame):

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    bodies, _ = hog.detectMultiScale(
        frame,
        winStride=(8,8)
    )

    return len(bodies) > 0