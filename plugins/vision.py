PLUGIN_NAME = "vision"
PLUGIN_CORE = True  # Agent soll wissen er hat Kamera-Zugriff
PLUGIN_DESCRIPTION = "Computer Vision Tools: snapshot, face_detect, qr_detect. Saves vision_*.jpg. Modes: snapshot|face|qr"
PLUGIN_PARAMS = ["mode"]

import os

try:
    import cv2

    _cv2_available = True
except ImportError:
    _cv2_available = False


def execute(params):
    if not _cv2_available:
        return {
            "success": False,
            "result": "opencv-python not installed. Run: pip install opencv-python --break-system-packages",
        }

    home = os.path.expanduser("~")
    project = f"{home}/moruk-os"
    os.makedirs(project, exist_ok=True)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return {"success": False, "result": "No camera detected (USB/webcam?)."}

    ret, frame = cap.read()
    cap.release()
    if not ret:
        return {"success": False, "result": "Capture failed."}

    mode = params.get("mode", "snapshot")
    output = f"{project}/vision_{mode}.jpg"

    if mode == "face":
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        cv2.rectangle(frame, (10, 10), (100, 30), (0, 255, 0), -1)
        cv2.putText(
            frame,
            f"Faces: {len(faces)}",
            (15, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 0),
            2,
        )
        for x, y, w, h in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)
        detail = f"{len(faces)} face(s) detected"

    elif mode == "qr":
        detector = cv2.QRCodeDetector()
        retval, decoded_info, points, _ = detector.detectAndDecodeMulti(frame)
        text = decoded_info[0] if retval and decoded_info else "No QR"
        color = (0, 255, 0) if retval else (0, 0, 255)
        cv2.putText(
            frame, f"QR: {text}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
        )
        detail = f"QR: {text}"

    else:
        detail = "snapshot"

    cv2.imwrite(output, frame)
    return {"success": True, "result": f"{mode.upper()}: Saved {output}. {detail}"}
